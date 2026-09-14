"""
Reconocimiento de texto en imagenes (OCR) para PROYECTO HARIMENT.

Soporta dos motores intercambiables, elegibles por configuracion
(`assets/config/settings.json` -> `ocr.motor`):

- "pytesseract" (por defecto): envoltura de Tesseract OCR. Rapido y
  liviano, buen punto de partida para texto claro y bien alineado
  (subtitulos de video, texto de una app).
- "trocr": modelo de IA (`microsoft/trocr-base-printed` via
  `transformers`) para texto con formato mas irregular, donde
  Tesseract clasico suele fallar mas (fondos complejos, contornos,
  fuentes decorativas).

Ambos motores exponen la misma interfaz (`ReconocedorTexto.reconocer`),
para que el resto de la aplicacion no necesite saber cual esta activo.

Uso basico:

    from hariment.ocr.captura_pantalla import capturar_pantalla
    from hariment.ocr.reconocimiento_texto import ReconocedorTexto

    reconocedor = ReconocedorTexto(motor="pytesseract")
    imagen = capturar_pantalla()
    texto = reconocedor.reconocer(imagen)
"""

from __future__ import annotations

from typing import Optional

# Tesseract identifica los idiomas con codigos de 3 letras, distintos a
# los que usa el resto del proyecto (2 letras). Este mapa traduce entre
# ambos para que la configuracion de idioma sea consistente en toda la app.
CODIGOS_IDIOMA_TESSERACT = {
    "es": "spa",
    "en": "eng",
    "pt": "por",
}


class MotorOcrNoSoportadoError(Exception):
    """Se lanza cuando se pide un motor de OCR que no esta implementado."""


class ReconocedorTexto:
    """Reconoce texto dentro de una imagen, usando el motor de OCR configurado."""

    def __init__(self, motor: str = "pytesseract") -> None:
        if motor not in ("pytesseract", "trocr"):
            raise MotorOcrNoSoportadoError(
                f"Motor de OCR desconocido: '{motor}'. Usa 'pytesseract' o 'trocr'."
            )
        self.motor = motor
        self._pipeline_trocr = None

    def reconocer(self, imagen, idioma: str = "es") -> str:
        """Reconoce el texto presente en `imagen` (PIL.Image).

        Args:
            imagen: imagen de Pillow (por ejemplo, obtenida con
                `hariment.ocr.captura_pantalla.capturar_pantalla`).
            idioma: codigo de idioma de 2 letras (es/en/pt) del texto
                esperado en la imagen. Solo lo usa el motor `pytesseract`;
                `trocr` (en su version base) esta entrenado para ingles.

        Returns:
            El texto reconocido, con espacios en blanco extra recortados.
        """
        if self.motor == "pytesseract":
            return self._reconocer_con_pytesseract(imagen, idioma)
        return self._reconocer_con_trocr(imagen)

    # ------------------------------------------------------------------

    def _reconocer_con_pytesseract(self, imagen, idioma: str) -> str:
        import pytesseract

        codigo_tesseract = CODIGOS_IDIOMA_TESSERACT.get(idioma, "eng")
        texto = pytesseract.image_to_string(imagen, lang=codigo_tesseract)
        return texto.strip()

    def _reconocer_con_trocr(self, imagen) -> str:
        if self._pipeline_trocr is None:
            self._pipeline_trocr = _cargar_pipeline_trocr()

        resultado = self._pipeline_trocr(imagen)
        # El pipeline de image-to-text de transformers devuelve
        # [{"generated_text": "..."}].
        return resultado[0]["generated_text"].strip()


def _cargar_pipeline_trocr():
    from transformers import pipeline

    return pipeline("image-to-text", model="microsoft/trocr-base-printed")


if __name__ == "__main__":
    # Demo: reconoce el texto de la pantalla actual y lo imprime.
    #   python -m hariment.ocr.reconocimiento_texto
    from hariment.ocr.captura_pantalla import capturar_pantalla

    imagen = capturar_pantalla()
    reconocedor = ReconocedorTexto(motor="pytesseract")
    texto = reconocedor.reconocer(imagen, idioma="es")

    print("Texto reconocido en pantalla:")
    print(texto or "(no se detecto texto)")
