"""Pruebas de la API (hariment.api.main), usando el TestClient de FastAPI.

Los endpoints de traduccion y OCR se prueban simulando (monkeypatch) el
Traductor y el ReconocedorTexto para no descargar modelos reales ni
requerir una pantalla; el objetivo es verificar el contrato HTTP
(rutas, validacion, forma de la respuesta), no la calidad del modelo.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from hariment.api import main as api_main
from hariment.translation.traductor import IdiomaNoSoportadoError


@pytest.fixture()
def cliente():
    return TestClient(api_main.app)


def test_salud(cliente):
    respuesta = cliente.get("/salud")
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "ok"


def test_idiomas_incluye_es_en(cliente):
    respuesta = cliente.get("/idiomas")
    assert respuesta.status_code == 200
    pares = [(item["origen"], item["destino"]) for item in respuesta.json()]
    assert ("es", "en") in pares


def test_traducir_devuelve_texto_traducido(cliente, monkeypatch):
    def traducir_falso(self, texto):
        return SimpleNamespace(
            texto_original=texto,
            texto_traducido=texto.upper(),
            idioma_origen=self.idioma_origen,
            idioma_destino=self.idioma_destino,
        )

    monkeypatch.setattr(api_main.Traductor, "traducir", traducir_falso)

    respuesta = cliente.post(
        "/traducir", json={"texto": "hola", "idioma_origen": "es", "idioma_destino": "en"}
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["texto_traducido"] == "HOLA"
    assert cuerpo["idioma_destino"] == "en"


def test_traducir_con_idioma_no_soportado_devuelve_400(cliente, monkeypatch):
    def traducir_que_falla(self, texto):
        raise IdiomaNoSoportadoError("par de idiomas no soportado")

    monkeypatch.setattr(api_main.Traductor, "traducir", traducir_que_falla)

    respuesta = cliente.post(
        "/traducir", json={"texto": "hola", "idioma_origen": "es", "idioma_destino": "de"}
    )

    assert respuesta.status_code == 400


def test_ocr_captura_devuelve_texto_reconocido(cliente, monkeypatch):
    monkeypatch.setattr(api_main, "capturar_pantalla", lambda: "imagen-falsa")
    monkeypatch.setattr(
        api_main._reconocedor_texto, "reconocer", lambda imagen, idioma: "texto de la pantalla"
    )

    respuesta = cliente.post("/ocr/captura", params={"idioma_texto": "es"})

    assert respuesta.status_code == 200
    assert respuesta.json()["texto_reconocido"] == "texto de la pantalla"
    assert respuesta.json()["traduccion"] is None  # no se pidio idioma_destino


def test_ocr_captura_traduce_si_se_pide_idioma_destino(cliente, monkeypatch):
    monkeypatch.setattr(api_main, "capturar_pantalla", lambda: "imagen-falsa")
    monkeypatch.setattr(
        api_main._reconocedor_texto, "reconocer", lambda imagen, idioma: "hola"
    )

    def traducir_falso(self, texto):
        return SimpleNamespace(
            texto_original=texto,
            texto_traducido="hello",
            idioma_origen=self.idioma_origen,
            idioma_destino=self.idioma_destino,
        )

    monkeypatch.setattr(api_main.Traductor, "traducir", traducir_falso)

    respuesta = cliente.post("/ocr/captura", params={"idioma_texto": "es", "idioma_destino": "en"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["texto_reconocido"] == "hola"
    assert cuerpo["traduccion"]["texto_traducido"] == "hello"
