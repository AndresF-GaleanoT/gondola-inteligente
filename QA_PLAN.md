# QA PLAN — Góndola Inteligente (pipeline YOLO + FastAPI + dashboard)

Plan integral de pruebas y validación del sistema de análisis de video:
detección/tracking de personas, permanencia, interacción con producto
(pick-up / put-back), heatmaps, embudo, dashboard y **privacidad estricta**
(anonimización total de rostros, sin reconocimiento facial ni análisis de
emociones).

Herramientas existentes que este plan reutiliza:

| Harness | Comando | Cubre |
|---|---|---|
| Tests de unidad | `python -m unittest discover -s tests -v` | lógica de gesto/persona y API |
| Tests de frontend | `cd frontend; npm test` | mapeo de zonas, límites, layout |
| Validación de embudo vs GT | `python -m app.interfaces.validar_embudo --gt ground_truth/candidatos.json [--tol N --barrido-tol]` | P/R/F1 del pick-up/put-back |
| Chequeo de coherencia | `python -m app.interfaces.validar_embudo` (o con `--metricas`) | invariantes del JSON |
| Suite QA de este plan | `python scripts_qa/qa_privacidad.py`, `qa_metricas.py`, `qa_rendimiento.py` | privacidad, métricas, rendimiento |

Entorno de referencia: Windows + RTX 2060 (CUDA), Python 3.13, `python -m uvicorn backend.main:app`, Vite `:5173`.

Convenciones: cada caso tiene ID único, criterio de aceptación y estado
(`IMPLEMENTADO` = automatizado hoy, `AUTOMATIZABLE` = script planeado,
`MANUAL` = requiere video/inspección visual). Todos los casos críticos de
privacidad están en estado `IMPLEMENTADO` para correr en CI/demo.

---

## 1. Privacidad y Anonimización (Compliance)

Referencia de código: `app/infrastructure/anonimizacion.py`,
`app/use_cases/procesar_video.py:129-134`, `app/config.py:159-142`,
Ley 1581 de 2012 (Colombia).

### PRIV-01 — Difuminado total de rostros en el flujo de render
- **Requisito**: todo frame exportado/previsualizado debe llevar el rostro
  irreconocible (blur fuerte) antes de guardarse o mostrarse.
- **Método**: inspección estática + ejecución. Verificar que `anonimizar()`
  se invoca en `procesar_video.py` ANTES de guardar el frame, y que el
  kernel de blur cubre el ancho del rostro (`TAM_BLUR=61`, `SIGMA_BLUR=24`).
- **Pasos**: 1) `python scripts_qa/qa_privacidad.py`; 2) revisar 3 frames de
  `outputs/vision_frames/` elegidos al azar: el rostro no debe tener facciones
  distinguibles.
- **Esperado**: check OK; los JPEG no permiten identificar a la persona.
- **Criterio**: blur aplicado en el 100% de cajas de cabeza detectadas
  (las cabezas se derivan de `_bbox_cabeza` con suavizado temporal).
- **Estado**: IMPLEMENTADO (check automatizado) + verificación visual MANUAL.

### PRIV-02 — Sin identificadores personales / datos biométricos en estado
- **Requisito**: ni `outputs/metricas_retail.json`, ni los logs, ni la BD
  guardan nombre, cédula, embeddings, rostros ni cualquier dato identificable.
- **Método**: `qa_privacidad.py` barre claves/valores del JSON y de todos los
  archivos de `outputs/`, buscando términos prohibidos y archivos de tipo
  `*face*`, `*embed*`, `*crop*`, `*rostro*`.
- **Esperado**: cero coincidencias; solo sobreviven IDs internos de tracking
  (números opacos sin vínculo a identidad).
- **Criterio**: recuento de hallazgos = 0 al correr la suite.
- **Estado**: IMPLEMENTADO.

### PRIV-03 — Ausencia de modelos de reconocimiento facial
- **Requisito**: el pipeline solo carga pose (`yolov11n-pose.pt`) y producto
  (`yolov8n-producto-mano.pt`); ningún modelo facial.
- **Método**: scan de imports/archivos de modelos en `app/` + validación de
  las rutas `MODELO_POSE`/`MODELO_OBJETOS` (no contienen "face").
- **Esperado**: scan sin coincidencias para `face_recognition|facenet|deepface|
  insightface|embedding|biometric|emotion|sentiment|expression`.
- **Criterio**: suite en verde.
- **Estado**: IMPLEMENTADO.

