"""
Captura de pantalla para PROYECTO HARIMENT.

Usa `mss` (rapido y multiplataforma) para tomar una captura de la
pantalla completa o de una region especifica, y la devuelve como una
imagen de Pillow lista para pasarle al modulo de OCR
(`hariment.ocr.reconocimiento_texto`).

Uso basico:

    from hariment.ocr.captura_pantalla import capturar_pantalla

    imagen = capturar_pantalla()              # pantalla completa
    imagen = capturar_pantalla(monitor=2)      # un monitor especifico
    imagen = capturar_pantalla(region=(0, 0, 800, 600))  # una region (x, y, ancho, alto)
"""

from __future__ import annotations

from typing import Optional, Tuple


def capturar_pantalla(
    monitor: int = 1,
    region: Optional[Tuple[int, int, int, int]] = None,
):
    """Toma una captura de pantalla y la devuelve como imagen de Pillow.

    Args:
        monitor: indice del monitor a capturar cuando hay varios
            (1 = principal en la convencion de `mss`; 0 = todos combinados).
            Se ignora si se pasa `region`.
        region: tupla (x, y, ancho, alto) en pixeles, para capturar solo
            una parte de la pantalla (por ejemplo, donde esta el video
            que se quiere traducir) en vez de la pantalla completa.

    Returns:
        Una `PIL.Image.Image` en modo RGB.
    """
    import mss
    from PIL import Image

    with mss.mss() as captura:
        if region is not None:
            x, y, ancho, alto = region
            area = {"left": x, "top": y, "width": ancho, "height": alto}
        else:
            area = captura.monitors[monitor]

        captura_cruda = captura.grab(area)
        imagen = Image.frombytes("RGB", captura_cruda.size, captura_cruda.bgra, "raw", "BGRX")
        return imagen


def seleccionar_region_pantalla(ventana_padre=None):
    """Muestra una ventana semitransparente de pantalla completa donde el
    usuario dibuja un rectangulo (clic + arrastrar) para elegir la zona
    exacta que se quiere capturar (por ejemplo, la caja de chat de un
    juego o los subtitulos de un video), en vez de capturar toda la
    pantalla.

    Se usa una ventana de tkinter en vez de mss/PIL para el overlay
    porque necesita recibir eventos de mouse en tiempo real; la
    captura final de la imagen se sigue haciendo con `capturar_pantalla`.

    Args:
        ventana_padre: ventana tkinter existente (para que el overlay se
            comporte como un dialogo de esa aplicacion). Puede ser None.

    Returns:
        Una tupla (x, y, ancho, alto) en pixeles de pantalla, o `None` si
        el usuario cancelo (tecla Escape) o hizo un area invalida
        (ancho o alto menor a 5 pixeles).
    """
    import tkinter as tk

    resultado = {"region": None}
    inicio = {"x": 0, "y": 0}

    overlay = tk.Toplevel(ventana_padre) if ventana_padre is not None else tk.Tk()
    overlay.attributes("-fullscreen", True)
    overlay.attributes("-alpha", 0.3)
    overlay.configure(bg="black")
    overlay.attributes("-topmost", True)
    overlay.config(cursor="crosshair")

    lienzo = tk.Canvas(overlay, bg="black", highlightthickness=0)
    lienzo.pack(fill="both", expand=True)

    etiqueta_ayuda = tk.Label(
        overlay,
        text="Arrastra para elegir el área a capturar. Esc para cancelar.",
        fg="white",
        bg="black",
        font=("Segoe UI", 14),
    )
    lienzo.create_window(20, 20, anchor="nw", window=etiqueta_ayuda)

    rectangulo_id = {"id": None}

    def _al_presionar(evento):
        inicio["x"], inicio["y"] = evento.x, evento.y
        if rectangulo_id["id"] is not None:
            lienzo.delete(rectangulo_id["id"])
        rectangulo_id["id"] = lienzo.create_rectangle(
            evento.x, evento.y, evento.x, evento.y, outline="#00FF00", width=2
        )

    def _al_arrastrar(evento):
        if rectangulo_id["id"] is not None:
            lienzo.coords(rectangulo_id["id"], inicio["x"], inicio["y"], evento.x, evento.y)

    def _al_soltar(evento):
        x0, y0 = inicio["x"], inicio["y"]
        x1, y1 = evento.x, evento.y
        x, y = min(x0, x1), min(y0, y1)
        ancho, alto = abs(x1 - x0), abs(y1 - y0)
        if ancho >= 5 and alto >= 5:
            resultado["region"] = (x, y, ancho, alto)
        overlay.destroy()

    def _al_cancelar(_evento=None):
        overlay.destroy()

    lienzo.bind("<ButtonPress-1>", _al_presionar)
    lienzo.bind("<B1-Motion>", _al_arrastrar)
    lienzo.bind("<ButtonRelease-1>", _al_soltar)
    overlay.bind("<Escape>", _al_cancelar)

    overlay.grab_set()
    overlay.wait_window()

    return resultado["region"]


def listar_monitores() -> list[dict]:
    """Devuelve informacion de los monitores disponibles (para una futura
    seleccion en la interfaz de "que pantalla/monitor capturar")."""
    import mss

    with mss.mss() as captura:
        # El indice 0 es "todos los monitores combinados"; se excluye porque
        # no corresponde a un monitor fisico seleccionable individualmente.
        return list(captura.monitors[1:])


if __name__ == "__main__":
    # Demo: guarda una captura de pantalla completa en el directorio actual.
    #   python -m hariment.ocr.captura_pantalla
    imagen = capturar_pantalla()
    imagen.save("captura_prueba.png")
    print(f"Captura guardada en captura_prueba.png ({imagen.size[0]}x{imagen.size[1]})")
