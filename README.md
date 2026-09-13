# Góndola Inteligente — HackTech 5.0

> Sistema de visión computacional para retail que convierte el video de la tienda en decisiones de
> *space management*: detecta tomas y devoluciones (pick-up / put-back), mide la permanencia y el
> tráfico por zona, y recomienda cómo redistribuir la góndola. Todo con **privacidad por diseño**
> (Ley 1581 de 2012) y procesamiento 100% local.

## El problema

Las marcas no saben qué pasa frente a sus góndolas: cuánta gente se detiene, quién toma un producto y
lo devuelve, o por dónde circula la gente. Sin ese dato, el planograma se define a ciegas. Este sistema
convierte el video en señales accionables, sin cámaras inteligentes costosas y sin enviar datos a la nube.

## Qué hace

El pipeline clasifica a cada persona como *transitando*, *llegando al estante*, *inspeccionando el
producto*, *mano en estante*, *devolviendo* o *producto adquirido*, y registra los eventos de **toma** y
**devolución** por zona. Los rostros se pixelan en el propio pipeline (no hay reconocimiento facial).

El **dashboard web** ofrece cinco vistas:

| Vista | Qué muestra |
|-------|-------------|
| Lectura general | KPIs (visitantes, tomas, interacción, devolución) y la escena anotada en vivo |
| Analítica | Gráficas interactivas (ECharts): embudo, permanencia, comportamiento y recorridos (Sankey) |
| Plano de tienda | Mapa de actividad y clasificación caliente/templada/fría por góndola |
| Evidencias | Cada evento con su fotograma, zona e ID temporal anónimo |
| Informe | Documento imprimible/PDF con recomendaciones y metodología |

**Editor de zonas**: permite calibrar los polígonos de cada góndola sobre una vista previa del video
(con rostros ya anonimizados). Al guardar, el análisis se **re-ejecuta automáticamente** con las nuevas
zonas y un **overlay en vivo** las dibuja sobre la escena anotada.

## Stack tecnológico

| Capa | Tecnologías |
|------|-------------|
| Visión | ultralytics (YOLO pose + producto-en-mano fine-tuneado), OpenCV, NumPy, ByteTrack |
| Backend | Python 3, FastAPI, uvicorn |
| Frontend | React 19, Vite 8, ECharts, three.js |
| Calidad | unittest, scripts_qa (privacidad / métricas / rendimiento), ESLint |

## Arquitectura

Arquitectura por capas (Clean Architecture): el dominio no depende de frameworks; los adaptadores
aíslan YOLO/OpenCV/HTTP.

```
video de tienda → YOLO-pose + ByteTrack (IDs) + YOLO producto-en-mano   [infrastructure]
                → máquina de estados (pick-up / put-back / permanencia) [domain]
                → heatmap de tráfico + análisis por zona                [domain]
                → recomendaciones de planograma (agente determinista)   [domain]
                → JSON de métricas (outputs/metricas_retail.json)       [use_cases]
                → backend FastAPI /api/*                                [interfaces]
                → dashboard React (5 vistas + editor de zonas)          [frontend]
```

```
app/
├── config.py                  → constantes de ajuste (umbrales, zonas, colores)
├── application/
│   ├── paths.py               → rutas resueltas a la raíz del repo
│   └── zonas.py               → persistencia/validación/escalado de zonas
├── domain/                    → reglas de negocio puras
│   ├── persona.py             → máquina de estados de la persona y de la mano
│   ├── analisis.py            → heatmap de tráfico + analizador de zonas
│   ├── agente.py              → recomendaciones de planograma (determinista)
│   ├── geometria.py           → helpers geométricos puros
│   └── poligonos.py           → validación de polígonos (ray-casting)
├── use_cases/
│   ├── procesar_video.py      → orquesta el pipeline de detección
│   └── exportar_metricas.py   → vuelca las métricas a JSON
├── infrastructure/
│   ├── vision.py              → adaptadores YOLO + captura de video
│   ├── anonimizacion.py       → mosaico de rostros (privacidad)
│   └── dibujo.py              → etiquetas sobre el fotograma
└── interfaces/
    ├── api.py                 → FastAPI (endpoints del dashboard)
    ├── cli.py                 → pipeline por línea de comandos
    └── validar_embudo.py      → validación P/R/F1 contra ground truth
```

## Flujo de uso (desde el dashboard)

1. **Subir un video** → el backend extrae una **vista previa con rostros pixelados**.
2. **Calibrar las zonas** sobre esa vista previa (arrastrar los vértices de cada góndola).
3. **Ejecutar el análisis** → el pipeline YOLO corre en segundo plano.
4. El dashboard consulta `/api/estado` para el progreso y `/api/datos` para las métricas.
5. Al **guardar las zonas de nuevo**, el análisis se **re-ejecuta** automáticamente.

## Instalación

```bash
pip install -r requirements.txt
cd frontend
npm install
```

Opcional — aceleración GPU (RTX 2060 u otra NVIDIA):

