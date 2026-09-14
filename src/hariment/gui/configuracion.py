"""
Gestion de configuracion de PROYECTO HARIMENT.

Este modulo tiene dos responsabilidades:

1. `GestorConfiguracion`: cargar/guardar la configuracion del usuario en
   `assets/config/settings.json` (si no existe, se parte de
   `assets/config/settings.example.json`). No depende de tkinter, por lo
   que se puede usar y probar (tests) en cualquier entorno.
2. `VentanaConfiguracion`: una ventana emergente (Toplevel) con controles
   para cambiar en caliente lo que el usuario pidio que fuera
   configurable: idioma de entrada/salida, y estilo de los subtitulos
   (posicion, tamaño de letra, colores, opacidad, tiempo de permanencia).

La ventana no aplica nada por si sola: al presionar "Guardar" llama a un
callback (`al_guardar`) con el diccionario de configuracion actualizado,
para que quien la abrio (la ventana principal) decida como aplicarlo.

`tkinter` se importa de forma perezosa (dentro de `crear_ventana_configuracion`)
para que `GestorConfiguracion` se pueda importar y testear en entornos que
no tengan tkinter instalado (por ejemplo, algunos entornos de CI/Linux).
"""

from __future__ import annotations

import json
import os
from typing import Callable

from hariment.translation.traductor import idiomas_soportados

RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
RUTA_CONFIG_USUARIO = os.path.join(RAIZ_PROYECTO, "assets", "config", "settings.json")
RUTA_CONFIG_EJEMPLO = os.path.join(RAIZ_PROYECTO, "assets", "config", "settings.example.json")

POSICIONES_SUBTITULO = ["superior", "inferior"]

# Nombres amigables para mostrar en la interfaz, mapeados al codigo real.
NOMBRES_IDIOMA = {
    "es": "Español",
    "en": "Inglés",
    "pt": "Portugués",
    "auto": "Detectar automáticamente",
}


class GestorConfiguracion:
    """Lee y escribe la configuracion del usuario en disco (JSON)."""

    def __init__(self, ruta_usuario: str = RUTA_CONFIG_USUARIO, ruta_ejemplo: str = RUTA_CONFIG_EJEMPLO) -> None:
        self.ruta_usuario = ruta_usuario
        self.ruta_ejemplo = ruta_ejemplo

    def cargar(self) -> dict:
        """Carga la configuracion del usuario; si no existe, usa la de ejemplo."""
        ruta = self.ruta_usuario if os.path.exists(self.ruta_usuario) else self.ruta_ejemplo
        with open(ruta, "r", encoding="utf-8") as archivo:
            return json.load(archivo)

    def guardar(self, configuracion: dict) -> None:
        """Guarda la configuracion del usuario, creando la carpeta si hace falta."""
        os.makedirs(os.path.dirname(self.ruta_usuario), exist_ok=True)
        with open(self.ruta_usuario, "w", encoding="utf-8") as archivo:
            json.dump(configuracion, archivo, indent=2, ensure_ascii=False)


