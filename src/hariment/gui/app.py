"""
Interfaz grafica de PROYECTO HARIMENT.

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
import sys
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

# ---------------------------------------------------------------------
# Paleta de colores del proyecto: morado + blanco como colores
# primordiales (pedido explicito), con buen contraste entre ellos. El
# resto de tonos (grises/negros de apoyo) son de libre eleccion, elegidos
# para que el morado y el blanco resalten sobre un fondo oscuro neutro.
# ---------------------------------------------------------------------
COLOR_MORADO = "#8B5CF6"          # morado principal (botones, acentos)
COLOR_MORADO_OSCURO = "#6D28D9"   # morado mas oscuro (hover/realces)
COLOR_MORADO_SUAVE = "#C4B5FD"    # morado claro (texto secundario sobre fondo oscuro)
COLOR_BLANCO = "#FFFFFF"          # blanco principal (texto sobre morado/oscuro)
COLOR_FONDO_VENTANA = "#151020"   # fondo general, casi negro con tinte morado
COLOR_FONDO_PANEL = "#221A33"     # paneles/barras (un poco mas claro que el fondo)
COLOR_FONDO_HISTORIAL = "#1B1428" # area de historial
COLOR_BORDE_SUTIL = "#3B2E57"     # separadores/bordes suaves
COLOR_TEXTO_TENUE = "#A9A0C4"     # texto secundario (menos protagonismo)
COLOR_ESTADO_ACTIVO = "#22C55E"   # verde: "escuchando"
COLOR_ESTADO_INACTIVO = "#A9A0C4"

COLOR_FONDO_SUBTITULO = "#000000"
COLOR_TEXTO_SUBTITULO = "#FFFFFF"
TAMANO_FUENTE_SUBTITULO = 20

# Ancho/alto minimos de la ventana: evita que, al achicarla, los botones
# de las barras superiores queden ocultos fuera del area visible (tkinter
# no los "envuelve" automaticamente a otra linea si no caben).
ANCHO_MINIMO_VENTANA = 660
ALTO_MINIMO_VENTANA = 420

logger = logging.getLogger(__name__)


def _configurar_identidad_app_windows() -> None:
    """En Windows, si no se declara un "App User Model ID" propio, la
    barra de tareas agrupa la ventana bajo el icono generico de Python en
    vez del icono de la app (aunque la ventana en si ya lo muestre bien).
    Esto lo corrige; en otros sistemas operativos no hace nada.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Hariment.ProyectoHariment.TraductorTiempoReal"
        )
    except Exception:
        logger.debug("No se pudo fijar el AppUserModelID de Windows", exc_info=True)


