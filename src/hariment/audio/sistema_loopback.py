"""
Captura y transcripcion del audio que reproduce el propio sistema
("loopback"): lo que suena por los parlantes (un video, una llamada,
etc.), no lo que capta el microfono.

Se usa la libreria `soundcard`, que expone el audio de salida como si
fuera un dispositivo de grabacion mas ("loopback device") de forma
multiplataforma:

- Windows: usa WASAPI loopback internamente. Es la forma recomendada;
  no requiere instalar un driver de audio virtual aparte.
- Linux (PulseAudio/PipeWire): graba el monitor del dispositivo de
  salida por defecto.
- macOS: requiere un dispositivo de loopback virtual instalado aparte
  (por ejemplo BlackHole), ya que macOS no expone loopback nativo.

La logica de deteccion de voz/silencio y el flujo de transcripcion con
Whisper son identicos a `microfono.py` (Etapa 3); por eso esta clase
reutiliza esas mismas constantes y el mismo patron, cambiando solo
*de donde* viene el audio.

Uso basico:

    from hariment.audio.sistema_loopback import TranscriptorAudioSistema

    def al_transcribir(segmento):
        print("Se escucho en el sistema:", segmento.texto)

    transcriptor = TranscriptorAudioSistema(idioma="en", al_transcribir=al_transcribir)
    transcriptor.iniciar()
    ...
    transcriptor.detener()
"""

from __future__ import annotations

import queue
import threading
from typing import Callable, Optional

import numpy as np

from hariment.audio.microfono import (
    DURACION_BLOQUE_SEGUNDOS,
    DURACION_MAXIMA_FRASE_SEGUNDOS,
    FRECUENCIA_MUESTREO,
    SEGUNDOS_SILENCIO_PARA_CERRAR_FRASE,
    UMBRAL_SILENCIO,
    SegmentoTranscrito,
)


class DispositivoLoopbackNoDisponibleError(Exception):
    """Se lanza cuando no se encuentra un dispositivo de loopback en el sistema."""


