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

import logging
import queue
import threading
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
from hariment.ocr.captura_pantalla import capturar_pantalla, seleccionar_region_pantalla
from hariment.ocr.reconocimiento_texto import ReconocedorTexto
from hariment.translation.traductor import Traductor

# Valores por defecto (alineados con assets/config/settings.example.json).
# La Etapa 5 los hara configurables desde la propia interfaz.
IDIOMA_ORIGEN_POR_DEFECTO = "es"
IDIOMA_DESTINO_POR_DEFECTO = "en"
MODELO_WHISPER_POR_DEFECTO = "small"

COLOR_FONDO_SUBTITULO = "#000000"
COLOR_TEXTO_SUBTITULO = "#FFFFFF"
TAMANO_FUENTE_SUBTITULO = 20

logger = logging.getLogger(__name__)


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

        motor_ocr = self.configuracion.get("ocr", {}).get("motor", "pytesseract")
        self.reconocedor_texto = ReconocedorTexto(motor=motor_ocr)

        # Region de pantalla (x, y, ancho, alto) elegida por el usuario para
        # el OCR. Si es None, se captura la pantalla completa (comportamiento
        # por defecto).
        self._region_captura = None

        self._construir_ventana()
        self._aplicar_estilo_subtitulo(self.configuracion.get("subtitulos", {}))
        self._actualizar_etiqueta_idiomas()
        self._programar_revision_de_cola()

        self._atajo_captura = self.configuracion.get("ocr", {}).get("atajo_captura", "<f9>")
        self._listener_atajo = None
        self._iniciar_atajo_global_captura()

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
        self.etiqueta_idiomas.pack(side="left", padx=(0, 5))

        self.boton_invertir_idiomas = self._boton(
            marco, texto="🔁", comando=self._invertir_idiomas
        )
        self.boton_invertir_idiomas.pack(side="left", padx=(0, 20))

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

        self.boton_capturar_pantalla = self._boton(
            marco, texto="📷 Traducir pantalla", comando=self._capturar_y_traducir_pantalla
        )
        self.boton_capturar_pantalla.pack(side="left", padx=(0, 5))

        self.boton_elegir_region = self._boton(
            marco, texto="🖼 Elegir área", comando=self._elegir_region_captura
        )
        self.boton_elegir_region.pack(side="left", padx=(0, 20))

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
                logger.warning("Dispositivo de loopback no disponible: %s", error)
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
                logger.warning("Dispositivo de loopback no disponible: %s", error)
                self._actualizar_estado(escuchando=False)
                self.etiqueta_subtitulo.configure(text=str(error))

    def _capturar_y_traducir_pantalla(self) -> None:
        """Toma una captura de pantalla, reconoce el texto (OCR) y lo
        traduce, reutilizando el mismo overlay de subtitulos e historial
        que usan el microfono y el audio del sistema."""
        self.boton_capturar_pantalla.configure(state="disabled")
        self.etiqueta_subtitulo.configure(text="Reconociendo texto en pantalla…")
        # Se ejecuta en un hilo aparte: el OCR (y, con TrOCR, un modelo de
        # transformers) puede tardar y no debe congelar la ventana.
        threading.Thread(target=self._ejecutar_captura_en_hilo, daemon=True).start()

    def _elegir_region_captura(self) -> None:
        """Deja que el usuario dibuje con el mouse la zona exacta de la
        pantalla que se quiere capturar (por ejemplo, la caja de chat de
        un juego), en vez de capturar la pantalla completa cada vez.

        Capturar solo esa zona mejora mucho la calidad del OCR: evita que
        se mezcle texto de la propia ventana de HARIMENT, del juego, del
        escritorio, etc. en una sola imagen ruidosa.
        """
        # Se minimiza la ventana un instante para que no aparezca ella misma
        # dentro de la captura de referencia que ve el usuario al seleccionar.
        self.ventana.iconify()
        self.ventana.after(200, self._mostrar_selector_de_region)

    def _mostrar_selector_de_region(self) -> None:
        region = seleccionar_region_pantalla(self.ventana)
        self.ventana.deiconify()
        if region is not None:
            self._region_captura = region
            self.etiqueta_subtitulo.configure(
                text=f"Área de captura configurada ({region[2]}x{region[3]} px). "
                "Usa '📷 Traducir pantalla' para traducir esa zona."
            )
            self.boton_elegir_region.configure(text="🖼 Área elegida ✓")
        # Si el usuario cancelo (Esc), se mantiene la region anterior (o
        # ninguna, si nunca eligio una) sin mostrar ningun error.

    def _ejecutar_captura_en_hilo(self) -> None:
        """Corre en un hilo aparte para no congelar la ventana mientras se
        captura la pantalla y se reconoce el texto (OCR)."""
        try:
            imagen = capturar_pantalla(region=self._region_captura)
            texto = self.reconocedor_texto.reconocer(imagen, idioma=self.traductor.idioma_origen)
        except Exception as error:  # se informa el error en vez de dejar la app colgada
            logger.exception("Fallo la captura/reconocimiento de pantalla")
            mensaje = f"No se pudo capturar/reconocer la pantalla: {error}"
            self.ventana.after(0, lambda: self.etiqueta_subtitulo.configure(text=mensaje))
            return
        finally:
            self.ventana.after(0, lambda: self.boton_capturar_pantalla.configure(state="normal"))

        if texto:
            segmento = SegmentoTranscrito(texto=texto, idioma_detectado=self.traductor.idioma_origen)
            self._cola_eventos.put(segmento)  # se traduce/muestra en el hilo principal via la cola
        else:
            mensaje = "No se detectó texto en pantalla."
            self.ventana.after(0, lambda: self.etiqueta_subtitulo.configure(text=mensaje))

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

    def _invertir_idiomas(self) -> None:
        """Intercambia idioma de origen y destino (ej. es→en pasa a en→es).

        Es util sobre todo para el OCR de pantalla: para hablar por el
        microfono normalmente se usa es→en, pero para leer texto en
        ingles (subtitulos, chats de un juego, etc.) y verlo en español
        hace falta el par contrario. En vez de entrar a Configuración
        cada vez, este boton lo cambia con un clic.
        """
        nuevo_origen, nuevo_destino = self.traductor.idioma_destino, self.traductor.idioma_origen
        self.traductor.cambiar_idiomas(nuevo_origen, nuevo_destino)
        self.transcriptor.idioma = nuevo_origen

        self.configuracion["idioma_origen"] = nuevo_origen
        self.configuracion["idioma_destino"] = nuevo_destino
        self.gestor_configuracion.guardar(self.configuracion)

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

    def _iniciar_atajo_global_captura(self) -> None:
        """Registra una tecla rapida global (por defecto F9) para disparar
        '📷 Traducir pantalla' sin importar que ventana tenga el foco.

        Esto es clave para usarlo mientras se juega: no hace falta
        minimizar el juego ni cambiar de ventana para hacer clic en el
        boton, algo que en juegos en pantalla completa/ventana sin
        bordes es muy incomodo o directamente imposible.

        Usa `pynput`, que engancha el teclado a nivel de sistema (no
        requiere permisos de administrador en Windows). Si la libreria
        no esta instalada, la app sigue funcionando normalmente: solo
        no habra atajo global, y se avisa una vez en el historial.
        """
        try:
            from pynput import keyboard as pynput_keyboard
        except ImportError:
            logger.warning(
                "pynput no esta instalado: el atajo global de captura (%s) "
                "no estara disponible. Instalalo con 'pip install pynput' "
                "para activarlo.",
                self._atajo_captura,
            )
            return

        def _al_presionar_atajo():
            # El listener de pynput corre en su propio hilo del sistema
            # operativo; hay que pasar el trabajo al hilo principal de
            # tkinter con .after(0, ...) para no tocar la interfaz desde
            # fuera de ese hilo.
            self.ventana.after(0, self._capturar_y_traducir_pantalla)

        try:
            self._listener_atajo = pynput_keyboard.GlobalHotKeys(
                {self._atajo_captura: _al_presionar_atajo}
            )
            self._listener_atajo.start()
            logger.info("Atajo global de captura activado: %s", self._atajo_captura)
        except Exception:
            logger.exception(
                "No se pudo activar el atajo global de captura (%s)", self._atajo_captura
            )
            self._listener_atajo = None

    def _al_cerrar_ventana(self) -> None:
        self.transcriptor.detener()
        if self._listener_atajo is not None:
            self._listener_atajo.stop()
        self.ventana.destroy()

    def ejecutar(self) -> None:
        self.ventana.mainloop()


def main() -> None:
    app = AplicacionHariment()
    app.ejecutar()


if __name__ == "__main__":
    main()
