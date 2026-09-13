# PROYECTO HARIMENT

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

En planificación / diseño inicial. Aún no hay código implementado.

## Roadmap

1. Prototipo base: transcripción por micrófono (Whisper) + traducción español → inglés (transformers), con interfaz mínima.
2. Subtítulos en pantalla configurables (posición, estilo, tiempo de permanencia).
3. Captura y traducción de audio del sistema (loopback).
4. Captura de pantalla + OCR para reconocer y traducir texto en imágenes/video.
5. Selección de idioma de entrada/salida, con soporte ampliado (prioridad: portugués y otros idiomas de Latinoamérica).
6. Exposición del motor como API (FastAPI), desacoplando la lógica de la interfaz.
7. Exploración de una interfaz de escritorio más avanzada y una futura versión para teléfono.

## Licencia

Por definir.