### PRIV-04 — Sin análisis de emociones ni expresiones faciales
- **Requisito**: ningún clasificador de emociones/expresiones en el pipeline.
- **Método**: scan de `app/` por los términos de PRIV-03 (regex) y revisión
  del árbol de paquetes (`app/domain`, `app/infrastructure`, `app/interfaces`
  no contienen módulo de análisis facial).
- **Esperado**: cero coincidencias.
- **Criterio**: suite en verde.
- **Estado**: IMPLEMENTADO.

### PRIV-05 — Principio de minimización y finalidad (Ley 1581)
- **Requisito**: el sistema solo procesa lo necesario para métricas
  (posición, pose, gesto); no genera rostros, no persiste video original
  (upload se borra al finalizar salvo `CONSERVAR_VIDEOS_SUBIDOS=True`).
- **Método**: verificación de `_iniciar_analisis` (`eliminar_al_final`) en
  `app/interfaces/api.py` + `qa_privacidad.py` (no hay artefactos residuales
  de rostros/embeddings).
- **Esperado/Estado**: verificación documental + check de artefactos.
  IMPLEMENTADO (artefactos), MANUAL (política).

---

## 2. Funcionales de visión por computadora

### VIS-01 — Conteo de personas y tracking (continuidad de trayectorias)
- **Requisito**: contar afluencia y conservar trayectorias coherentes por ID.
- **Método**: sobre `video/videoBase.mp4` comparar inspección humana del
  conteo máximo simultáneo por pasillo vs `detalle_por_persona` (máximo de
  personas vivas por frame) y vs `total_personas`.
- **Datos**: GT de conteo (anotar frame a frame en un segmento de 60 s).
- **Esperado**: diferencia ≤ 1 persona por pasillo; IDs sin saltos bruscos
  de zona.
- **Métrica MOTA/MOTP**: hoy no hay herramienta de asociación vs GT
  (trayectorias están en `detalle_por_persona[].trayectoria` como
  `(frame, x, y)` suavizadas). Se propone `scripts_qa/qa_tracking.py`
  (planeado) que cargue GT de cajas, asocie greedy con IoU/centro y calcule
  MOTA/MOTP con densidades baja/media/alta.
- **Estado**: MANUAL (conteo) + AUTOMATIZABLE (MOTA/MOTP).

### VIS-02 — Mapas de calor
- **Requisito**: el heatmap refleja las zonas de mayor/menor circulación.
- **Método**: 1) con `videoBase.mp4` verificar que la celda más caliente
  corresponde al pasillo más transitado (solapamiento del máximo de la grilla
  96×96 con la zona de mayor `frames_dentro`); 2) escenario controlado:
  video sintético de N personas cruzando solo el pasillo central →
  el centroide del calor debe caer dentro del `Estante_Central`.
- **Esperado**: coherencia ≥ 0.8 entre ranking de calor y ranking de
  presencia por zona.
- **Datos**: `qa_metricas.py` valida rango (0–100), tamaño 96×96 y que no
  esté plano en cero (`chequeo_coherencia` en `validar_embudo.py:194`).
- **Estado**: IMPLEMENTADO (invariantes) + MANUAL/AUTOMATIZABLE (escenario
  controlado sintético).

### VIS-03 — Permanencia (dwell time)
- **Requisito**: distinguir tránsito de detenido con precisión.
- **Método**: capturar un segmento con clientes parados ≥ `QUIETO_PARA_VER`
  frames vs en movimiento; comparar `tiempo_viendo_seg` y
  `dwell_promedio_seg` contra cronómetro humano.
- **Esperado**: error medio ≤ 15% del tiempo anotado; sin personas en
  movimiento marcadas `Inspeccionar Producto` de forma sostenida.
- **Parámetros relevantes**: `QUIETO_PARA_VER=30`, `UMBRAL_QUIETO=20`,
  `SALIDA_VIENDO=45` (movimiento desactiva el conteo).
- **Estado**: MANUAL (segmento anotado) + AUTOMATIZABLE.

### VIS-04 — Interacción con producto (pick-up / put-back)
- **Requisito**: detectar toma/devolución con mínimos falsos positivos ante
  oclusiones parciales y parpadeo del detector.
- **Método (automático)**: validación P/R/F1 vs GT con tolerancia de frames:
  `python -m app.interfaces.validar_embudo --gt ground_truth/candidatos.json
  --barrido-tol` y `--tol 12`. En caso de fallo, revisar el detalle de
  personas con los FP listados.
