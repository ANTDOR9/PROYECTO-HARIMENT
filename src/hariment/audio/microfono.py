"""
Captura y transcripcion de voz por microfono, usando `openai-whisper`.

Estrategia usada (deteccion de voz por energia + segmentacion):

1. Se abre un stream continuo de audio desde el microfono.
2. Se mide la energia (volumen) de cada bloque pequeño de audio para
   decidir si la persona esta hablando o hay silencio.
3. Mientras hay voz, los bloques se acumulan en un buffer.
4. Cuando se detecta suficiente silencio despues de haber hablado, se
   considera cerrada una "frase" y ese buffer se envia a Whisper para
   transcribirse.

Esto evita transcribir audio vacio constantemente y da una experiencia
de subtitulos "en tiempo real" razonable sin depender de librerias de
deteccion de voz (VAD) mas pesadas; se puede mejorar mas adelante.

Uso basico:

    from hariment.audio.microfono import TranscriptorMicrofono

    def al_transcribir(texto):
        print("Dijiste:", texto)

    transcriptor = TranscriptorMicrofono(idioma="es", al_transcribir=al_transcribir)
    transcriptor.iniciar()
    ...
    transcriptor.detener()
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

FRECUENCIA_MUESTREO = 16_000  # Hz, la que espera Whisper
DURACION_BLOQUE_SEGUNDOS = 0.5
UMBRAL_SILENCIO = 0.010  # energia RMS por debajo de esto se considera silencio
SEGUNDOS_SILENCIO_PARA_CERRAR_FRASE = 0.8
DURACION_MAXIMA_FRASE_SEGUNDOS = 15


@dataclass
class SegmentoTranscrito:
    """Resultado de transcribir un segmento de audio hablado."""

    texto: str
    idioma_detectado: Optional[str] = None


class TranscriptorMicrofono:
    """Escucha el microfono en un hilo aparte y transcribe frase por frase con Whisper."""

    def __init__(
        self,
        idioma: Optional[str] = "es",
        modelo: str = "small",
        al_transcribir: Optional[Callable[[SegmentoTranscrito], None]] = None,
        dispositivo_entrada: Optional[int] = None,
    ) -> None:
        """
        Args:
            idioma: codigo de idioma que se le sugiere a Whisper (ej. "es").
                Si es None, Whisper intenta detectar el idioma automaticamente.
            modelo: tamaño del modelo Whisper ("tiny", "base", "small", "medium", "large").
                Modelos mas grandes son mas precisos pero mas lentos.
            al_transcribir: funcion callback que se llama con cada SegmentoTranscrito
                apenas Whisper termina de procesar una frase.
            dispositivo_entrada: indice del dispositivo de microfono a usar
                (None = dispositivo por defecto del sistema).
        """
        self.idioma = idioma
        self.nombre_modelo = modelo
        self.al_transcribir = al_transcribir
        self.dispositivo_entrada = dispositivo_entrada

        self._modelo_whisper = None
        self._hilo: Optional[threading.Thread] = None
        self._escuchando = threading.Event()
        self._cola_audio: "queue.Queue[np.ndarray]" = queue.Queue()

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def iniciar(self) -> None:
        """Empieza a escuchar el microfono en segundo plano."""
        if self._escuchando.is_set():
            return  # ya esta escuchando

        self._cargar_modelo_si_hace_falta()
        self._escuchando.set()
        self._hilo = threading.Thread(target=self._bucle_escucha, daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        """Detiene la escucha del microfono."""
        self._escuchando.clear()
        if self._hilo is not None:
            self._hilo.join(timeout=2)
            self._hilo = None

    @property
    def esta_escuchando(self) -> bool:
        return self._escuchando.is_set()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _cargar_modelo_si_hace_falta(self) -> None:
        if self._modelo_whisper is None:
            import whisper  # import perezoso: openai-whisper es pesado de cargar

            self._modelo_whisper = whisper.load_model(self.nombre_modelo)

    def _bucle_escucha(self) -> None:
        import sounddevice as sd

        buffer_frase: list[np.ndarray] = []
        segundos_hablando = 0.0
        segundos_en_silencio = 0.0

        def callback_audio(indata, frames, tiempo_info, status):
            self._cola_audio.put(indata.copy())

        tamano_bloque = int(FRECUENCIA_MUESTREO * DURACION_BLOQUE_SEGUNDOS)

        with sd.InputStream(
            samplerate=FRECUENCIA_MUESTREO,
            channels=1,
            dtype="float32",
            blocksize=tamano_bloque,
            device=self.dispositivo_entrada,
            callback=callback_audio,
        ):
            while self._escuchando.is_set():
                try:
                    bloque = self._cola_audio.get(timeout=0.2)
                except queue.Empty:
                    continue

                bloque = bloque.flatten()
                energia = float(np.sqrt(np.mean(bloque**2)))
                hay_voz = energia > UMBRAL_SILENCIO

                if hay_voz:
                    buffer_frase.append(bloque)
                    segundos_hablando += DURACION_BLOQUE_SEGUNDOS
                    segundos_en_silencio = 0.0
                elif buffer_frase:
                    # Hubo voz antes; contamos este silencio para decidir si ya cerro la frase.
                    buffer_frase.append(bloque)
                    segundos_en_silencio += DURACION_BLOQUE_SEGUNDOS

                frase_lista_por_silencio = (
                    buffer_frase and segundos_en_silencio >= SEGUNDOS_SILENCIO_PARA_CERRAR_FRASE
                )
                frase_lista_por_duracion_maxima = (
                    segundos_hablando >= DURACION_MAXIMA_FRASE_SEGUNDOS
                )

                if frase_lista_por_silencio or frase_lista_por_duracion_maxima:
                    audio_frase = np.concatenate(buffer_frase)
                    self._transcribir_y_notificar(audio_frase)
                    buffer_frase = []
                    segundos_hablando = 0.0
                    segundos_en_silencio = 0.0

    def _transcribir_y_notificar(self, audio: np.ndarray) -> None:
        resultado = self._modelo_whisper.transcribe(
            audio,
            language=self.idioma,
            fp16=False,
        )
        texto = (resultado.get("text") or "").strip()
        if not texto:
            return

        segmento = SegmentoTranscrito(
            texto=texto,
            idioma_detectado=resultado.get("language"),
        )
        if self.al_transcribir is not None:
            self.al_transcribir(segmento)


if __name__ == "__main__":
    # Demo por consola: transcribe y traduce en tiempo real.
    #   python -m hariment.audio.microfono
    from hariment.translation.traductor import Traductor

    traductor = Traductor(idioma_origen="es", idioma_destino="en")

    def mostrar_subtitulo(segmento: SegmentoTranscrito) -> None:
        resultado = traductor.traducir(segmento.texto)
        print(f"ES: {resultado.texto_original}")
        print(f"EN: {resultado.texto_traducido}")
        print("-" * 40)

    transcriptor = TranscriptorMicrofono(idioma="es", modelo="small", al_transcribir=mostrar_subtitulo)
    print("Escuchando microfono... (Ctrl+C para detener)")
    transcriptor.iniciar()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nDeteniendo...")
        transcriptor.detener()
