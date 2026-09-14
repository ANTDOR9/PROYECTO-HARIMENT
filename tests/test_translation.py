"""Pruebas del nucleo de traduccion (hariment.translation.traductor).

Las pruebas que requieren descargar un modelo real estan marcadas con
`slow` para poder omitirse en entornos sin conexion a internet o sin las
dependencias pesadas (`transformers`/`torch`) instaladas todavia.
"""

import pytest

from hariment.translation.traductor import (
    IdiomaNoSoportadoError,
    Traductor,
    idiomas_soportados,
)


def test_idiomas_soportados_incluye_es_en():
    pares = idiomas_soportados()
    assert ("es", "en") in pares


def test_idiomas_soportados_incluye_portugues():
    """El portugues fue pedido como idioma prioritario a futuro."""
    pares = idiomas_soportados()
    assert ("es", "pt") in pares or ("en", "pt") in pares


def test_par_idioma_no_soportado_lanza_error():
    traductor = Traductor(idioma_origen="es", idioma_destino="de")
    with pytest.raises(IdiomaNoSoportadoError):
        traductor._nombre_modelo()


def test_traducir_texto_vacio_no_falla():
    traductor = Traductor(idioma_origen="es", idioma_destino="en")
    resultado = traductor.traducir("")
    assert resultado.texto_traducido == ""


def test_cambiar_idiomas_actualiza_par_activo():
    traductor = Traductor(idioma_origen="es", idioma_destino="en")
    traductor.cambiar_idiomas("es", "pt")
    assert traductor.par_idiomas == ("es", "pt")


@pytest.mark.slow
def test_traduccion_real_es_a_en():
    """Requiere descargar el modelo la primera vez (necesita internet)."""
    traductor = Traductor(idioma_origen="es", idioma_destino="en")
    resultado = traductor.traducir("Hola, como estas?")
    assert resultado.texto_traducido
    assert resultado.texto_traducido.lower() != resultado.texto_original.lower()
