"""
API de PROYECTO HARIMENT (FastAPI).

Expone el mismo "cerebro" que usa la interfaz de escritorio (traduccion,
transcripcion de audio, OCR de capturas de pantalla) detras de endpoints
HTTP, para que otros clientes -una futura app movil, un script, u otra
interfaz- puedan usarlo sin duplicar logica.

Endpoints:

    GET  /salud                      -> estado del servicio
    GET  /idiomas                    -> pares de idiomas soportados para traducir
    POST /traducir                   -> traduce un texto
    POST /audio/transcribir          -> transcribe un archivo de audio subido (Whisper)
    POST /ocr/captura                -> captura la pantalla del servidor, reconoce y traduce el texto

Ejecutar con:

    python scripts/run_api.py

o directamente:

    uvicorn hariment.api.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import tempfile
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from hariment.ocr.captura_pantalla import capturar_pantalla
from hariment.ocr.reconocimiento_texto import MotorOcrNoSoportadoError, ReconocedorTexto
from hariment.translation.traductor import IdiomaNoSoportadoError, Traductor, idiomas_soportados

app = FastAPI(
    title="PROYECTO HARIMENT API",
    description="Traduccion en tiempo real: voz, audio del sistema y OCR de pantalla.",
    version="0.1.0",
)

# Los traductores se cachean por par de idiomas para no recargar el
# modelo de `transformers` en cada solicitud (ver hariment.translation.traductor,
# que ademas cachea el pipeline internamente).
_traductores_por_par: dict[tuple[str, str], Traductor] = {}

# Un unico reconocedor de OCR reutilizado entre solicitudes.
_reconocedor_texto = ReconocedorTexto(motor="pytesseract")

# El modelo de Whisper se carga una sola vez, la primera vez que se pide
# transcribir audio (es pesado: no conviene cargarlo al arrancar la API
# si nunca se usa ese endpoint).
_modelo_whisper = None


def _obtener_traductor(idioma_origen: str, idioma_destino: str) -> Traductor:
    clave = (idioma_origen, idioma_destino)
    if clave not in _traductores_por_par:
        _traductores_por_par[clave] = Traductor(idioma_origen=idioma_origen, idioma_destino=idioma_destino)
    return _traductores_por_par[clave]


def _obtener_modelo_whisper(nombre_modelo: str = "small"):
    global _modelo_whisper
    if _modelo_whisper is None:
        import whisper

        _modelo_whisper = whisper.load_model(nombre_modelo)
    return _modelo_whisper


# ----------------------------------------------------------------------
# Modelos de datos (Pydantic)
# ----------------------------------------------------------------------


class SolicitudTraduccion(BaseModel):
    texto: str
    idioma_origen: str = "es"
    idioma_destino: str = "en"


class RespuestaTraduccion(BaseModel):
    texto_original: str
    texto_traducido: str
    idioma_origen: str
    idioma_destino: str


class RespuestaTranscripcion(BaseModel):
    texto: str
    idioma_detectado: Optional[str] = None
    traduccion: Optional[RespuestaTraduccion] = None


class RespuestaOcr(BaseModel):
    texto_reconocido: str
    traduccion: Optional[RespuestaTraduccion] = None


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------


@app.get("/salud")
def salud() -> dict:
    """Chequeo simple de que la API esta arriba (util para la interfaz o para monitoreo)."""
    return {"estado": "ok", "servicio": "PROYECTO HARIMENT API"}


@app.get("/idiomas")
def idiomas() -> list[dict]:
    """Lista los pares de idiomas (origen, destino) con modelo de traduccion disponible."""
    return [{"origen": origen, "destino": destino} for origen, destino in idiomas_soportados()]


@app.post("/traducir", response_model=RespuestaTraduccion)
def traducir(solicitud: SolicitudTraduccion) -> RespuestaTraduccion:
    """Traduce un texto del idioma de origen al idioma de destino indicados."""
    try:
        traductor = _obtener_traductor(solicitud.idioma_origen, solicitud.idioma_destino)
        resultado = traductor.traducir(solicitud.texto)
    except IdiomaNoSoportadoError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return RespuestaTraduccion(
        texto_original=resultado.texto_original,
        texto_traducido=resultado.texto_traducido,
        idioma_origen=resultado.idioma_origen,
        idioma_destino=resultado.idioma_destino,
    )


@app.post("/audio/transcribir", response_model=RespuestaTranscripcion)
async def transcribir_audio(
    archivo: UploadFile = File(..., description="Archivo de audio (wav, mp3, m4a, etc.)"),
    idioma_origen: Optional[str] = None,
    idioma_destino: Optional[str] = None,
) -> RespuestaTranscripcion:
    """Transcribe un archivo de audio subido usando Whisper.

    Si se pasan `idioma_origen` e `idioma_destino`, tambien traduce el
    texto transcrito y lo incluye en la respuesta.
    """
    with tempfile.NamedTemporaryFile(suffix=f"_{archivo.filename}", delete=True) as archivo_temporal:
        archivo_temporal.write(await archivo.read())
        archivo_temporal.flush()

        modelo_whisper = _obtener_modelo_whisper()
        resultado = modelo_whisper.transcribe(archivo_temporal.name, language=idioma_origen, fp16=False)

    texto = (resultado.get("text") or "").strip()
    idioma_detectado = resultado.get("language")

    traduccion = None
    if texto and idioma_destino:
        origen_para_traducir = idioma_origen or idioma_detectado
        try:
            traductor = _obtener_traductor(origen_para_traducir, idioma_destino)
            resultado_traduccion = traductor.traducir(texto)
            traduccion = RespuestaTraduccion(
                texto_original=resultado_traduccion.texto_original,
                texto_traducido=resultado_traduccion.texto_traducido,
                idioma_origen=resultado_traduccion.idioma_origen,
                idioma_destino=resultado_traduccion.idioma_destino,
            )
        except IdiomaNoSoportadoError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return RespuestaTranscripcion(texto=texto, idioma_detectado=idioma_detectado, traduccion=traduccion)


@app.post("/ocr/captura", response_model=RespuestaOcr)
def ocr_captura(
    idioma_texto: str = "es",
    idioma_destino: Optional[str] = None,
) -> RespuestaOcr:
    """Captura la pantalla *del servidor donde corre la API*, reconoce el
    texto (OCR) y, si se pide `idioma_destino`, lo traduce.

    Nota: esto solo tiene sentido cuando la API corre en la misma maquina
    de escritorio del usuario (uso local), no en un servidor remoto.
    """
    try:
        imagen = capturar_pantalla()
        texto = _reconocedor_texto.reconocer(imagen, idioma=idioma_texto)
    except MotorOcrNoSoportadoError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    traduccion = None
    if texto and idioma_destino:
        try:
            traductor = _obtener_traductor(idioma_texto, idioma_destino)
            resultado_traduccion = traductor.traducir(texto)
            traduccion = RespuestaTraduccion(
                texto_original=resultado_traduccion.texto_original,
                texto_traducido=resultado_traduccion.texto_traducido,
                idioma_origen=resultado_traduccion.idioma_origen,
                idioma_destino=resultado_traduccion.idioma_destino,
            )
        except IdiomaNoSoportadoError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return RespuestaOcr(texto_reconocido=texto, traduccion=traduccion)
