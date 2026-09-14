"""Pruebas del modulo de captura/transcripcion de microfono (hariment.audio.microfono).

Estas pruebas no abren un microfono real ni descargan el modelo Whisper:
solo verifican la logica de deteccion de energia/silencio y el estado
del objeto, para poder correr en cualquier entorno (incluido CI).
"""

import numpy as np
import pytest

from hariment.audio.microfono import (
    FRECUENCIA_MUESTREO,
    UMBRAL_SILENCIO,
    SegmentoTranscrito,
    TranscriptorMicrofono,
)


def test_transcriptor_no_esta_escuchando_al_crearse():
    transcriptor = TranscriptorMicrofono(idioma="es", modelo="tiny")
    assert transcriptor.esta_escuchando is False


def test_bloque_de_silencio_tiene_energia_bajo_el_umbral():
    bloque_silencio = np.zeros(int(FRECUENCIA_MUESTREO * 0.5), dtype="float32")
    energia = float(np.sqrt(np.mean(bloque_silencio**2)))
    assert energia < UMBRAL_SILENCIO


def test_bloque_con_tono_supera_el_umbral_de_silencio():
    duracion = 0.5
    t = np.linspace(0, duracion, int(FRECUENCIA_MUESTREO * duracion), dtype="float32")
    tono = 0.5 * np.sin(2 * np.pi * 440 * t)  # tono audible simulando voz
    energia = float(np.sqrt(np.mean(tono**2)))
    assert energia > UMBRAL_SILENCIO


def test_segmento_transcrito_guarda_texto_e_idioma():
    segmento = SegmentoTranscrito(texto="hola mundo", idioma_detectado="es")
    assert segmento.texto == "hola mundo"
    assert segmento.idioma_detectado == "es"


def test_detener_sin_haber_iniciado_no_falla():
    transcriptor = TranscriptorMicrofono(idioma="es", modelo="tiny")
    transcriptor.detener()  # no deberia lanzar excepcion
    assert transcriptor.esta_escuchando is False
