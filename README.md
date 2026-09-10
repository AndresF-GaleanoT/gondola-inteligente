# Góndola Inteligente — Reto Hackathon

Sistema de visión computacional para retail que analiza el comportamiento de
los compradores frente a las góndolas en tiempo real: clasifica a cada persona
como **Transitando**, **Llegando al estante**, **Inspeccionando el producto**,
**Mano en estante**, **Devolviendo** o con **Producto Adquirido**, todo con
**pixelado de rostros** para cumplir la ley de protección de datos (Ley 1581 de 2012).

El sistema integra un pipeline de detección con un **backend FastAPI** que
sirve las métricas en tiempo real a un **dashboard React**, y permite incluso
ejecutar el análisis YOLO desde el propio frontend.

## El problema

> Las marcas no saben qué pasa frente a sus góndolas: cuánta gente pasa, quién
> se detiene y por cuánto tiempo. Sin ese dato, la distribución y el planograma
> se definen a ciegas. Este sistema convierte el video de la tienda en señales
> accionables de *space management*, sin cámaras inteligentes costosas y sin
> enviar datos a la nube.

## Arquitectura

```
video de tienda → YOLO-pose (cajas + keypoints) + ByteTrack (IDs)   [infrastructure]
                 + YOLO de producto en mano (fine-tune)             [posesión]
                 → máquina de estados: transitando / llegando /      [domain]
                   inspeccionando / mano en estante / devolviendo /
                   producto adquirido
                 → heatmap de tráfico + análisis por zona            [domain]
                 → recomendaciones de planograma (agente)            [domain]
                 → JSON de métricas (outputs/metricas_retail.json)   [use_cases]
                 → backend FastAPI /api/*                            [interfaces]
                 → frontend React (dashboard de storytelling)        [frontend]
```

### Arquitectura en capas (Clean Architecture)

El proyecto se organiza en capas, de dentro hacia fuera, de forma que la lógica
de negocio no depende de los frameworks:

```
app/
├── config.py                 → configuración global (constantes, zonas, ...)  [archivo raíz]
├── application/
│   └── paths.py              → rutas robustas a la raíz del repo
├── domain/                   → entidades y reglas de negocio puras
│   ├── geometria.py          → helpers geométricos (polígonos de zona)
│   ├── persona.py            → máquina de estados de la persona y de la mano
│   ├── analisis.py           → heatmap de tráfico + analizador de zonas
│   └── agente.py             → agente determinista: recomendaciones de planograma
├── use_cases/                → casos de uso (acciones del sistema)
│   ├── procesar_video.py     → orquesta el pipeline de detección
│   └── exportar_metricas.py  → vuelca las métricas a JSON
├── infrastructure/           → adaptadores a frameworks (YOLO, OpenCV, ...)
│   ├── vision.py             → modelos YOLO pose + objetos, el capturador
│   └── anonimizacion.py      → mosaico de rostros (privacidad, Ley 1581)
└── interfaces/               → capa de entrega
    └── api.py                → FastAPI: `/api/estado`, `/api/datos`, ...
```

### Flujo de datos

1. `app/interfaces/cli.py` (adaptador de entrada) ejecuta el caso de uso
   `app/use_cases/procesar_video.py`, que procesa el video y vuelca las métricas
   a `outputs/metricas_retail.json`.
2. `app/interfaces/api.py` (FastAPI) lee ese JSON y lo normaliza para el dashboard.
3. `frontend/` (Vite + React) consume el backend vía proxy `/api`.

### Componentes