def crear_ventana_configuracion(padre, configuracion_actual: dict, al_guardar: Callable[[dict], None]):
    """Crea, muestra y devuelve la ventana emergente de configuracion.

    Se construye la clase aqui dentro (en vez de a nivel de modulo) para
    que el `import tkinter` solo ocurra cuando realmente se abre la
    ventana, dejando el resto del modulo libre de esa dependencia.
    """
    import tkinter as tk
    from tkinter import ttk

    class VentanaConfiguracion(tk.Toplevel):
        def __init__(self) -> None:
            super().__init__(padre)
            self.title("Configuración — PROYECTO HARIMENT")
            self.geometry("420x520")
            self.resizable(False, False)
            self.configure(bg="#2B2B2B")

            self._configuracion = configuracion_actual
            self._al_guardar = al_guardar

            self._construir_seccion_idiomas()
            self._construir_seccion_subtitulos()
            self._construir_botones()

        # --------------------------------------------------------------

        def _construir_seccion_idiomas(self) -> None:
            marco = self._marco_titulado("Idiomas")

            pares_soportados = idiomas_soportados()
            idiomas_origen_disponibles = sorted({origen for origen, _ in pares_soportados})

            tk.Label(marco, text="Idioma de origen:", bg="#2B2B2B", fg="#FFFFFF").pack(anchor="w")
            self.variable_idioma_origen = tk.StringVar(value=self._configuracion.get("idioma_origen", "es"))
            combo_origen = ttk.Combobox(
                marco,
                textvariable=self.variable_idioma_origen,
                values=idiomas_origen_disponibles,
                state="readonly",
            )
            combo_origen.pack(fill="x", pady=(0, 10))
            combo_origen.bind("<<ComboboxSelected>>", lambda _evento: self._actualizar_destinos_disponibles())

            tk.Label(marco, text="Idioma de destino:", bg="#2B2B2B", fg="#FFFFFF").pack(anchor="w")
            self.variable_idioma_destino = tk.StringVar(value=self._configuracion.get("idioma_destino", "en"))
            self.combo_destino = ttk.Combobox(marco, textvariable=self.variable_idioma_destino, state="readonly")
            self.combo_destino.pack(fill="x")
            self._actualizar_destinos_disponibles()

        def _actualizar_destinos_disponibles(self) -> None:
            """Filtra los idiomas de destino segun el idioma de origen elegido,
            para no dejar seleccionar un par que no tiene modelo (Etapa 2)."""
            origen = self.variable_idioma_origen.get()
            destinos = sorted(destino for o, destino in idiomas_soportados() if o == origen)
            self.combo_destino["values"] = destinos
            if self.variable_idioma_destino.get() not in destinos and destinos:
                self.variable_idioma_destino.set(destinos[0])

        def _construir_seccion_subtitulos(self) -> None:
            marco = self._marco_titulado("Subtítulos")
            subtitulos = self._configuracion.get("subtitulos", {})

            tk.Label(marco, text="Posición:", bg="#2B2B2B", fg="#FFFFFF").pack(anchor="w")
            self.variable_posicion = tk.StringVar(value=subtitulos.get("posicion", "inferior"))
            ttk.Combobox(
                marco,
                textvariable=self.variable_posicion,
                values=POSICIONES_SUBTITULO,
                state="readonly",
            ).pack(fill="x", pady=(0, 10))

            tk.Label(marco, text="Tamaño de fuente:", bg="#2B2B2B", fg="#FFFFFF").pack(anchor="w")
            self.variable_tamano_fuente = tk.IntVar(value=subtitulos.get("tamano_fuente", 24))
            tk.Scale(
                marco, from_=12, to=48, orient="horizontal", variable=self.variable_tamano_fuente,
                bg="#2B2B2B", fg="#FFFFFF", highlightthickness=0, troughcolor="#444444",
            ).pack(fill="x", pady=(0, 10))

            tk.Label(marco, text="Color de texto (hex):", bg="#2B2B2B", fg="#FFFFFF").pack(anchor="w")
            self.variable_color_texto = tk.StringVar(value=subtitulos.get("color_texto", "#FFFFFF"))
            tk.Entry(marco, textvariable=self.variable_color_texto).pack(fill="x", pady=(0, 10))

            tk.Label(marco, text="Color de fondo (hex):", bg="#2B2B2B", fg="#FFFFFF").pack(anchor="w")
            self.variable_color_fondo = tk.StringVar(value=subtitulos.get("color_fondo", "#000000"))
            tk.Entry(marco, textvariable=self.variable_color_fondo).pack(fill="x", pady=(0, 10))

            tk.Label(marco, text="Tiempo de permanencia (segundos):", bg="#2B2B2B", fg="#FFFFFF").pack(anchor="w")
            self.variable_tiempo_permanencia = tk.IntVar(value=subtitulos.get("tiempo_permanencia_segundos", 4))
            tk.Scale(
                marco, from_=1, to=15, orient="horizontal", variable=self.variable_tiempo_permanencia,
                bg="#2B2B2B", fg="#FFFFFF", highlightthickness=0, troughcolor="#444444",
            ).pack(fill="x")

        def _construir_botones(self) -> None:
            marco = tk.Frame(self, bg="#2B2B2B")
            marco.pack(fill="x", padx=15, pady=15)

            tk.Button(marco, text="Cancelar", command=self.destroy).pack(side="right", padx=(10, 0))
            tk.Button(marco, text="Guardar", command=self._guardar_y_cerrar).pack(side="right")

        def _marco_titulado(self, titulo: str):
            contenedor = tk.LabelFrame(
                self, text=titulo, bg="#2B2B2B", fg="#FFFFFF", labelanchor="nw", padx=10, pady=10
            )
            contenedor.pack(fill="x", padx=15, pady=(15, 0))
            return contenedor

        # --------------------------------------------------------------

        def _guardar_y_cerrar(self) -> None:
            nueva_configuracion = dict(self._configuracion)
            nueva_configuracion["idioma_origen"] = self.variable_idioma_origen.get()
            nueva_configuracion["idioma_destino"] = self.variable_idioma_destino.get()
            nueva_configuracion["subtitulos"] = {
                **self._configuracion.get("subtitulos", {}),
                "posicion": self.variable_posicion.get(),
                "tamano_fuente": self.variable_tamano_fuente.get(),
                "color_texto": self.variable_color_texto.get(),
                "color_fondo": self.variable_color_fondo.get(),
                "tiempo_permanencia_segundos": self.variable_tiempo_permanencia.get(),
            }

            self._al_guardar(nueva_configuracion)
            self.destroy()

    return VentanaConfiguracion()
