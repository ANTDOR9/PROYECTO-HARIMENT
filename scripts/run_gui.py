"""Punto de entrada para lanzar la interfaz grafica de PROYECTO HARIMENT.

Uso:
    python scripts/run_gui.py
"""

import os
import sys

# Permite ejecutar el script directamente sin instalar el paquete,
# agregando "src/" al path de importacion.
RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ_PROYECTO, "src"))

from hariment.gui.app import main  # noqa: E402

if __name__ == "__main__":
    main()
