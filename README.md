<img src="assets/icons/icono_readme.png" alt="Icono de PROYECTO HARIMENT" width="72" align="left" />

# PROYECTO HARIMENT

<br clear="left"/>

Software de traducción y asistencia de idiomas en tiempo real. Escucha, reconoce y traduce voz, audio del sistema y texto en pantalla, mostrando el resultado como subtítulos configurables.

## Objetivo

Ayudar a comunicarse con personas que hablan otro idioma y a entender contenido (videos, llamadas, texto en pantalla) en un idioma distinto al propio, mediante transcripción y traducción automática en tiempo real.

## Funcionalidades planificadas

- **Reconocimiento de voz por micrófono**: transcribe en tiempo real lo que el usuario habla.
- **Captura de audio del sistema (loopback)**: transcribe el audio que reproduce el propio computador (videos, llamadas, etc.), no solo el micrófono.
- **Captura de pantalla + OCR**: toma una captura de pantalla y reconoce el texto presente en la imagen (subtítulos incrustados, texto de una app, etc.).
- **Traducción automática**: traduce el texto reconocido de español a inglés (versión inicial), con soporte planificado para más idiomas, priorizando portugués y otros idiomas de Latinoamérica.
- **Subtítulos en pantalla configurables**: posición, tamaño, color/estilo y tiempo de permanencia de los subtítulos mostrados.
- **Selección de idioma de entrada/salida**: el usuario podrá elegir o dejar en detección automática el idioma de origen, y elegir el idioma de destino.
- **Modo de activación en tiempo real**: botones para iniciar/detener la escucha (micrófono, audio del sistema) y la traducción, sin tener que cerrar la aplicación.
- **Interfaz gráfica simple**: pensada para escritorio (Windows), con posibilidad futura de una interfaz más avanzada.
- **Exposición como API**: la lógica de transcripción, OCR y traducción se podrá exponer mediante una API, para que otras interfaces (incluyendo una futura app móvil) puedan consumir el mismo motor.

## Arquitectura (visión general)

Tres posibles entradas alimentan un mismo núcleo de procesamiento:

```
Micrófono ─────┐
Audio del      ├──► Reconocimiento (voz→texto / OCR) ──► Traducción ──► Subtítulos en interfaz
sistema ───────┤
Captura de     │
pantalla ──────┘
```

A futuro, cada entrada y la traducción podrán exponerse como endpoints independientes de una API (por ejemplo: `/transcribir-audio`, `/ocr-captura`, `/traducir`), de forma que la interfaz de escritorio y una futura app móvil consuman el mismo backend.

## Librerías y tecnologías consideradas

| Librería / Herramienta | Uso en el proyecto |
|---|---|
| `openai-whisper` | Reconocimiento de voz (micrófono y audio del sistema) → texto |
| `soundcard` / `pyaudiowpatch` | Captura de audio del sistema (loopback) en Windows |
| `pytesseract` (Tesseract OCR) | Reconocimiento de texto en capturas de pantalla (OCR clásico) |
| `TrOCR` (Hugging Face `transformers`) | OCR alternativo basado en modelo de IA, para texto con formato irregular (subtítulos, fondos complejos) |
| `mss` / `pyautogui` | Captura de pantalla |
| `Pillow` | Manejo y preprocesamiento de imágenes |
| `transformers` (Hugging Face) | Traducción automática (ej. modelos `Helsinki-NLP/opus-mt-*`) |
| `torch` (PyTorch) | Backend de ejecución para modelos de `transformers` |
| `FastAPI` | Exposición del motor de transcripción/OCR/traducción como API |
| `tkinter` / `customtkinter` / `PyQt` | Interfaz gráfica de escritorio |

## Estado del proyecto

Las 9 etapas planificadas están implementadas end-to-end (micrófono, audio del sistema, OCR de pantalla, traducción, interfaz configurable, API y empaquetado). Próximos pasos naturales: ampliar idiomas más allá de es/en/pt, y explorar una interfaz de escritorio más avanzada o una versión móvil.