class AplicacionHariment:
    """Ventana principal de PROYECTO HARIMENT."""

    def __init__(self) -> None:
        _configurar_identidad_app_windows()

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

        self._atajo_captura = self.configuracion.get("ocr", {}).get("atajo_captura", "<f9>")
        self._listener_atajo = None

        self._construir_ventana()
        self._aplicar_estilo_subtitulo(self.configuracion.get("subtitulos", {}))
        self._actualizar_etiqueta_idiomas()
        self._programar_revision_de_cola()
        self._iniciar_atajo_global_captura()

    # ------------------------------------------------------------------
    # Construccion de la interfaz
    # ------------------------------------------------------------------

    def _construir_ventana(self) -> None:
        if _TIENE_CUSTOMTKINTER:
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("dark-blue")
            self.ventana = ctk.CTk()
        else:
            self.ventana = tk.Tk()

        self.ventana.title("PROYECTO HARIMENT — Traductor en tiempo real")
        self.ventana.geometry("760x540")
        self.ventana.minsize(ANCHO_MINIMO_VENTANA, ALTO_MINIMO_VENTANA)
        self.ventana.configure(bg=COLOR_FONDO_VENTANA)
        self.ventana.protocol("WM_DELETE_WINDOW", self._al_cerrar_ventana)
        self._aplicar_icono_ventana()

        self._construir_barra_superior()
        self._construir_historial()
        self._construir_barra_subtitulo()

    def _cargar_imagen_icono(self):
        """Carga (una sola vez) la imagen del icono de la app como
        `tk.PhotoImage`, y la guarda en `self` para que Tk no la recolecte
        como basura mientras la ventana este abierta (es un error comun:
        si no se guarda una referencia, el icono desaparece o falla)."""
        if getattr(self, "_imagen_icono", None) is not None:
            return self._imagen_icono

        import os

        ruta_icono = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "assets", "icons", "icono_app.png",
        )
        try:
            if os.path.exists(ruta_icono):
                self._imagen_icono = tk.PhotoImage(file=ruta_icono)
                return self._imagen_icono
        except Exception:
            logger.warning("No se pudo cargar la imagen del icono", exc_info=True)
        self._imagen_icono = None
        return None

    def _aplicar_icono_ventana(self, ventana=None) -> None:
        """Pone el icono de HARIMENT en la barra de titulo/barra de tareas
        de la ventana indicada (por defecto, la ventana principal).

        Se usa el PNG (no el .ico) porque tkinter en Windows/Linux/macOS
        lee PNG de forma nativa con `iconphoto`; el .ico solo hace falta
        aparte para el ejecutable empaquetado con PyInstaller (ver
        `scripts/build_windows.py`).
        """
        imagen = self._cargar_imagen_icono()
        if imagen is None:
            return
        objetivo = ventana if ventana is not None else self.ventana
        try:
            objetivo.iconphoto(True, imagen)
        except Exception:
            logger.warning("No se pudo aplicar el icono de la ventana", exc_info=True)

    def _construir_barra_superior(self) -> None:
        """Construye la barra superior en DOS filas (en vez de una sola
        fila muy ancha). Con una sola fila, al achicar la ventana los
        botones de mas a la derecha quedaban fuera del area visible y
        parecian "desaparecer"; repartidos en dos filas mas cortas caben
        comodamente incluso en el ancho minimo de la ventana."""
        contenedor = self._marco(self.ventana, color_fondo=COLOR_FONDO_PANEL)
        contenedor.pack(fill="x")

        fila_1 = self._marco(contenedor, color_fondo=COLOR_FONDO_PANEL)
        fila_1.pack(fill="x", padx=10, pady=(10, 5))

        fila_2 = self._marco(contenedor, color_fondo=COLOR_FONDO_PANEL)
        fila_2.pack(fill="x", padx=10, pady=(0, 10))

        # --- Fila 1: idiomas, iniciar/detener, estado, configuracion ---
        self.etiqueta_idiomas = self._etiqueta(
            fila_1,
            texto=f"{IDIOMA_ORIGEN_POR_DEFECTO.upper()} → {IDIOMA_DESTINO_POR_DEFECTO.upper()}",
            color=COLOR_MORADO_SUAVE,
            negrita=True,
        )
        self.etiqueta_idiomas.pack(side="left", padx=(0, 4))

        self.boton_invertir_idiomas = self._boton(
            fila_1, texto="🔁", comando=self._invertir_idiomas, ancho=36
        )
        self.boton_invertir_idiomas.pack(side="left", padx=(0, 14))

        self.boton_iniciar_detener = self._boton(
            fila_1, texto="▶ Iniciar", comando=self._alternar_escucha, primario=True
        )
        self.boton_iniciar_detener.pack(side="left")

        self.boton_configuracion = self._boton(
            fila_1, texto="⚙ Configuración", comando=self._abrir_configuracion
        )
        self.boton_configuracion.pack(side="right")

        self.etiqueta_estado = self._etiqueta(
            fila_1, texto="● Detenido", color=COLOR_ESTADO_INACTIVO, negrita=True
        )
        self.etiqueta_estado.pack(side="right", padx=(0, 16))

        # --- Fila 2: fuente de entrada, captura de pantalla, atajo ---
        self.variable_fuente = tk.StringVar(value=self._fuente_entrada)
        marco_fuente = self._marco(fila_2, color_fondo=COLOR_FONDO_PANEL)
        marco_fuente.pack(side="left", padx=(0, 14))
        for etiqueta, valor in (("🎤 Micrófono", "microfono"), ("🔊 Audio del sistema", "sistema")):
            tk.Radiobutton(
                marco_fuente,
                text=etiqueta,
                variable=self.variable_fuente,
                value=valor,
                command=self._cambiar_fuente_entrada,
                bg=COLOR_FONDO_PANEL,
                fg=COLOR_BLANCO,
                selectcolor=COLOR_FONDO_PANEL,
                activebackground=COLOR_FONDO_PANEL,
                activeforeground=COLOR_MORADO_SUAVE,
                highlightthickness=0,
                borderwidth=0,
            ).pack(side="left")

        self.boton_capturar_pantalla = self._boton(
            fila_2, texto="📷 Traducir pantalla", comando=self._capturar_y_traducir_pantalla
        )
        self.boton_capturar_pantalla.pack(side="left", padx=(0, 6))

        self.boton_elegir_region = self._boton(
            fila_2, texto="🖼 Elegir área", comando=self._elegir_region_captura
        )
        self.boton_elegir_region.pack(side="left", padx=(0, 14))

        # Aviso permanente (tipo "chip") del atajo de teclado global
        # configurado actualmente, para que el usuario no lo olvide ni
        # tenga que adivinarlo mientras juega.
        self.etiqueta_atajo = self._chip_atajo(fila_2)
        self.etiqueta_atajo.pack(side="right")

    def _chip_atajo(self, padre):
        """Crea la pequeña "pastilla" que muestra el atajo de captura
        actual (ej. "⌨ Captura: F9"), estilo notificacion permanente."""
        texto_tecla = self._atajo_captura.strip("<>").upper()
        marco = tk.Frame(padre, bg=COLOR_MORADO_OSCURO, highlightthickness=0)
        tk.Label(
            marco,
            text=f"⌨ Captura: {texto_tecla}",
            bg=COLOR_MORADO_OSCURO,
            fg=COLOR_BLANCO,
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=4,
        ).pack()
        return marco

    def _actualizar_chip_atajo(self) -> None:
        """Reconstruye el chip del atajo (ej. tras cambiar la tecla en
        Configuración), sin tener que reconstruir toda la barra."""
        if not hasattr(self, "etiqueta_atajo"):
            return
        padre = self.etiqueta_atajo.master
        self.etiqueta_atajo.destroy()
        self.etiqueta_atajo = self._chip_atajo(padre)
        self.etiqueta_atajo.pack(side="right")

    def _construir_historial(self) -> None:
        self.area_historial = scrolledtext.ScrolledText(
            self.ventana,
            wrap="word",
            height=15,
            bg=COLOR_FONDO_HISTORIAL,
            fg=COLOR_BLANCO,
            insertbackground=COLOR_BLANCO,
            borderwidth=0,
            padx=12,
            pady=10,
            spacing1=2,
            spacing3=10,  # espacio despues de cada parrafo: separa entradas
        )
        self.area_historial.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Tags de formato: distinguen claramente la linea del idioma de
        # origen (lo que se dijo/leyo) de la linea traducida, en vez de
        # mostrar ambas mezcladas con el mismo color y tamaño.
        self.area_historial.tag_configure(
            "etiqueta_origen", foreground=COLOR_MORADO_SUAVE, font=("Segoe UI", 9, "bold")
        )
        self.area_historial.tag_configure(
            "etiqueta_destino", foreground=COLOR_BLANCO, font=("Segoe UI", 9, "bold")
        )
        self.area_historial.tag_configure(
            "texto_origen", foreground=COLOR_TEXTO_TENUE, font=("Segoe UI", 11)
        )
        self.area_historial.tag_configure(
            "texto_destino", foreground=COLOR_BLANCO, font=("Segoe UI", 12, "bold")
        )
        self.area_historial.tag_configure(
            "separador", foreground=COLOR_BORDE_SUTIL, font=("Segoe UI", 8)
        )

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

        texto_tecla = self._atajo_captura.strip("<>").upper()
        self.etiqueta_subtitulo = tk.Label(
            self.marco_subtitulo,
            text=(
                "Presiona “Iniciar” y habla en español…  "
                f"(atajo de captura de pantalla: {texto_tecla})"
            ),
            bg=COLOR_FONDO_SUBTITULO,
            fg=COLOR_TEXTO_SUBTITULO,
            font=("Segoe UI", TAMANO_FUENTE_SUBTITULO),
            wraplength=680,
            justify="center",
        )
        self.etiqueta_subtitulo.pack(expand=True)

    # Pequeños helpers para no repetir el if/else de customtkinter en cada widget.

    def _marco(self, padre, color_fondo: str = COLOR_FONDO_VENTANA):
        if _TIENE_CUSTOMTKINTER:
            return ctk.CTkFrame(padre, fg_color=color_fondo)
        return tk.Frame(padre, bg=color_fondo)

    def _etiqueta(self, padre, texto: str, color: str = COLOR_BLANCO, negrita: bool = False):
        if _TIENE_CUSTOMTKINTER:
            fuente = ("Segoe UI", 12, "bold") if negrita else None
            return ctk.CTkLabel(padre, text=texto, text_color=color, font=fuente)
        fuente = ("Segoe UI", 10, "bold") if negrita else ("Segoe UI", 10)
        return tk.Label(padre, text=texto, bg=COLOR_FONDO_PANEL, fg=color, font=fuente)

    def _boton(self, padre, texto: str, comando, primario: bool = False, ancho: int | None = None):
        """Boton con la paleta morado/blanco: los botones "primarios"
        (ej. Iniciar/Detener) usan morado solido con texto blanco; el
        resto usa un morado mas discreto para no competir visualmente."""
        color_fondo = COLOR_MORADO if primario else COLOR_FONDO_HISTORIAL
        color_borde = COLOR_MORADO
        if _TIENE_CUSTOMTKINTER:
            return ctk.CTkButton(
                padre,
                text=texto,
                command=comando,
                fg_color=color_fondo,
                hover_color=COLOR_MORADO_OSCURO,
                text_color=COLOR_BLANCO,
                border_color=color_borde,
                border_width=1 if not primario else 0,
                width=ancho or 140,
            )
        boton = tk.Button(
            padre,
            text=texto,
            command=comando,
            bg=color_fondo,
            fg=COLOR_BLANCO,
            activebackground=COLOR_MORADO_OSCURO,
            activeforeground=COLOR_BLANCO,
            relief="flat",
            highlightthickness=1,
            highlightbackground=color_borde,
            highlightcolor=color_borde,
            padx=10,
            pady=4,
            cursor="hand2",
        )
        if ancho:
            boton.configure(width=3)
        return boton

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
            texto_estado, color_estado = "● Escuchando", COLOR_ESTADO_ACTIVO
            texto_boton = "■ Detener"
        else:
            texto_estado, color_estado = "● Detenido", COLOR_ESTADO_INACTIVO
            texto_boton = "▶ Iniciar"

        if _TIENE_CUSTOMTKINTER:
            self.etiqueta_estado.configure(text=texto_estado, text_color=color_estado)
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
        self._agregar_al_historial(resultado)

    def _agregar_al_historial(self, resultado) -> None:
        """Agrega una entrada al historial con formato claro: la linea del
        idioma de origen y la traducida quedan visualmente separadas (con
        etiquetas de color distinto y un pequeño divisor), en vez de texto
        plano donde ambos idiomas se mezclan y confunden."""
        origen = resultado.idioma_origen.upper()
        destino = resultado.idioma_destino.upper()

        self.area_historial.configure(state="normal")
        self.area_historial.insert("end", f"{origen}  ", "etiqueta_origen")
        self.area_historial.insert("end", f"{resultado.texto_original}\n", "texto_origen")
        self.area_historial.insert("end", f"{destino}  ", "etiqueta_destino")
        self.area_historial.insert("end", f"{resultado.texto_traducido}\n", "texto_destino")
        self.area_historial.insert("end", "─" * 60 + "\n", "separador")
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
        ventana_configuracion = crear_ventana_configuracion(
            self.ventana,
            configuracion_actual=self.configuracion,
            al_guardar=self._aplicar_configuracion,
        )
        # Misma imagen de icono que la ventana principal (no solo la
        # ventana principal debe mostrar el icono de HARIMENT).
        self._aplicar_icono_ventana(ventana_configuracion)

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
        if _TIENE_CUSTOMTKINTER:
            self.etiqueta_idiomas.configure(
                text=f"{self.traductor.idioma_origen.upper()} → {self.traductor.idioma_destino.upper()}"
            )
        else:
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