| Módulo | Rol |
|--------|-----|
| `app/interfaces/cli.py` | Adaptador de entrada (invoca el caso de uso; opcional `--no-ventana` para headless y `--gt`/`--umbral-f1` para validar tras exportar) |
| `app/config.py` | Constantes: video, zonas, umbrales, modelos, colores |
| `app/domain/geometria.py` | Helpers de geometría / imagen (polígonos de zona) |
| `app/domain/persona.py` | Máquina de estados de persona y de mano (pick-up / put-back) |
| `app/domain/analisis.py` | Heatmap de tráfico + analizador de zonas calientes/frías |
| `app/domain/agente.py` | Agente determinista (sin LLM): `recomendar_zona` y `recomendar_planograma` con `facing_pct` |
| `app/use_cases/procesar_video.py` | Orquestador del pipeline de detección (escala zonas al video real) |
| `app/use_cases/exportar_metricas.py` | Vuelca métricas a JSON para el dashboard (incluye `recomendaciones`) |
| `app/infrastructure/vision.py` | Adaptadores YOLO (pose + objetos) y capturador de video |
| `app/infrastructure/anonimizacion.py` | Mosaico de rostros (privacidad, Ley 1581) |
| `app/interfaces/api.py` | FastAPI: `/api/estado`, `/api/datos`, `POST /api/analizar`, `POST /api/video`, estáticos |
| `backend/main.py` | Punto de arranque de la API (`uvicorn main:app`) |
| `app/interfaces/validar_embudo.py` | Validación del embudo: precision/recall/F1 vs GT + sanity; reutilizable desde el pipeline con umbral de F1 |
| `app/interfaces/extraer_frames_gt.py` | Extrae frames del video (`--cada 0.5`) para anotar el ground truth con un asistente (Gemini) |
| `frontend/src/domain` | Lógica pura del dashboard: `zones.js` / `agente.js` (zonas y agente determinista) y `layout.js` (góndolas, pasillos y mapeo zona→góndola configurable) |
| `frontend/src/application` | Caso de uso de carga de datos (`api.js`, fetch con fallback a `public/datos.json`) |
| `frontend/src/presentation` | Componentes de UI: dashboard (`App.jsx`) y plano 3D cenital (`HabboFloor.jsx`) |

## Instalación

```bash
pip install -r requirements.txt
```

`python-multipart` ya forma parte de `requirements.txt`; no es necesario
instalarlo por separado para subir videos desde el dashboard.

Opcional — aceleración GPU (RTX 2060 u otra NVIDIA) y OpenCV con ventanas:

```bash
pip install "torch==2.13.0+cu126" "torchvision==0.28.0+cu126" --index-url https://download.pytorch.org/whl/cu126
pip uninstall -y opencv-python-headless
```

> ⚠️ Los modelos YOLO (`.pt`) se descargan automáticamente con ultralytics la
> primera vez (`models/yolo11n-pose.pt`), o son generados por el fine-tune
> (`models/yolov8n-producto-mano.pt`).

## Uso

### 1. Ejecutar el pipeline

```bash
python -m app.interfaces.cli                    # con ventana OpenCV en vivo
python -m app.interfaces.cli --no-ventana       # headless (solo métricas)
```

Con ventana, pulsa `q` para salir y `h` para alternar el heatmap en vivo.
`--no-ventana` omite todo el render (no abre OpenCV) y es el modo que usa la API
en segundo plano. Al terminar genera `outputs/metricas_retail.json`.

### 2. Levantar el backend FastAPI

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

Endpoints disponibles:

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/estado` | Estado real (`inactivo`, `iniciando`, `procesando`, `completado` o `error`), progreso y resultado |
| GET | `/api/datos` | Métricas reales del pipeline (zonas normalizadas) |
| POST | `/api/analizar` | Ejecuta `app/interfaces/cli.py` (YOLO) en segundo plano |
| POST | `/api/video` | Sube un video (multipart), lo guarda en `video/subidos/` y dispara el análisis YOLO en segundo plano |
| GET | `/` | Sirve el frontend estático (`dist/` o `public/`) o avisa del modo dev |

### 3. Levantar el frontend (dashboard)

```bash
cd frontend
npm install
npm run dev
```

El frontend corre en `http://localhost:5173` y consume el backend (`:8000`)
mediante el proxy configurado en `frontend/vite.config.js` (todo `/api/*`
se reenvía a `http://localhost:8000`).

> El backend también sirve los estáticos del frontend cuando existe `dist/`:
> con `npm run build` + `uvicorn` basta abrir `http://localhost:8000`.

La subida acepta hasta **500 MB** por defecto. El límite puede modificarse con
`GONDOLA_MAX_VIDEO_MB`. Los videos originales subidos son temporales y se
eliminan al terminar el proceso; únicamente permanecen los fotogramas
anonimizados necesarios para el visor.

Para lanzarlo en un solo clic del backend, `POST /api/analizar` dispara el YOLO
en *background*; el dashboard consulta `/api/estado` para saber cuándo están
listos los datos.

### Fine-tune del detector de producto en mano

Los pesos del detector de producto en mano (`models/yolov8n-producto-mano.pt`) se
generaron con los scripts de entrenamiento del dataset Roboflow `theft-full-2500`
(ver `datasets/`).

## Configuración clave

Todo se ajusta en `app/config.py`:

