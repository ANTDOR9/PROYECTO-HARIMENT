"""Pruebas del modulo de OCR (hariment.ocr.reconocimiento_texto).

No se abre pantalla real ni se descargan modelos: se prueba la
seleccion/validacion de motor y el mapeo de codigos de idioma, con un
motor "pytesseract" simulado (no requiere tener Tesseract instalado en
esta maquina para correr estas pruebas).
"""

import pytest

from hariment.ocr.reconocimiento_texto import (
    CODIGOS_IDIOMA_TESSERACT,
    MotorOcrNoSoportadoError,
    ReconocedorTexto,
)


def test_motor_no_soportado_lanza_error_al_crear():
    with pytest.raises(MotorOcrNoSoportadoError):
        ReconocedorTexto(motor="motor-inventado")


def test_motor_por_defecto_es_pytesseract():
    reconocedor = ReconocedorTexto()
    assert reconocedor.motor == "pytesseract"


def test_mapa_de_idiomas_incluye_espanol_ingles_portugues():
    assert CODIGOS_IDIOMA_TESSERACT["es"] == "spa"
    assert CODIGOS_IDIOMA_TESSERACT["en"] == "eng"
    assert CODIGOS_IDIOMA_TESSERACT["pt"] == "por"


def test_reconocer_con_pytesseract_usa_el_codigo_de_idioma_correcto(monkeypatch):
    """Verifica que se traduce 'es' -> 'spa' al llamar a pytesseract,
    sin necesitar tener Tesseract realmente instalado."""
    import types
    import sys

    llamadas = {}

    def image_to_string_falso(imagen, lang):
        llamadas["lang"] = lang
        return "  texto reconocido  "

    modulo_falso = types.SimpleNamespace(image_to_string=image_to_string_falso)
    monkeypatch.setitem(sys.modules, "pytesseract", modulo_falso)

    reconocedor = ReconocedorTexto(motor="pytesseract")
    texto = reconocedor.reconocer(imagen="imagen-de-prueba", idioma="es")

    assert llamadas["lang"] == "spa"
    assert texto == "texto reconocido"  # se recortan espacios extra