class TranscriptorAudioSistema:
    """Escucha el audio de salida del sistema y transcribe frase por frase con Whisper.

    Comparte la misma estrategia de segmentacion por energia/silencio que
    `TranscriptorMicrofono` (Etapa 3); ver ese modulo para el detalle.
    """

    def __init__(
        self,
        idioma: Optional[str] = None,
        modelo: str = "small",
        al_transcribir: Optional[Callable[[SegmentoTranscrito], None]] = None,
        nombre_dispositivo_salida: Optional[str] = None,
    ) -> None:
        """
        Args:
            idioma: codigo de idioma sugerido a Whisper (ej. "en" si estas
                escuchando un video en ingles). None = deteccion automatica,
                util porque el audio del sistema puede venir en cualquier idioma.
            modelo: tamaño del modelo Whisper.
            al_transcribir: callback con cada SegmentoTranscrito.
            nombre_dispositivo_salida: nombre (o parte del nombre) del
                dispositivo de salida a "escuchar en loopback". None usa el
                dispositivo de reproduccion por defecto del sistema.
        """
        self.idioma = idioma
        self.nombre_modelo = modelo
        self.al_transcribir = al_transcribir
        self.nombre_dispositivo_salida = nombre_dispositivo_salida

        self._modelo_whisper = None
        self._hilo: Optional[threading.Thread] = None
        self._escuchando = threading.Event()

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def iniciar(self) -> None:
        if self._escuchando.is_set():
            return

        self._cargar_modelo_si_hace_falta()
        self._escuchando.set()
        self._hilo = threading.Thread(target=self._bucle_escucha, daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        self._escuchando.clear()
        if self._hilo is not None:
            self._hilo.join(timeout=2)
            self._hilo = None

    @property
    def esta_escuchando(self) -> bool:
        return self._escuchando.is_set()

    @staticmethod
    def listar_dispositivos_salida() -> list[str]:
        """Devuelve los nombres de los altavoces/dispositivos de salida
        disponibles, utiles para que la interfaz deje elegir cual escuchar."""
        import soundcard as sc

        return [altavoz.name for altavoz in sc.all_speakers()]

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _cargar_modelo_si_hace_falta(self) -> None:
        if self._modelo_whisper is None:
            import whisper

            self._modelo_whisper = whisper.load_model(self.nombre_modelo)

    def _obtener_microfono_loopback(self):
        import soundcard as sc

        try:
            if self.nombre_dispositivo_salida:
                altavoz = sc.get_speaker(self.nombre_dispositivo_salida)
            else:
                altavoz = sc.default_speaker()
        except Exception as error:  # soundcard lanza distintos tipos segun el SO
            raise DispositivoLoopbackNoDisponibleError(
                "No se encontro un dispositivo de salida para escuchar en loopback. "
                "En macOS se necesita un dispositivo virtual (ej. BlackHole) instalado "
                "aparte, ya que el sistema operativo no expone loopback nativo."
            ) from error

        # En Windows, `soundcard` permite grabar directamente el "microfono
        # loopback" asociado al altavoz; en Linux equivale al "monitor".
        return sc.get_microphone(id=str(altavoz.name), include_loopback=True)

    def _bucle_escucha(self) -> None:
        microfono_loopback = self._obtener_microfono_loopback()
        tamano_bloque = int(FRECUENCIA_MUESTREO * DURACION_BLOQUE_SEGUNDOS)

        buffer_frase: list[np.ndarray] = []
        segundos_hablando = 0.0
        segundos_en_silencio = 0.0

        with microfono_loopback.recorder(samplerate=FRECUENCIA_MUESTREO, channels=1) as grabadora:
            while self._escuchando.is_set():
                bloque = grabadora.record(numframes=tamano_bloque)
                bloque = bloque.flatten().astype("float32")

                energia = float(np.sqrt(np.mean(bloque**2)))
                hay_sonido = energia > UMBRAL_SILENCIO

                if hay_sonido:
                    buffer_frase.append(bloque)
                    segundos_hablando += DURACION_BLOQUE_SEGUNDOS
                    segundos_en_silencio = 0.0
                elif buffer_frase:
                    buffer_frase.append(bloque)
                    segundos_en_silencio += DURACION_BLOQUE_SEGUNDOS

                frase_lista_por_silencio = (
                    buffer_frase and segundos_en_silencio >= SEGUNDOS_SILENCIO_PARA_CERRAR_FRASE
                )
                frase_lista_por_duracion_maxima = segundos_hablando >= DURACION_MAXIMA_FRASE_SEGUNDOS

                if frase_lista_por_silencio or frase_lista_por_duracion_maxima:
                    audio_frase = np.concatenate(buffer_frase)
                    self._transcribir_y_notificar(audio_frase)
                    buffer_frase = []
                    segundos_hablando = 0.0
                    segundos_en_silencio = 0.0

    def _transcribir_y_notificar(self, audio: np.ndarray) -> None:
        idioma_para_whisper = None if self.idioma in (None, "auto") else self.idioma
        resultado = self._modelo_whisper.transcribe(audio, language=idioma_para_whisper, fp16=False)
        texto = (resultado.get("text") or "").strip()
        if not texto:
            return

        segmento = SegmentoTranscrito(texto=texto, idioma_detectado=resultado.get("language"))
        if self.al_transcribir is not None:
            self.al_transcribir(segmento)


if __name__ == "__main__":
    # Demo por consola: transcribe y traduce lo que suena en el sistema.
    #   python -m hariment.audio.sistema_loopback
    import time

    from hariment.translation.traductor import Traductor

    traductor = Traductor(idioma_origen="en", idioma_destino="es")

    def mostrar_subtitulo(segmento: SegmentoTranscrito) -> None:
        resultado = traductor.traducir(segmento.texto)
        print(f"Sistema ({segmento.idioma_detectado}): {resultado.texto_original}")
        print(f"ES: {resultado.texto_traducido}")
        print("-" * 40)

    transcriptor = TranscriptorAudioSistema(idioma=None, modelo="small", al_transcribir=mostrar_subtitulo)
    print("Escuchando el audio del sistema... (Ctrl+C para detener)")
    try:
        transcriptor.iniciar()
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nDeteniendo...")
        transcriptor.detener()
    except DispositivoLoopbackNoDisponibleError as error:
        print(f"Error: {error}")
