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
