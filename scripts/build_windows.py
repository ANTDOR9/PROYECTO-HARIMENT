"""Empaqueta la interfaz de escritorio de PROYECTO HARIMENT como un .exe
de Windows usando PyInstaller.

Uso (en Windows, con el entorno virtual activado y `pip install pyinstaller`):

    python scripts/build_windows.py

El ejecutable queda en dist/HarimentApp/HarimentApp.exe (modo carpeta,
--onedir) en vez de un solo archivo (--onefile), a proposito: Whisper y
transformers son pesados, y --onedir arranca mucho mas rapido que
--onefile (que descomprime todo en cada ejecucion).
"""

import os
import subprocess
import sys

RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller no esta instalado. Instalalo con: pip install pyinstaller")
        sys.exit(1)

    script_entrada = os.path.join(RAIZ_PROYECTO, "scripts", "run_gui.py")
    ruta_assets = os.path.join(RAIZ_PROYECTO, "assets")

    comando = [
        sys.executable,
        "-m",
        "PyInstaller",
        script_entrada,
        "--name",
        "HarimentApp",
        "--windowed",  # sin consola visible al abrir la app
        "--paths",
        os.path.join(RAIZ_PROYECTO, "src"),
        "--add-data",
        f"{ruta_assets}{os.pathsep}assets",
        "--clean",
        "--noconfirm",
    ]

    icono = os.path.join(RAIZ_PROYECTO, "assets", "icons", "hariment.ico")
    if os.path.exists(icono):
        comando += ["--icon", icono]

    print("Ejecutando:", " ".join(comando))
    subprocess.run(comando, cwd=RAIZ_PROYECTO, check=True)

    print("\nListo. Ejecutable en: dist/HarimentApp/HarimentApp.exe")
    print(
        "Nota: la primera vez que la app use Whisper/transformers, esos "
        "modelos se descargan aparte (no van dentro del .exe) y quedan en "
        "la cache del usuario."
    )


if __name__ == "__main__":
    main()
