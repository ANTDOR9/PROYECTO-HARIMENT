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


class TesseractNoInstaladoError(Exception):
    """Se lanza cuando pytesseract no logra encontrar el ejecutable de Tesseract."""


# Rutas donde el instalador oficial de Tesseract para Windows (UB-Mannheim)
# suele dejar el ejecutable. Si pytesseract no lo encuentra en el PATH,
# probamos estas rutas conocidas antes de rendirnos.
_RUTAS_TESSERACT_WINDOWS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

_ruta_tesseract_configurada = False


def _configurar_ruta_tesseract(pytesseract_modulo) -> None:
    """Si Tesseract no esta en el PATH, intenta apuntar pytesseract
    directamente al .exe en las rutas de instalacion tipicas de Windows.

    Se ejecuta una sola vez por proceso (cacheado con una bandera simple)
    para no pagar el costo de revisar el sistema de archivos en cada
    captura de pantalla.
    """
    global _ruta_tesseract_configurada
    if _ruta_tesseract_configurada:
        return
    _ruta_tesseract_configurada = True

    # Acceso defensivo: en los tests, `pytesseract` se reemplaza por un
    # modulo de prueba simplificado que no tiene esta sub-estructura; en
    # ese caso no hay nada que auto-detectar y se sigue de largo.
    submodulo = getattr(pytesseract_modulo, "pytesseract", None)
    if submodulo is None:
        return

    import shutil

    if shutil.which(getattr(submodulo, "tesseract_cmd", None) or "tesseract"):
        return

    import os

    for ruta in _RUTAS_TESSERACT_WINDOWS:
        if os.path.isfile(ruta):
            pytesseract_modulo.pytesseract.tesseract_cmd = ruta
            return


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

        _configurar_ruta_tesseract(pytesseract)

        codigo_tesseract = CODIGOS_IDIOMA_TESSERACT.get(idioma, "eng")
        try:
            texto = pytesseract.image_to_string(imagen, lang=codigo_tesseract)
        except pytesseract.TesseractNotFoundError as error:
            raise TesseractNoInstaladoError(
                "No se encontro el programa Tesseract OCR instalado en el sistema. "
                "Instalalo desde https://github.com/UB-Mannheim/tesseract/wiki "
                "(usa las opciones por defecto) y vuelve a intentar. Si ya lo "
                "instalaste, verifica que la carpeta de instalacion este en el "
                "PATH del sistema o reinicia la terminal despues de instalarlo."
            ) from error
        except pytesseract.TesseractError as error:
            mensaje = str(error)
            if "Failed loading language" in mensaje or "Error opening data file" in mensaje:
                # El motor de Tesseract esta instalado pero le falta el
                # paquete de datos de idioma (por ejemplo "spa" para
                # espanol). El instalador de Windows solo trae ingles
                # por defecto salvo que se marquen idiomas adicionales.
                raise TesseractNoInstaladoError(
                    f"Tesseract esta instalado pero le falta el paquete de idioma "
                    f"'{codigo_tesseract}' (necesario para reconocer texto en "
                    f"'{idioma}'). Descarga el archivo '{codigo_tesseract}.traineddata' "
                    f"desde https://github.com/tesseract-ocr/tessdata "
                    f"y colocalo dentro de la carpeta "
                    f"'C:\\Program Files\\Tesseract-OCR\\tessdata\\'. "
                    f"Luego vuelve a intentar."
                ) from error
            raise
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