| Constante | Efecto |
|-----------|--------|
| `VIDEO` | Ruta del video a procesar (`video/videoBase.mp4`) |
| `ZONAS` | Zonas de góndola como **polígonos** (`poligono` + `agarro`) en coordenadas de referencia 1280×720 |
| `ANCHO_REF_ZONAS` / `ALTO_REF_ZONAS` / `escalar_zonas` | Las zonas se **escalan automáticamente** a la resolución real del video (no fijas a 720p) |
| `IMGSZ` / `CONF` / `IOU` / `PROCESAR_CADA_N` | Precisión y rendimiento de la detección |
| `QUIETO_PARA_VER` / `UMBRAL_QUIETO` / `SALIDA_VIENDO` | Tolerancia anti-jitter del clasificador de permanencia |
| `VENTANA_SALIDA_OBJETO` | Frames tras abandonar la zona en los que aún se cuenta el pick-up |
| `OBJETO_OBSERVACIONES_CONFIRMAR` | Observaciones consecutivas de producto necesarias para confirmar una toma y descartar destellos |
| `OBJETO_OBSERVACIONES_REARMAR` | Observaciones sin producto necesarias para permitir una nueva toma de la misma persona |
| `MODELO_OBJETOS` / `CLASES_POSESION` | Detector de producto en mano y clases de posesión (`Object In Hand`, `Product_Hiding`) |
| `CONF_OBJETOS` | Umbral de confianza del detector de objetos en mano |
| `MANO_RADIO` / `MANO_OBJ_TOLERANCIA` | Heurística de posesión: solapamiento o distancia muñeca↔bbox del producto |
| `MANO_OBJ_TOLERANCIA_RELAJADA` | Radio de alcance real de la mano (tolerancia + radio): detecta el agarre sin exigir solape estricto muñeca-caja (los dedos no cubren la caja en planos frontales) |
| `POSESION_DISPARA_PICKUP` | El flanco de posesión (estricta o relajada) dentro de una zona dispara la toma aunque la muñeca no esté formalmente dentro del polígono `agarro` |
| `MANO_EN_ZONA_PARA_RETIRAR` | Frames mínimo con la mano en la zona para contar la interacción |
| `VENTANA_DEDUPE_PICKUP` | Frames tras un pick-up en una zona dentro de los cuales otro pick-up en la misma zona se considera el mismo evento (evita que un único gesto dividido por el tracker se cuente varias veces) |
| `TAM_BLUR` / `SIGMA_BLUR` | Tamaño y desviación del mosaico de privacidad (equilibrio velocidad/anonimizado) |
| `CABEZA_*` | Recorte, suavizado y confianza de la zona facial desde los keypoints de YOLO-pose (`CABEZA_ANCHO`, `CABEZA_ALTO`, `CABEZA_CENTRO_Y`, `SUAVIZADO_CABEZA`, `CONF_CABEZA_KP`) |
| `MAX_TRAYECTORIA_PUNTOS` | Acota la trayectoria registrada por persona (evita que el JSON crezca sin límite) |
| `MOSTRAR_HEATMAP` / `MOSTRAR_RESUMEN` | Overlay del heatmap en pantalla y exportación de métricas al terminar (headless acumula igual el heatmap) |

## Zonas del dashboard

Las zonas del pipeline viven en coordenadas de referencia de **1280×720**
(`ANCHO_REF_ZONAS` / `ALTO_REF_ZONAS`) y se escalan a la resolución real del
video con `escalar_zonas()`. El backend emite los **ids crudos** del pipeline y
solo la web los traduce al nombre visible (`ZONE_NAME_MAP`):

| Zona YOLO | Zona dashboard | Polígono (referencia 1280×720) |
|-----------|----------------|-------------------------------|
| `Estante_Izquierdo` | Góndola izquierda | `[[350,30],[422,30],[300,630],[100,630]]` |
| `Estante_Central` | Góndola central | `[[589,43],[700,40],[762,634],[538,634]]` |
| `Estante_Derecho` | Góndola derecha | `[[830,43],[930,43],[1200,634],[1000,634]]` |

## Métricas exportadas

`outputs/metricas_retail.json` incluye:

- **Embudo de interacción**: total de pick-ups, put-backs y tasa de rechazo.
- **Análisis por zona**: visitas, dwell promedio (seg), presencia, clasificación
  (caliente / templada / fría), pick-ups/put-backs por zona y escala para el dashboard.
- **Recomendaciones del agente**: `recomendaciones.motor`, `recomendaciones.por_zona`
  (diagnóstico accionable por zona) y `recomendaciones.planograma` (texto +
  `facing_pct` = reparto de facing recomendado por zona, 0-100).