## Estructura de carpetas

```
PROYECTO-HARIMENT/
├── src/hariment/
│   ├── audio/            # Captura de micrófono y audio del sistema (loopback) + transcripción con Whisper
│   │   ├── microfono.py
│   │   └── sistema_loopback.py
│   ├── ocr/               # Captura de pantalla y reconocimiento de texto (OCR)
│   │   ├── captura_pantalla.py
│   │   └── reconocimiento_texto.py
│   ├── translation/       # Núcleo de traducción automática (transformers)
│   │   └── traductor.py
│   ├── subtitles/         # Overlay de subtítulos en pantalla (configurable)
│   │   └── overlay.py
│   ├── gui/                # Interfaz gráfica de escritorio
│   │   ├── app.py
│   │   └── configuracion.py
│   └── api/                # API (FastAPI) que expone el motor del proyecto
│       └── main.py
├── scripts/                # Puntos de entrada (lanzar GUI, lanzar API)
│   ├── run_gui.py
│   └── run_api.py
├── tests/                   # Pruebas unitarias por módulo
├── docs/                    # Documentación técnica (arquitectura, etapas)
│   ├── arquitectura.md
│   └── etapas.md
├── assets/
│   ├── config/              # Archivos de configuración (idiomas, estilo de subtítulos)
│   └── icons/                # Recursos gráficos de la interfaz
├── requirements.txt
├── .gitignore
├── LICENSE
└── README.md
```

## Etapas de desarrollo

El desarrollo está planificado en 9 etapas, desde la configuración base hasta el empaquetado final. Detalle completo en [`docs/etapas.md`](docs/etapas.md):

1. Configuración base del proyecto
2. Núcleo de traducción de texto
3. Reconocimiento de voz por micrófono
4. Interfaz gráfica mínima con subtítulos
5. Configuración de subtítulos e idiomas
6. Audio del sistema (loopback)
7. Captura de pantalla + OCR
8. Exposición como API
9. Empaquetado y pulido final

## Roadmap

1. Prototipo base: transcripción por micrófono (Whisper) + traducción español → inglés (transformers), con interfaz mínima.
2. Subtítulos en pantalla configurables (posición, estilo, tiempo de permanencia).
3. Captura y traducción de audio del sistema (loopback).
4. Captura de pantalla + OCR para reconocer y traducir texto en imágenes/video.
5. Selección de idioma de entrada/salida, con soporte ampliado (prioridad: portugués y otros idiomas de Latinoamérica).
6. Exposición del motor como API (FastAPI), desacoplando la lógica de la interfaz.
7. Exploración de una interfaz de escritorio más avanzada y una futura versión para teléfono.

## Instalación

Requiere Python 3.10 o superior.

```bash
# 1. Clonar el repositorio
git clone https://github.com/<usuario>/PROYECTO-HARIMENT.git
cd PROYECTO-HARIMENT

# 2. Crear y activar entorno virtual
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate     # Linux/Mac

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Copiar configuración de ejemplo
copy assets\config\settings.example.json assets\config\settings.json   # Windows
cp assets/config/settings.example.json assets/config/settings.json               # Linux/Mac
```

> Nota: `pytesseract` requiere además tener instalado el motor [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) en el sistema operativo.

## Uso

```bash
# Interfaz de escritorio
python scripts/run_gui.py

# API (documentacion interactiva en http://127.0.0.1:8000/docs)
python scripts/run_api.py
```

Los logs de la aplicación (útiles para depurar errores, especialmente
una vez empaquetada) quedan en `logs/hariment.log`.

## Empaquetado (Windows)

```bash
pip install pyinstaller
python scripts/build_windows.py
```

Genera un ejecutable en `dist/HarimentApp/HarimentApp.exe`. Se usa modo
carpeta (`--onedir`) en vez de un solo archivo porque Whisper y
`transformers` son pesados y `--onedir` arranca mucho más rápido.

## Licencia

Por definir.
