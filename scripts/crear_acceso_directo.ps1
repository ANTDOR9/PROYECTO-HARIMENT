# Crea un acceso directo de PROYECTO HARIMENT en el Escritorio de Windows,
# usando el icono de la cabeza (assets/icons/hariment.ico) y arrancando la
# app sin abrir una consola visible (via pythonw.exe del entorno virtual).
#
# Uso (desde la carpeta del proyecto, con PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\crear_acceso_directo.ps1
#
# Si prefieres, tambien puedes abrir este archivo con click derecho ->
# "Ejecutar con PowerShell".

$ErrorActionPreference = "Stop"

$raizProyecto = Split-Path -Parent $PSScriptRoot
$rutaPythonw = Join-Path $raizProyecto "venv\Scripts\pythonw.exe"
$rutaScript = Join-Path $raizProyecto "scripts\run_gui.py"
$rutaIcono = Join-Path $raizProyecto "assets\icons\hariment.ico"
$rutaEscritorio = [Environment]::GetFolderPath("Desktop")
$rutaAccesoDirecto = Join-Path $rutaEscritorio "PROYECTO HARIMENT.lnk"

if (-not (Test-Path $rutaPythonw)) {
    Write-Host "No se encontro el entorno virtual en '$rutaPythonw'."
    Write-Host "Crea el venv primero (python -m venv venv) e instala requirements.txt."
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$acceso = $shell.CreateShortcut($rutaAccesoDirecto)
$acceso.TargetPath = $rutaPythonw
$acceso.Arguments = '"' + $rutaScript + '"'
$acceso.WorkingDirectory = $raizProyecto
$acceso.IconLocation = $rutaIcono
$acceso.Description = "PROYECTO HARIMENT - Traductor en tiempo real"
$acceso.Save()

Write-Host "Listo: acceso directo creado en el Escritorio -> $rutaAccesoDirecto"
