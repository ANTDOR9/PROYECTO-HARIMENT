"""Pruebas del modulo de audio del sistema (hariment.audio.sistema_loopback).

Igual que en test_audio.py, no se abre un dispositivo de audio real ni
se descarga Whisper: solo se prueba el estado del objeto y que reutiliza
correctamente la misma logica/constantes que TranscriptorMicrofono.
"""

from hariment.audio.microfono import (
    DURACION_BLOQUE_SEGUNDOS,
    FRECUENCIA_MUESTREO,
    UMBRAL_SILENCIO,
)
from hariment.audio.sistema_loopback import (
    DispositivoLoopbackNoDisponibleError,
    TranscriptorAudioSistema,
)


def test_transcriptor_sistema_no_esta_escuchando_al_crearse():
    transcriptor = TranscriptorAudioSistema(modelo="tiny")
    assert transcriptor.esta_escuchando is False


def test_transcriptor_sistema_reutiliza_constantes_de_microfono():
    """Ambas fuentes (microfono y sistema) deben compartir la misma
    frecuencia de muestreo, tamaño de bloque y umbral de silencio, para
    que el resto del pipeline (Whisper, traductor) las trate igual."""
    import hariment.audio.sistema_loopback as modulo

    assert modulo.FRECUENCIA_MUESTREO == FRECUENCIA_MUESTREO
    assert modulo.UMBRAL_SILENCIO == UMBRAL_SILENCIO
    assert modulo.DURACION_BLOQUE_SEGUNDOS == DURACION_BLOQUE_SEGUNDOS


def test_detener_sin_haber_iniciado_no_falla():
    transcriptor = TranscriptorAudioSistema(modelo="tiny")
    transcriptor.detener()
    assert transcriptor.esta_escuchando is False


def test_idioma_none_permite_deteccion_automatica():
    """El audio del sistema puede venir en cualquier idioma, a diferencia
    del microfono donde el usuario suele hablar siempre el mismo."""
    transcriptor = TranscriptorAudioSistema(idioma=None, modelo="tiny")
    assert transcriptor.idioma is None


def test_error_dispositivo_no_disponible_es_una_excepcion_propia():
    assert issubclass(DispositivoLoopbackNoDisponibleError, Exception)
