"""
Configuracion centralizada de logging para PROYECTO HARIMENT.

Se agrega en la Etapa 9 (pulido final) porque, una vez empaquetada la
app con `--windowed` (Etapa 9, `scripts/build_windows.py`), ya no hay
consola visible: sin esto, un error durante la escucha del microfono o
una traduccion fallida desaparecerian en silencio para el usuario.

Uso basico (al inicio de un punto de entrada, como scripts/run_gui.py):

    from hariment.registro import configurar_logging
    configurar_logging()

Despues, en cualquier modulo:

    import logging
    logger = logging.getLogger(__name__)
    logger.info("...")
    logger.exception("algo fallo")
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

NOMBRE_ARCHIVO_LOG = "hariment.log"
TAMANO_MAXIMO_BYTES = 2 * 1024 * 1024  # 2 MB por archivo
CANTIDAD_RESPALDOS = 3


def _ruta_carpeta_logs() -> str:
    raiz_proyecto = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(raiz_proyecto, "logs")


def configurar_logging(nivel: int = logging.INFO) -> None:
    """Configura logging a consola y a un archivo rotativo (logs/hariment.log).

    Se puede llamar varias veces sin problema (por ejemplo si tanto la
    GUI como la API se importan en el mismo proceso durante pruebas):
    solo agrega los handlers una vez.
    """
    logger_raiz = logging.getLogger()
    if logger_raiz.handlers:
        return  # ya configurado

    logger_raiz.setLevel(nivel)
    formato = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    manejador_consola = logging.StreamHandler()
    manejador_consola.setFormatter(formato)
    logger_raiz.addHandler(manejador_consola)

    try:
        carpeta_logs = _ruta_carpeta_logs()
        os.makedirs(carpeta_logs, exist_ok=True)
        manejador_archivo = RotatingFileHandler(
            os.path.join(carpeta_logs, NOMBRE_ARCHIVO_LOG),
            maxBytes=TAMANO_MAXIMO_BYTES,
            backupCount=CANTIDAD_RESPALDOS,
            encoding="utf-8",
        )
        manejador_archivo.setFormatter(formato)
        logger_raiz.addHandler(manejador_archivo)
    except OSError:
        # Si por algun motivo no se puede escribir en disco (permisos,
        # disco lleno), la app sigue funcionando solo con log a consola.
        logger_raiz.warning("No se pudo crear el archivo de log; se continua solo con consola.")
