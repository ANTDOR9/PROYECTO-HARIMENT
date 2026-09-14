# Etapas del proyecto

## Etapa 1 — Configuración base del proyecto ✅
Estructura de carpetas, entorno virtual, dependencias iniciales, README y control de versiones (Git/GitHub).

## Etapa 2 — Núcleo de traducción de texto ✅
Integración de `transformers` (modelo Helsinki-NLP u otro) para traducir texto español → inglés. Sin interfaz todavía, probado por consola/scripts.

## Etapa 3 — Reconocimiento de voz por micrófono ✅
Integración de `openai-whisper` para transcribir el micrófono en tiempo real y conectarlo con el núcleo de traducción de la Etapa 2.

## Etapa 4 — Interfaz gráfica mínima con subtítulos ✅
Ventana de escritorio (`customtkinter`/`tkinter`) que muestra el texto transcrito y traducido como subtítulo. Botones básicos de iniciar/detener.

## Etapa 5 — Configuración de subtítulos e idiomas
Panel de configuración: posición/estilo de subtítulos, selección de idioma de entrada y salida, detección automática de idioma.

## Etapa 6 — Audio del sistema (loopback)
Captura del audio que reproduce el propio computador (videos, llamadas) como segunda fuente de entrada, reutilizando el mismo pipeline de transcripción/traducción.

## Etapa 7 — Captura de pantalla + OCR
Función para capturar pantalla, reconocer texto (`pytesseract` o `TrOCR`) y traducirlo, mostrado en el mismo overlay de subtítulos.

## Etapa 8 — Exposición como API
Separar el motor (voz, OCR, traducción) detrás de una API con `FastAPI`, para que la interfaz de escritorio (y a futuro una app móvil) lo consuman como cliente.

## Etapa 9 — Empaquetado y pulido final
Empaquetado ejecutable para Windows, manejo de errores, pruebas, optimización de rendimiento y documentación final. Exploración de interfaz avanzada / versión móvil.