- **Criterio**: F1 ≥ 0.75 con tol 12 (umbral de demo); el pipeline puede
  fallar el export si se pasa `--umbral-f1` (ver `ground_truth/README.md`).
- **Caso de oclusión**: video sintético donde la mano se oculta por otro
  cliente mientras toma → el gesto debe confirmarse igualmente por
  `MANO_EN_ZONA_CONFIRMA_GESTO=6` o por `POSESION_DISPARA_PICKUP`.
- **Unidad**: `tests/test_persona.py` (toma y devolución misma persona,
  respuesta tardía del detector, destellos sin toma, racha única, segunda
  toma).
- **Estado**: IMPLEMENTADO (unidad) + IMPLEMENTADO (P/R/F1 vs GT) +
  AUTOMATIZABLE (oclusión sintética).

### VIS-05 — Zonas y escalado a resolución real
- **Requisito**: zonas calibradas a 1280×720 se escalan a cualquier
  resolución (polígonos y agarro por punto en `escalar_zonas`,
  `app/config.py:110`).
- **Método**: ejecutar el pipeline con un video 640×360 y otro 1920×1080;
  verificar que `escala_dashboard.x/.y` de cada zona NO cambie (coordenadas
  normalizadas) y que los eventos sigan casando con el mismo GT (mismo
  `f1` a tol ﬁja).
- **Esperado/Estado**: invariante normalizada AUTOMATIZABLE; actualmente
  manual con videos reescalados (`ffmpeg -i video/videoBase.mp4 -vf scale=640:360 video/q360.mp4`).

---

## 3. Integración y embudo de conversión

### INT-01 — Flujo Aproximación → Toma → Devolución/Compra por estante
- **Requisito**: el embudo se calcula por estante y globalmente sin pérdida.
- **Método**: `qa_metricas.py` verifica: ids de zonas = `ZONAS` de config;
  contadores ≥ 0; `tasa_rechazo = put_backs/pick_ups` en [0,1]; totales del
  embudo global = Σ por zona; aviso si `put_backs > pick_ups`; ningún
  pick-up con 0 visitas.
- **Esperado**: todas las invariantes en verde.
- **Estado**: IMPLEMENTADO.

### INT-02 — Sincronización backend → dashboard
- **Requisito**: el dashboard muestra las métricas reales del último análisis,
  no demo mezclado.
- **Método**: `tests/test_api.py` (el `/api/datos` responde 404 si no existe
  el JSON real; `/api/estado` solo estados explícitos). Además: ejecutar
  análisis → `/api/estado` pasa `iniciando→procesando→completado` con
  `progreso_pct` creciente; al terminar `/api/datos` refleja los nuevos
  totales.
- **Esperado**: transición de estados correcta; `elimina visualmente los
  resultados anteriores` (dashboard) verificado a mano.
- **Estado**: IMPLEMENTADO (unit) + MANUAL (E2E navegador).

### INT-03 — Coherencia de métricas exportadas
- **Requisito**: el JSON de métricas es autoconsistente (sanity).
- **Método**: `chequeo_coherencia` de `app/interfaces/validar_embudo.py:161`
  (tasas, visitas, heatmap, zonas no vacías) + `qa_metricas.py`.
- **Estado**: IMPLEMENTADO.

---

## 4. Rendimiento y estrés

Referencias de optimización ya presentes: `PROCESAR_CADA_N=4`,
`IMGSZ=960`, splat gaussiano local del heatmap, blur de rostro 61×61.

### PERF-01 — Fotogramas procesados por segundo (FPS)
- **Método**: `python scripts_qa/qa_rendimiento.py` ejecuta el pipeline y
  reporta tiempo de pared, FPS medio, margen de tiempo real
  (`fps_pipe × PROCESAR_CADA_N / fps`, el pipeline consume la cinta a
  velocidad real cuando ≥ 1.0), uso de GPU (muestreo de `nvidia-smi`),
  RAM del proceso en ejecución, frames anotados generados y tamaño del JSON.
- **Criterio (RTX 2060, 720p)**: `FPS ≥ 10` y margen de tiempo real ≥ 1.0.
  Además registrar en una tabla de regresión: cada build que toque el
  pipeline debe re-correrlo y comparar (en la máquina de referencia con el
  video completo de regresión el recuento se eleva a margen ≥ 1.5).
- **Carga concurrente**: lanzar 2 pipelines en paralelo con videos
  distintos y verificar que el FPS individual no cae > 40% (acumulación
  de colas de CUDA).