```bash
pip install "torch==2.13.0+cu126" "torchvision==0.28.0+cu126" --index-url https://download.pytorch.org/whl/cu126
pip uninstall -y opencv-python-headless
```

Los modelos YOLO (`.pt`) se descargan automáticamente con ultralytics la primera vez
(`models/yolo11n-pose.pt`); el detector fine-tuneado de producto-en-mano se genera con el dataset
Roboflow `theft-full-2500` (ver `datasets/`).

## Uso

Levantar todo de una vez:

```powershell
powershell -ExecutionPolicy Bypass -File .\arrancar.ps1
# Dashboard  → http://localhost:5173
# Backend API → http://localhost:8000
```

O por separado:

```bash
python -m uvicorn backend.main:app --reload --port 8000   # backend
cd frontend && npm run dev                                # frontend
```

### Pipeline por línea de comandos

```bash
python -m app.interfaces.cli                     # con ventana OpenCV en vivo
python -m app.interfaces.cli --no-ventana        # headless (solo métricas)
```

## API

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/estado` | Estado del análisis (`inactivo`, `iniciando`, `procesando`, `completado`, `error`) y progreso |
| GET | `/api/datos` | Métricas reales del pipeline (zonas, embudo, heatmap, recomendaciones) |
| POST | `/api/analizar` | Ejecuta el análisis YOLO en segundo plano |
| POST | `/api/reiniciar` | Reinicia las métricas (borra resultados previos) |
| POST | `/api/video` | Sube un video y prepara la vista previa para calibrar (no analiza aún) |
| GET | `/api/zonas` | Zonas vigentes (polígono + agarro) en el frame de referencia |
| PUT | `/api/zonas` | Persiste las zonas editadas (y re-ejecuta el análisis) |
| POST | `/api/zonas/restablecer` | Vuelve a las zonas de fábrica |
| GET | `/api/vision-frames` | Índice de los fotogramas anotados del visor |
| GET | `/` | Sirve el frontend estático (`dist/`) |

## Configuración clave (`app/config.py`)

| Constante | Efecto |
|-----------|--------|
| `PROCESAR_CADA_N = 4` | Procesa 1 de cada 4 frames (~2× más rápido) sin perder el gesto |
| `IMGSZ` / `IMGSZ_OBJETOS` | Resolución de entrada (960 = equilibrio precisión/costo) |
| `ZONAS` | Zonas de góndola como polígonos (`poligono` + `agarro`) en 1280×720, escaladas al video real |
| `VENTANA_DEDUPE_PICKUP` / `VENTANA_DEVOLUCION` | Deduplicación de eventos y ventana de devolución |
| `TAM_BLUR` / `SIGMA_BLUR` | Mosaico de privacidad (61×61) |
| `MAX_TRAYECTORIA_PUNTOS` | Acota la trayectoria por persona (evita JSON ilimitado) |

## Zonas del dashboard

Coordenadas de referencia (1280×720), escaladas a la resolución real del video. El backend emite los
IDs crudos; la web los traduce a nombres visibles.

| Zona YOLO | Zona dashboard |
|-----------|----------------|
| `Estante_Izquierdo` | Góndola izquierda |
| `Estante_Central` | Góndola central |
| `Estante_Derecho` | Góndola derecha |

## Métricas exportadas

`outputs/metricas_retail.json` incluye: embudo de interacción (pick-ups / put-backs / rechazo),
análisis por zona (visitas, dwell, presencia, clasificación caliente/templada/fría), heatmap global,
recomendaciones del agente (`por_zona` + `planograma` con `facing_pct`) y detalle por persona.

## Privacidad (Ley 1581 de 2012)

- Rostros **pixelados** antes de cualquier render, centrados en los keypoints faciales de YOLO-pose.
- Sin reconocimiento facial, emociones ni datos biométricos.
- IDs de seguimiento **efímeros** (no re-identifican personas).
- Procesamiento **100% local** (edge), sin envío de video a la nube.

## Pruebas y verificación

```bash
python -m unittest discover -s tests          # 36 tests de backend
python scripts_qa/qa_privacidad.py            # auditoría de privacidad (0 hallazgos)
python scripts_qa/qa_metricas.py              # 25 invariantes de métricas
python scripts_qa/qa_rendimiento.py           # benchmark FPS / margen de tiempo real
cd frontend && npm test && npm run build      # tests y build del frontend
```

Resultados de referencia (RTX 2060, 720p): **~24 FPS** de proceso y **~4× margen de tiempo real**.

## Equipo

**AlphaNode · RETAIL LAB — HackTech 5.0 · 2026**

- Andrés Felipe Galeano Téllez
- Juan David Sandoval Bello
- Sara Valentina Caicedo Duarte
- Sarita Toloza Buitrago
- Silvana Sofía Siza Soriano
- Thomas Felipe Cepeda Mogollón
- Wendy Mariana Vargas Ramírez
- Yeikov Jared Ramos Sánchez
