# Arquitectura de PROYECTO HARIMENT

## Vision general

El proyecto separa por completo el **motor** (voz, OCR, traduccion) de
sus **clientes** (interfaz de escritorio y API). Ambos clientes llaman
exactamente al mismo codigo en `src/hariment/`, asi que una mejora al
motor (por ejemplo, un mejor modelo de traduccion) beneficia a los dos
sin duplicar logica.

```
                    ┌────────────────────────┐
   Microfono ──────►│                        │
                    │   hariment.audio       │
   Audio del        │   (microfono.py,       │
   sistema ────────►│   sistema_loopback.py) │──┐
                    └────────────────────────┘  │
                                                  │  texto transcrito
   Captura de        ┌───────────────────────┐  │
   pantalla ────────►│    hariment.ocr        │──┤
                    │  (captura_pantalla.py, │  │
                    │  reconocimiento_texto) │  │
                    └───────────────────────┘  │
                                                  ▼
                                    ┌─────────────────────────┐
                                    │  hariment.translation    │
                                    │      (traductor.py)      │
                                    └─────────────────────────┘
                                                  │
                                                  ▼ texto traducido
                        ┌─────────────────────────────────────┐
                        │                                     │
                ┌───────▼────────┐                  ┌─────────▼────────┐
                │  hariment.gui   │                  │  hariment.api     │
                │  (app.py)       │                  │  (main.py,        │
                │  interfaz de    │                  │  FastAPI)         │
                │  escritorio     │                  │  para otros       │
                │                 │                  │  clientes/futuro  │
                └─────────────────┘                  │  app movil        │
                                                       └───────────────────┘
```

## Modulos y responsabilidades

- **`hariment.audio`** — captura audio (microfono o sistema) y lo
  transcribe con Whisper. Ambas clases (`TranscriptorMicrofono`,
  `TranscriptorAudioSistema`) comparten la misma estrategia de
  segmentacion por energia/silencio y la misma interfaz
  (`iniciar()`, `detener()`, `esta_escuchando`), para que quien las usa
  no necesite saber cual esta activa.
- **`hariment.ocr`** — captura pantalla (`captura_pantalla.py`) y
  reconoce el texto de una imagen (`reconocimiento_texto.py`), con dos
  motores intercambiables (`pytesseract` / `trocr`).
- **`hariment.translation`** — traduce texto entre idiomas usando
  modelos de `transformers`, con carga perezosa y cache de modelos por
  par de idiomas.
- **`hariment.gui`** — interfaz de escritorio (Tkinter/customtkinter):
  conecta audio/OCR con el traductor y muestra el resultado como
  subtitulo; `configuracion.py` gestiona la configuracion persistente
  del usuario (idiomas, estilo de subtitulos, fuente de entrada).
- **`hariment.api`** — expone el mismo motor via HTTP (FastAPI), para
  cualquier cliente que no sea la interfaz de escritorio (una futura
  app movil, un script, otra interfaz).

## Decisiones de diseño

- **Carga perezosa de modelos pesados** (Whisper, `transformers`): se
  cargan la primera vez que realmente se usan, no al iniciar la app, asi
  que arrancar la interfaz o la API es instantaneo aunque el usuario
  nunca use, por ejemplo, el OCR.
- **Todo en hilos aparte de la interfaz**: la captura de audio corre en
  un hilo daemon propio y se comunica con la ventana principal via una
  `queue.Queue`, revisada periodicamente con `Tk.after()`. Tkinter no es
  thread-safe, asi que nunca se toca un widget directamente desde otro
  hilo.
- **Configuracion como datos, no como codigo**: todo lo que el usuario
  puede cambiar (idiomas, estilo de subtitulos, fuente de entrada, motor
  de OCR, host/puerto de la API) vive en `assets/config/settings.json`
  (JSON plano), leido por `GestorConfiguracion` y reutilizado tanto por
  la interfaz como por el script de la API.
- **Motor de traduccion/OCR intercambiable**: se eligio un patron simple
  (un parametro `motor`/par de idiomas que selecciona una funcion de
  carga) en vez de una arquitectura de plugins mas compleja, porque el
  proyecto solo necesita alternar entre 2-3 opciones conocidas de
  antemano, no cargar motores de terceros dinamicamente.

## Flujo de una traduccion en vivo (ejemplo: microfono)

1. `TranscriptorMicrofono` detecta que hay voz por energia de la señal.
2. Al detectar silencio (o pasar el limite de duracion), corta la frase
   y la transcribe con Whisper.
3. El resultado (`SegmentoTranscrito`) se pone en la cola de eventos de
   la interfaz.
4. `AplicacionHariment._programar_revision_de_cola()` (corriendo en el
   hilo principal, via `after()`) saca el segmento de la cola.
5. Se traduce el texto con `Traductor.traducir()`.
6. Se actualiza la barra de subtitulos y el historial.

El mismo flujo, sin la interfaz, es lo que expone `POST /audio/transcribir`
en la API: recibe un archivo de audio en vez de escuchar en vivo, pero
llama a las mismas piezas (Whisper + `Traductor`).