- **Estado**: IMPLEMENTADO (benchmark simple) + MANUAL (concurrencia).

### PERF-02 — Memoria RAM/GPU y fugas
- **Método**: `qa_rendimiento.py --vigilar-memoria` muestrea RAM del proceso
  (psutil) y VRAM (nvidia-smi) cada 1 s; ejecutar 1) video completo;
  2) video largo sintético (≥ 10 min) y verificar que RAM/VRAM no crecen
  monótonamente (meseta).
- **Parámetros de mitigación ya activos**: `MAX_TRAYECTORIA_PUNTOS=200`,
  `BORRAR_ID_TRAS=90`, historial por ID, blur de 61×61, index de frames a
  ~5 FPS.
- **Criterio**: sin crecimiento lineal de RAM/VRAM ≥ 20% entre min 2 y final.
- **Estado**: AUTOMATIZABLE (se entrega el esqueleto de `--vigilar-memoria`;
  el video largo sintético es MANUAL/datos).

### PERF-03 — Robustez con videos largos
- **Método**: sintetizar video de 30 min con personas cíclicas
  (`scripts_qa/gen_video_sintetico.py` planeado) y corroborar: recuento
  estable, sin crashes, artefactos de visión sin saturación (heatmap
  promedio no todo-255 gracias a la normalización por frames).
- **Estado**: AUTOMATIZABLE.

---

## 5. Motor de recomendación (módulo deseable)

Referencia: `app/domain/agente.py` (`recomendar_zona`, `recomendar_planograma`).

### REC-01 — La recomendación se deriva solo de métricas observadas
- **Método**: tests de caja blanca con 4 escenarios sintéticos de zonas
  (caliente con rechazo, templada, fría con visitas sin pick, sin visitas).
  Cada salida debe citar números consistentes (visitas, pick, rechazo %).
- **Esperado**: `recomendar_zona` no contradice sus inputs (p.ej. "caliente
  con mejor embudo" solo si `pick ≥ put` y clasificación caliente).
- **Estado**: AUTOMATIZABLE (script de invariantes texto ↔ métricas).

### REC-02 — Planograma (origen/destino/facing) coherente
- **Método**: `recomendar_planograma` debe devolver `origen=fria`, `destino=caliente`
  y `facing_pct` (Σ=100%). Caso sin caliente/fría → `accion=mantener`.
- **Estado**: AUTOMATIZABLE (mismas escenas sintéticas).

### REC-03 — (Extensión) Orquestación de modelos LLM NVIDIA
- **Nota**: el proyecto contempla consultar la API de NVIDIA (NIM) para un
  paso opcional de recomendación aumentada. Si se integra: probar (1) listado
  de modelos con `GET /v1/models`, (2) fallback controlado al agente
  determinista cuando el LLM no responde o no hay clave, (3) latencia < 60 s
  por consulta ensamblada. **Esto es deseable y NO debe bloquear la demo.**

---

## Trazabilidad

| Requisito del usuario | Casos | Estado |
|---|---|---|
| Privacidad total (blur, sin identificación) | PRIV-01..05 | IMPLEMENTADO |
| Sin reconocimiento facial ni emociones | PRIV-03, PRIV-04 | IMPLEMENTADO |
| Conteo y tracking con MOTA/MOTP | VIS-01 | MANUAL/AUTOMATIZABLE |
| Mapas de calor | VIS-02 | IMPLEMENTADO (invariantes) |
| Dwell time | VIS-03 | MANUAL |
| Interacción pick-up/put-back con FPs ante oclusiones | VIS-04 | IMPLEMENTADO |
| Embudo por estante sin pérdida | INT-01, INT-03 | IMPLEMENTADO |
| Sincronización dashboard | INT-02 | IMPLEMENTADO (unit) |
| FPS en carga / memoria / larga duración | PERF-01..03 | IMPLEMENTADO (benchmark) |
| Recomendaciones lógicas | REC-01..02 | AUTOMATIZABLE |

## Ejecución rápida de la regresión (demo/CI)

```powershell
python -m unittest discover -s tests -v
python scripts_qa/qa_privacidad.py
python scripts_qa/qa_metricas.py
python scripts_qa/qa_rendimiento.py
python -m app.interfaces.cli --video video/videoBase.mp4 --no-ventana --gt ground_truth/candidatos.json --umbral-f1 0.7
cd frontend; npm test; npm run lint; npm run build
```