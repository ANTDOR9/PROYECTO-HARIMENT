"""Punto de entrada para lanzar la API de PROYECTO HARIMENT.

Uso:
    python scripts/run_api.py

La API queda disponible en http://127.0.0.1:8000 por defecto, con
documentacion interactiva automatica en http://127.0.0.1:8000/docs
(generada por FastAPI).
"""

import json
import os
import sys

RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ_PROYECTO, "src"))

RUTA_CONFIG_USUARIO = os.path.join(RAIZ_PROYECTO, "assets", "config", "settings.json")
RUTA_CONFIG_EJEMPLO = os.path.join(RAIZ_PROYECTO, "assets", "config", "settings.example.json")


def _leer_host_y_puerto() -> tuple[str, int]:
    ruta = RUTA_CONFIG_USUARIO if os.path.exists(RUTA_CONFIG_USUARIO) else RUTA_CONFIG_EJEMPLO
    with open(ruta, "r", encoding="utf-8") as archivo:
        configuracion_api = json.load(archivo).get("api", {})
    return configuracion_api.get("host", "127.0.0.1"), configuracion_api.get("puerto", 8000)


if __name__ == "__main__":
    import uvicorn

    from hariment.registro import configurar_logging

    configurar_logging()
    host, puerto = _leer_host_y_puerto()
    print(f"Iniciando PROYECTO HARIMENT API en http://{host}:{puerto} (docs en /docs)")
    uvicorn.run("hariment.api.main:app", host=host, port=puerto, reload=False)
