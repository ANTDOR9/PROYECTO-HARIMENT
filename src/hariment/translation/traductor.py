"""
Nucleo de traduccion automatica de PROYECTO HARIMENT.

Este modulo envuelve modelos de traduccion pre-entrenados de Hugging Face
(`transformers`) para convertir texto de un idioma de origen a un idioma
de destino. Esta pensado para ser el "cerebro" comun que consumen tanto
la transcripcion de voz (Etapa 3) como el OCR (Etapa 7), sin depender de
ninguno de los dos.

Uso basico:

    from hariment.translation.traductor import Traductor

    traductor = Traductor(idioma_origen="es", idioma_destino="en")
    resultado = traductor.traducir("Hola, como estas?")
    print(resultado)  # "Hello, how are you?"

El modelo se descarga la primera vez que se usa un par de idiomas y luego
queda en cache local (carpeta de cache de Hugging Face), por lo que las
siguientes ejecuciones son mas rapidas.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache


# Mapa de pares de idiomas soportados -> modelo de Hugging Face a usar.
# Se prioriza portugues por ser el segundo idioma pedido para la zona
# de Latinoamerica, pero el diccionario esta pensado para crecer.
MODELOS_POR_PAR_DE_IDIOMA: dict[tuple[str, str], str] = {
    ("es", "en"): "Helsinki-NLP/opus-mt-es-en",
    ("en", "es"): "Helsinki-NLP/opus-mt-en-es",
    ("es", "pt"): "Helsinki-NLP/opus-mt-es-pt",
    ("pt", "es"): "Helsinki-NLP/opus-mt-pt-es",
    ("en", "pt"): "Helsinki-NLP/opus-mt-en-pt-BR",
}


class IdiomaNoSoportadoError(Exception):
    """Se lanza cuando no hay un modelo configurado para el par de idiomas pedido."""


@dataclass
class ResultadoTraduccion:
    """Resultado de una traduccion, con el texto original y el traducido."""

    texto_original: str
    texto_traducido: str
    idioma_origen: str
    idioma_destino: str


class Traductor:
    """Traduce texto entre idiomas usando modelos pre-entrenados de `transformers`.

    El modelo real solo se carga en memoria la primera vez que se necesita
    (carga perezosa), para no pagar ese costo si el usuario nunca activa
    la traduccion en la interfaz.
    """

    def __init__(self, idioma_origen: str = "es", idioma_destino: str = "en") -> None:
        self.idioma_origen = idioma_origen
        self.idioma_destino = idioma_destino
        self._pipeline = None

    @property
    def par_idiomas(self) -> tuple[str, str]:
        return (self.idioma_origen, self.idioma_destino)

    def _nombre_modelo(self) -> str:
        try:
            return MODELOS_POR_PAR_DE_IDIOMA[self.par_idiomas]
        except KeyError as error:
            disponibles = ", ".join(f"{o}->{d}" for o, d in MODELOS_POR_PAR_DE_IDIOMA)
            raise IdiomaNoSoportadoError(
                f"No hay modelo configurado para traducir de "
                f"'{self.idioma_origen}' a '{self.idioma_destino}'. "
                f"Pares disponibles actualmente: {disponibles}"
            ) from error

    def _obtener_pipeline(self):
        if self._pipeline is None:
            self._pipeline = _cargar_pipeline_traduccion(
                self._nombre_modelo(), self.idioma_origen, self.idioma_destino
            )
        return self._pipeline

    def cambiar_idiomas(self, idioma_origen: str, idioma_destino: str) -> None:
        """Cambia el par de idiomas activo. Si cambia, se libera el modelo cargado
        para que la proxima traduccion cargue el modelo correcto."""
        if (idioma_origen, idioma_destino) != self.par_idiomas:
            self.idioma_origen = idioma_origen
            self.idioma_destino = idioma_destino
            self._pipeline = None

    def traducir(self, texto: str) -> ResultadoTraduccion:
        """Traduce un texto del idioma de origen al idioma de destino configurados."""
        texto = (texto or "").strip()
        if not texto:
            return ResultadoTraduccion(
                texto_original=texto,
                texto_traducido="",
                idioma_origen=self.idioma_origen,
                idioma_destino=self.idioma_destino,
            )

        pipeline_traduccion = self._obtener_pipeline()
        salida = pipeline_traduccion(texto)
        texto_traducido = salida[0]["translation_text"]

        return ResultadoTraduccion(
            texto_original=texto,
            texto_traducido=texto_traducido,
            idioma_origen=self.idioma_origen,
            idioma_destino=self.idioma_destino,
        )


class _TraductorManual:
    """Envoltura minima que imita la interfaz de un pipeline de `transformers`
    (`pipeline_traduccion(texto)` -> `[{"translation_text": "..."}]`), pero
    llamando al modelo y al tokenizer directamente.

    Se hizo asi -en vez de usar `transformers.pipeline("translation", ...)`
    o `TranslationPipeline`- porque esas dos APIs de alto nivel han ido
    cambiando de forma incompatible entre versiones de `transformers`
    (algunas no registran la tarea "translation" ni con el formato
    "translation_XX_to_YY", y otras ni siquiera exportan la clase
    `TranslationPipeline`). Cargar el modelo y el tokenizer con las clases
    `AutoModelForSeq2SeqLM`/`AutoTokenizer` y llamar `.generate()` a mano es
    una API mucho mas estable entre versiones.
    """

    def __init__(self, modelo, tokenizador) -> None:
        self._modelo = modelo
        self._tokenizador = tokenizador

    def __call__(self, texto: str):
        entradas = self._tokenizador(texto, return_tensors="pt", truncation=True)
        tokens_generados = self._modelo.generate(**entradas, max_new_tokens=512)
        texto_traducido = self._tokenizador.decode(tokens_generados[0], skip_special_tokens=True)
        return [{"translation_text": texto_traducido}]


@lru_cache(maxsize=8)
def _cargar_pipeline_traduccion(nombre_modelo: str, idioma_origen: str, idioma_destino: str):
    """Carga (y cachea en memoria) el modelo y tokenizer de traduccion.

    Separado en una funcion con cache propia para que, si la aplicacion
    cambia de par de idiomas y luego vuelve al anterior, no se vuelva a
    descargar/cargar el mismo modelo dos veces. `idioma_origen`/`idioma_destino`
    solo se usan como parte de la clave de cache (distintos pares -> distinta
    entrada), no se le pasan al modelo.
    """
    # Import perezoso: evita cargar torch/transformers si este modulo se
    # importa pero nunca se usa (por ejemplo en tests que solo revisan la
    # configuracion de idiomas).
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    modelo = AutoModelForSeq2SeqLM.from_pretrained(nombre_modelo)
    tokenizador = AutoTokenizer.from_pretrained(nombre_modelo)
    return _TraductorManual(modelo, tokenizador)


def idiomas_soportados() -> list[tuple[str, str]]:
    """Devuelve la lista de pares (origen, destino) que tienen modelo configurado."""
    return list(MODELOS_POR_PAR_DE_IDIOMA.keys())


if __name__ == "__main__":
    # Prueba rapida por consola:
    #   python -m hariment.translation.traductor "Hola, como estas?"
    import sys

    texto_prueba = " ".join(sys.argv[1:]) or "Hola, como estas? Este es un texto de prueba."
    traductor = Traductor(idioma_origen="es", idioma_destino="en")
    resultado = traductor.traducir(texto_prueba)

    print(f"[{resultado.idioma_origen} -> {resultado.idioma_destino}]")
    print(f"Original : {resultado.texto_original}")
    print(f"Traducido: {resultado.texto_traducido}")