- **Zonas calientes y frías**.
- **Heatmap global** promedio de tráfico (grilla), confinado a los pasillos del plano 3D.
- **Detalle por persona** (trayectoria y acciones).

### Analítica visual con Apache ECharts

La navegación lateral incluye una sección independiente de **Analítica** con
cuatro visualizaciones calculadas desde el JSON real del pipeline:

- **Funnel:** tránsito observado → parada → aproximación → toma → toma sin
  devolución observada.
- **Barras:** permanencia promedio por góndola, con una línea de referencia del
  promedio del análisis.
- **Donut:** personas sin toma, con toma sin devolución y con toma + devolución.
- **Sankey:** transiciones consecutivas de los IDs temporales entre góndolas.

La última etapa del funnel no se denomina “compra”: la ausencia de una
devolución en cámara no confirma una venta. Para medir conversión comercial real
sería necesario integrar el resultado con el sistema POS.

### Agente determinista

Ni el backend ni el frontend llaman a un LLM: las recomendaciones se derivan con
reglas puras sobre las métricas del pipeline (`app/domain/agente.py` y su gemelo
local `frontend/src/domain/agente.js` como fallback). Analizan visites, pick-ups,
put-backs, rechazo, dwell, presencia y clasificación de cada zona para responder
*qué reubicar* (categoría fría → zona caliente) y *con qué reparto de facing*.

### Validación del embudo

La validación está **integrada al workflow** y puede exigirse en el propio
comando de exportación con un umbral de F1:

```bash
# Coherencia del JSON exportado (sin GT)
python -m app.interfaces.validar_embudo --metricas outputs/metricas_retail.json

# Precisión / recall / F1 contra un ground truth anotado
python -m app.interfaces.validar_embudo --gt ground_truth/video2.json

# Desde el pipeline: exporta métricas Y valida en el mismo comando
# (--umbral-f1 falla el proceso si el F1 no alcanza el mínimo)
python -m app.interfaces.cli --video video/videoBase.mp4 \
    --gt ground_truth/video2.json --umbral-f1 0.8
```

El ground truth se anota en `ground_truth/` (ver `ground_truth/README.md` y la
plantilla `video2.template.json`): se registra `frame`, `tipo`
(`pick_up`/`put_back`) y zona. Dos vías:

- **Manual**: se pausa el video frame a frame y se anota en
  `ground_truth/video2.json` (anotación independiente del equipo).
- **Con asistente (Gemini)**: `app/interfaces/extraer_frames_gt.py --video video/2.mp4
  --cada 0.5` extrae frames; un asistente los lee y produce
  `ground_truth/video2_gemini.json`. Útil para contrastar la anotación manual.

El pipeline exporta el mismo campo `frame` en `detalle_por_persona[].eventos`
para comparar con tolerancia ajustable (`--tol N`, default 15).

## Privacidad (Ley 1581 de 2012)

- **Desenfoque de rostros** aplicado al frame antes del render. Se centra en los
  keypoints faciales que estima YOLO-pose para cubrir solo la cara real, sin
  tapar las manos ni los brazos al interactuar con el producto.
- No se generan plantillas biométricas. El video original subido se conserva
  solo mientras se analiza y se elimina automáticamente al finalizar.
- Los IDs de seguimiento son efímeros y no re-identifican personas.
- Todo el procesamiento es local (edge), sin envío de video a la nube.

## Datos

- `datasets/` — dataset de Roboflow para el fine-tune (`theft-full-2500`) y
  videos MERL (`MERL_tomas_1`, `Videos_MERL_Shopping_Dataset`). No se suben
  (varios GB).
- `models/` — pesos YOLO (no se suben).
- `video/` — videos de prueba (`.mp4`, no se suben).
- `outputs/` — métricas generadas (no se suben).

## Pruebas y verificación

```bash
# Backend y reglas del dominio
python -m unittest discover -s tests -v

# Frontend
cd frontend
npm test
npm run lint
npm run build
```

## Devs

Proyecto del equipo **AlphaNode** — HackTech 5.0 · 2026.

**Integrantes:**
- Sara Valentina Caicedo Duarte
- Thomas Felipe Cepeda Mogollón
- Andrés Felipe Galeano Téllez
- Yeikov Jared Ramos Sánchez
- Juan David Sandoval Bello
- Silvana Sofía Siza Soriano
- Sarita Toloza Buitrago
- Wendy Mariana Vargas Ramírez

## Se corre backend con y en la carpeta completa
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload
 ## y frontend con npm run dev y en la carpeta \frontend
