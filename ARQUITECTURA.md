# ARQUITECTURA - RetailVision Edge AI (Góndola Inteligente / ZoneMetrics)

Desarrollo académico grupal — Universidad Santo Tomás, Seccional Tunja (docente asesor
Sergio Arley Puerto Moreno) · retail / visibilidad de inventario.

> Lectura rápida: arquitectura de **capas limpias** (domain puro,
> use cases de orquestación, adaptadores de infraestructura) con un **pipeline
> YOLO de detección de gestos** validado contra ground truth, **privacidad por
> diseño** (Ley 1581 de 2012 – Colombia) y un **dashboard web** de métricas en
> vivo.

---

## 1. Contexto y problema

En retail, la **rotura de stock** no solo es falta de reposición: es producto que
el cliente *interactúa* con la góndola (toma, mira, devuelve) sin que el sistema
lo registre. La solución detecta, a partir de video de cámaras de pasillo:

- **Pick-up** (toma de producto) y **put-back** (devolución) por persona.
- **Zona de interacción** por estante (izquierda / centro / derecha).
- **Heatmap de tráfico** y **recomendaciones** (estantes fríos → calientes).

Los rostros se **anonimizan en el propio pipeline** (blur por keypoints de pose),
de modo que nunca se persiste material biométrico.

---

## 2. Arquitectura por capas

```
                     ┌─────────────────────────────────────────────┐
 FRONTEND (React)    │  domain/(merge/rates/agente)                │
                     │  application/api.js  → GET/POST /api/*       │
                     │  presentation/(dashboard, editor zonas)     │
                     └──────────────────────┬──────────────────────┘
                                            │ HTTP (proxy /api → :8000)
                                            v
 BACKEND (FastAPI)  app/interfaces/api.py   │  subprocess → app/interfaces/cli.py
                    ────────────────────────┴───────────────────────────────
                    │                                                      │
                    v                                                      v
            app/use_cases/                              app/application/
            procesar_video.py (pipeline)                paths.py (rutas)
            exportar_metricas.py (JSON)                 zonas.py (persistencia)
                    │
        ┌───────────┼──────────────┬───────────────┐
        v           v              v               v
  app/domain/   app/domain/   app/domain/   app/infrastructure/
  persona.py    analisis.py   agente.py     vision.py (YOLO+ByteTrack)
  (máquina de   (heatmap,     (recomenda-   anonimizacion.py (blur rostros)
  estados,      contadores    ciones)       dibujo.py (textos en frame)
  gestos pick/  por zona)                                             │
  put-back)     geometria.py / poligonos.py (puras, sin cv2)         │
              │                                                │
              └───────────────────────┬────────────────────────┘
                                      v
                            outputs/metricas_retail.json
                            outputs/vision_frames/ (JPEGs + escena_anotada.mp4)
```

### Reglas de dependencia (respetadas desde la consolidación)

| Capa | Contiene | Depende de |
|---|---|---|
| `app/domain/` | Lógica de negocio pura (finito de estados del cliente, geometría de polígonos, heatmap, agente). `poligonos.py`/`geometria.py` **no importan cv2 ni numpy**. | Nada interno |
| `app/application/` | Persistencia de zonas (`zonas.py`), rutas (`paths.py`). Funciones con parámetros explícitos (rutas/dimensiones) → testeables sin tocar la config real. | `domain/` |
| `app/use_cases/` | Orquestación del pipeline (frames, tracking, anonimización, exportación). | `domain/`, `infrastructure/`, `application/` |
| `app/infrastructure/` | Adaptadores YOLO, ByteTrack, captura de video, blur, dibujo. | Solo librerías externas |
| `app/interfaces/` | FastAPI (API), argparse (CLI), validación P/R/F1 vs GT. | Todas las anteriores |

`app/config.py` quedó como **constantes de ajuste** (umbrales, zonas por defecto,
colores, parámetros de anonimización) + cableado; toda la persistencia de zonas
vive en `application/zonas.py` (write-back al literal y runtime JSON).

---

## 3. Flujo del pipeline (1 análisis)

1. `POST /api/video` sube el video y deja un **fotograma preview** para calibrar
   zonas ANTES de analizar (`estado = listo_para_analizar`, se restaura al
   recargar la página).
2. `POST /api/analizar` lanza el pipeline en un subproceso aislado:
   - Cada `PROCESAR_CADA_N` frames: **pose YOLO + objeto en mano YOLO fine-tune**
     y tracking ByteTrack.
   - `persona.py` clasifica comportamiento e interacción (pick-up / put-back)
     priorizando la muñeca sobre el área de "agarro" de cada zona.
   - `analisis.py` acumula contadores por zona y heatmap de tráfico.
   - `anonimizacion.py` difumina rostros por keypoints de cabeza.
   - Exporta `metricas_retail.json` + fotogramas anotados + `escena_anotada.mp4`.
3. El dashboard consulta `GET /api/datos` y superpone las zonas **en vivo** sobre
   el video (`ZoneOverlay`).

Las zonas se calibran en el editor web (SVG sobre un frame de referencia 1280×720)
y se **escalan a la resolución real** del video.

---

## 4. Configuración y persistencia de zonas

- `_ZONAS_DEFAULT` (literal en `app/config.py`) es la **única fuente de verdad**
  de fábrica.
- El editor web persiste en `config/zonas_runtime.json` (que el pipeline prioriza
  en el import) y hace **write-back** al literal vía AST, conservando el archivo.
- El backend valida cada polígono (vértices enteros, dentro del frame, sin
  autointersección, área > 0) — el frontend replica esa validación **en vivo**
  antes de permitir Guardar.

---

## 5. Calidad y verificación

| Ámbito | Resultado |
|---|---|
| Tests unitarios | **36/36 OK** backend (`python -m unittest discover -s tests -q`) + suite frontend |
| `qa_privacidad.py` | CUMPLE, 0 hallazgos (sin facial/embeddings, outputs limpios) |
| `qa_metricas.py` | 25 invariantes OK (embudo, heatmap 0-100, recomendaciones) |
| `qa_rendimiento.py` | FPS ~24.4, margen de tiempo real **~4.07×** |
| Validación vs GT | P/R/F1 del embudo con `validar_embudo.py` |

## 6. Ejecución

```
powershell -File arrancar.ps1
# backend  → http://localhost:8000
# frontend → http://localhost:5173
```