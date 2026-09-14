"""
Interfaz grafica minima de PROYECTO HARIMENT.

Ventana de escritorio (customtkinter, con fallback a tkinter puro si
customtkinter no esta instalado) que:

- Muestra un boton para Iniciar/Detener la escucha del microfono.
- Muestra el subtitulo actual (texto traducido) en una barra tipo overlay.
- Mantiene un historial simple de lo transcrito/traducido.

La configuracion fina de estilo de subtitulos e idiomas se agrega en la
Etapa 5 (`configuracion.py`); esta version usa valores por defecto
razonables para validar que todo el flujo funciona de punta a punta:

    microfono -> Whisper -> Traductor -> subtitulo en pantalla

Los modulos de audio (Whisper) corren en un hilo aparte (ver
`hariment.audio.microfono.TranscriptorMicrofono`) y se comunican con la
interfaz mediante una cola thread-safe, para no bloquear la ventana
mientras se transcribe o traduce.
"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import scrolledtext

try:
    import customtkinter as ctk

    _TIENE_CUSTOMTKINTER = True
except ImportError:  # pragma: no cover - depende de si esta instalado
    _TIENE_CUSTOMTKINTER = False

from hariment.audio.microfono import SegmentoTranscrito, TranscriptorMicrofono
from hariment.audio.sistema_loopback import (
    DispositivoLoopbackNoDisponibleError,
    TranscriptorAudioSistema,
)
from hariment.gui.configuracion import GestorConfiguracion, crear_ventana_configuracion
from hariment.translation.traductor import Traductor

# Valores por defecto (alineados con assets/config/settings.example.json).
# La Etapa 5 los hara configurables desde la propia interfaz.
IDIOMA_ORIGEN_POR_DEFECTO = "es"
IDIOMA_DESTINO_POR_DEFECTO = "en"
MODELO_WHISPER_POR_DEFECTO = "small"

COLOR_FONDO_SUBTITULO = "#000000"
COLOR_TEXTO_SUBTITULO = "#FFFFFF"
TAMANO_FUENTE_SUBTITULO = 20


class AplicacionHariment:
    """Ventana principal de PROYECTO HARIMENT."""

    def __init__(self) -> None:
        self._cola_eventos: "queue.Queue[SegmentoTranscrito]" = queue.Queue()

        self.gestor_configuracion = GestorConfiguracion()
        self.configuracion = self.gestor_configuracion.cargar()

        idioma_origen = self.configuracion.get("idioma_origen", IDIOMA_ORIGEN_POR_DEFECTO)
        idioma_destino = self.configuracion.get("idioma_destino", IDIOMA_DESTINO_POR_DEFECTO)

        self.traductor = Traductor(idioma_origen=idioma_origen, idioma_destino=idioma_destino)

        self._fuente_entrada = self.configuracion.get("fuente_entrada", "microfono")
        self.transcriptor = self._crear_transcriptor(self._fuente_entrada, idioma_origen)

        self._construir_ventana()
        self._aplicar_estilo_subtitulo(self.configuracion.get("subtitulos", {}))
        self._actualizar_etiqueta_idiomas()
        self._programar_revision_de_cola()

    # ------------------------------------------------------------------
    # Construccion de la interfaz
    # ------------------------------------------------------------------

    def _construir_ventana(self) -> None:
        if _TIENE_CUSTOMTKINTER:
            ctk.set_appearance_mode("dark")
            self.ventana = ctk.CTk()
        else:
            self.ventana = tk.Tk()

        self.ventana.title("PROYECTO HARIMENT — Traductor en tiempo real")
        self.ventana.geometry("720x480")
        self.ventana.protocol("WM_DELETE_WINDOW", self._al_cerrar_ventana)

        self._construir_barra_superior()
        self._construir_historial()
        self._construir_barra_subtitulo()

    def _construir_barra_superior(self) -> None:
        marco = self._marco(self.ventana)
        marco.pack(fill="x", padx=10, pady=10)

        self.etiqueta_idiomas = self._etiqueta(
            marco,
            texto=f"{IDIOMA_ORIGEN_POR_DEFECTO.upper()} → {IDIOMA_DESTINO_POR_DEFECTO.upper()}",
        )
        self.etiqueta_idiomas.pack(side="left", padx=(0, 20))

        self.boton_iniciar_detener = self._boton(
            marco, texto="▶ Iniciar", comando=self._alternar_escucha
        )
        self.boton_iniciar_detener.pack(side="left")

        self.etiqueta_estado = self._etiqueta(marco, texto="● Detenido", color="#AAAAAA")
        self.etiqueta_estado.pack(side="right")

        self.boton_configuracion = self._boton(
            marco, texto="⚙ Configuración", comando=self._abrir_configuracion
        )
        self.boton_configuracion.pack(side="right", padx=(0, 20))

        self.variable_fuente = tk.StringVar(value=self._fuente_entrada)
        marco_fuente = tk.Frame(marco, bg="#2B2B2B") if not _TIENE_CUSTOMTKINTER else self._marco(marco)
        marco_fuente.pack(side="left", padx=(0, 20))
        for etiqueta, valor in (("🎤 Micrófono", "microfono"), ("🔊 Audio del sistema", "sistema")):
            tk.Radiobutton(
                marco_fuente,
                text=etiqueta,
                variable=self.variable_fuente,
                value=valor,
                command=self._cambiar_fuente_entrada,
                bg="#2B2B2B",
                fg="#FFFFFF",
                selectcolor="#2B2B2B",
                activebackground="#2B2B2B",
                activeforeground="#FFFFFF",
            ).pack(side="left")

    def _construir_historial(self) -> None:
        self.area_historial = scrolledtext.ScrolledText(
            self.ventana,
            wrap="word",
            height=15,
            bg="#1E1E1E",
            fg="#DDDDDD",
            insertbackground="#DDDDDD",
            borderwidth=0,
        )
        self.area_historial.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.area_historial.configure(state="disabled")

    def _construir_barra_subtitulo(self) -> None:
        """Barra inferior tipo 'overlay' que simula donde iran los subtitulos.

        En esta etapa vive dentro de la misma ventana; una version futura
        podra separarla en una ventana flotante sin bordes, siempre
        configurable (posicion, tamaño, color) segun la Etapa 5.
        """
        self.marco_subtitulo = tk.Frame(self.ventana, bg=COLOR_FONDO_SUBTITULO, height=80)
        self.marco_subtitulo.pack(fill="x", side="bottom")
        self.marco_subtitulo.pack_propagate(False)

        self.etiqueta_subtitulo = tk.Label(
            self.marco_subtitulo,
            text="Presiona “Iniciar” y habla en español…",
            bg=COLOR_FONDO_SUBTITULO,
            fg=COLOR_TEXTO_SUBTITULO,
            font=("Segoe UI", TAMANO_FUENTE_SUBTITULO),
            wraplength=680,
            justify="center",
        )
        self.etiqueta_subtitulo.pack(expand=True)

    # Pequeños helpers para no repetir el if/else de customtkinter en cada widget.

    def _marco(self, padre):
        return ctk.CTkFrame(padre) if _TIENE_CUSTOMTKINTER else tk.Frame(padre, bg="#2B2B2B")

    def _etiqueta(self, padre, texto: str, color: str = "#FFFFFF"):
        if _TIENE_CUSTOMTKINTER:
            return ctk.CTkLabel(padre, text=texto)
        return tk.Label(padre, text=texto, bg="#2B2B2B", fg=color)

    def _boton(self, padre, texto: str, comando):
        if _TIENE_CUSTOMTKINTER:
            return ctk.CTkButton(padre, text=texto, command=comando)
        return tk.Button(padre, text=texto, command=comando)

    # ------------------------------------------------------------------
    # Logica de la aplicacion
    # ------------------------------------------------------------------

    def _alternar_escucha(self) -> None:
        if self.transcriptor.esta_escuchando:
            self.transcriptor.detener()
            self._actualizar_estado(escuchando=False)
        else:
            try:
                self.transcriptor.iniciar()
                self._actualizar_estado(escuchando=True)
            except DispositivoLoopbackNoDisponibleError as error:
                self.etiqueta_subtitulo.configure(text=str(error))

    def _actualizar_estado(self, escuchando: bool) -> None:
        if escuchando:
            texto_estado, color_estado = "● Escuchando", "#4CAF50"
            texto_boton = "■ Detener"
        else:
            texto_estado, color_estado = "● Detenido", "#AAAAAA"
            texto_boton = "▶ Iniciar"

        if _TIENE_CUSTOMTKINTER:
            self.etiqueta_estado.configure(text=texto_estado)
        else:
            self.etiqueta_estado.configure(text=texto_estado, fg=color_estado)

        self.boton_iniciar_detener.configure(text=texto_boton)

    def _programar_revision_de_cola(self) -> None:
        """Revisa periodicamente si llegaron nuevas transcripciones desde el
        hilo de audio, y actualiza la interfaz en el hilo principal (Tk no es
        thread-safe: nunca se debe tocar la interfaz desde otro hilo)."""
        try:
            while True:
                segmento = self._cola_eventos.get_nowait()
                self._procesar_segmento(segmento)
        except queue.Empty:
            pass
        finally:
            self.ventana.after(150, self._programar_revision_de_cola)

    def _procesar_segmento(self, segmento: SegmentoTranscrito) -> None:
        resultado = self.traductor.traducir(segmento.texto)

        self.etiqueta_subtitulo.configure(text=resultado.texto_traducido)

        self.area_historial.configure(state="normal")
        self.area_historial.insert(
            "end", f"ES: {resultado.texto_original}\nEN: {resultado.texto_traducido}\n\n"
        )
        self.area_historial.see("end")
        self.area_historial.configure(state="disabled")

    def _crear_transcriptor(self, fuente: str, idioma_origen: str):
        """Crea el transcriptor correspondiente a la fuente elegida
        (microfono o audio del sistema), ambos con la misma interfaz
        (iniciar/detener/esta_escuchando) para que el resto de la app
        no necesite saber cual esta usando."""
        if fuente == "sistema":
            return TranscriptorAudioSistema(
                idioma=idioma_origen,
                modelo=MODELO_WHISPER_POR_DEFECTO,
                al_transcribir=self._cola_eventos.put,
            )
        return TranscriptorMicrofono(
            idioma=idioma_origen,
            modelo=MODELO_WHISPER_POR_DEFECTO,
            al_transcribir=self._cola_eventos.put,
        )

    def _cambiar_fuente_entrada(self) -> None:
        """Cambia entre escuchar el microfono o el audio del sistema.
        Si estaba escuchando, se detiene la fuente anterior antes de
        cambiar, para no dejar dos hilos de captura corriendo a la vez."""
        estaba_escuchando = self.transcriptor.esta_escuchando
        if estaba_escuchando:
            self.transcriptor.detener()

        self._fuente_entrada = self.variable_fuente.get()
        self.configuracion["fuente_entrada"] = self._fuente_entrada
        self.gestor_configuracion.guardar(self.configuracion)

        self.transcriptor = self._crear_transcriptor(self._fuente_entrada, self.traductor.idioma_origen)

        if estaba_escuchando:
            try:
                self.transcriptor.iniciar()
                self._actualizar_estado(escuchando=True)
            except DispositivoLoopbackNoDisponibleError as error:
                self._actualizar_estado(escuchando=False)
                self.etiqueta_subtitulo.configure(text=str(error))

    def _abrir_configuracion(self) -> None:
        crear_ventana_configuracion(
            self.ventana,
            configuracion_actual=self.configuracion,
            al_guardar=self._aplicar_configuracion,
        )

    def _aplicar_configuracion(self, nueva_configuracion: dict) -> None:
        """Aplica en caliente los cambios hechos en la ventana de configuracion
        y los guarda en disco para la proxima vez que se abra la aplicacion."""
        self.configuracion = nueva_configuracion
        self.gestor_configuracion.guardar(nueva_configuracion)

        idioma_origen = nueva_configuracion.get("idioma_origen", IDIOMA_ORIGEN_POR_DEFECTO)
        idioma_destino = nueva_configuracion.get("idioma_destino", IDIOMA_DESTINO_POR_DEFECTO)

        self.traductor.cambiar_idiomas(idioma_origen, idioma_destino)
        self.transcriptor.idioma = idioma_origen  # se aplica en la proxima frase transcrita

        self._aplicar_estilo_subtitulo(nueva_configuracion.get("subtitulos", {}))
        self._actualizar_etiqueta_idiomas()

    def _aplicar_estilo_subtitulo(self, subtitulos: dict) -> None:
        color_fondo = subtitulos.get("color_fondo", COLOR_FONDO_SUBTITULO)
        color_texto = subtitulos.get("color_texto", COLOR_TEXTO_SUBTITULO)
        tamano_fuente = subtitulos.get("tamano_fuente", TAMANO_FUENTE_SUBTITULO)
        posicion = subtitulos.get("posicion", "inferior")

        self.marco_subtitulo.configure(bg=color_fondo)
        self.etiqueta_subtitulo.configure(
            bg=color_fondo, fg=color_texto, font=("Segoe UI", tamano_fuente)
        )
        self.marco_subtitulo.pack_forget()
        self.marco_subtitulo.pack(fill="x", side="top" if posicion == "superior" else "bottom")

    def _actualizar_etiqueta_idiomas(self) -> None:
        self.etiqueta_idiomas.configure(
            text=f"{self.traductor.idioma_origen.upper()} → {self.traductor.idioma_destino.upper()}"
        )

    def _al_cerrar_ventana(self) -> None:
        self.transcriptor.detener()
        self.ventana.destroy()

    def ejecutar(self) -> None:
        self.ventana.mainloop()


def main() -> None:
    app = AplicacionHariment()
    app.ejecutar()


if __name__ == "__main__":
    main()
