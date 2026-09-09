# INTERFACES / api - capa de entrega FastAPI.
#   GET /api/estado   GET /api/datos   POST /api/analizar   POST /api/video
#   GET /api/vision-frames  (indice de los fotogramas anotados del pipeline)
#   GET /vision-frames/*   (JPEGs anotados, para el "visor" del dashboard)
#   * / sirve el frontend estatico (dist/ o public/).

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from ..application import paths
from ..config import MAX_VIDEO_MB, CONSERVAR_VIDEOS_SUBIDOS
from ..application.paths import JSON_METRICAS, FRONTEND_DIST, \
    FRONTEND_PUBLIC, VIDEO_DIR, VISION_FRAMES, \
    VISION_FRAMES_INDEX, ANALYSIS_STATUS, ANALYSIS_LOG

# Los nombres mostrados ("Góndola izquierda/…") los define la WEB
# (frontend/src/domain/zones.js), no el backend: aqui viajan ids crudos.

app = FastAPI(title="Góndola Inteligente - Backend YOLO")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv(
        "GONDOLA_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

_analisis_lock = threading.Lock()
_estado_analisis = {
    "estado": "inactivo",
    "run_id": None,
    "progreso_pct": 0,
    "mensaje": "Sin análisis en curso.",
    "error": None,
    "iniciado_en": None,
    "finalizado_en": None,
}
_VIDEOS_SUBIDOS = VIDEO_DIR / "subidos"

# Extensiones de video aceptadas.
_EXTENSIONES_VIDEO = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def _ruta_guardado_video(nombre_original: str) -> Path:
    """Devuelve la ruta unica donde guardar un video subido."""
    _VIDEOS_SUBIDOS.mkdir(parents=True, exist_ok=True)
    ext = Path(nombre_original).suffix.lower()
    if ext not in _EXTENSIONES_VIDEO:
        raise HTTPException(status_code=400, detail=f"Formato no soportado: {ext}. "
                            f"Usa {sorted(_EXTENSIONES_VIDEO)}.")
    base = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    return _VIDEOS_SUBIDOS / f"{base}_{Path(nombre_original).name}"


def _actualizar_estado(**cambios):
    with _analisis_lock:
        _estado_analisis.update(cambios)


def _leer_progreso_hijo(run_id):
    ruta = Path(ANALYSIS_STATUS)
    if not ruta.exists() or not run_id:
        return {}
    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if data.get("run_id") == run_id else {}


def _detalle_error_log():
    ruta = Path(ANALYSIS_LOG)
    if not ruta.exists():
        return "El proceso YOLO terminó con error. Consulta outputs/analysis.log."
    try:
        lineas = [l.strip() for l in ruta.read_text(
            encoding="utf-8", errors="replace").splitlines() if l.strip()]
    except OSError:
        return "El proceso YOLO terminó con error."
    return lineas[-1][:500] if lineas else "El proceso YOLO terminó con error."


def _resolver_video_permitido(ruta_video: Optional[str]) -> Path:
    ruta = Path(ruta_video) if ruta_video else Path(paths.VIDEO)
    if not ruta.is_absolute():
        ruta = Path(paths.ROOT) / ruta
    ruta = ruta.resolve()
    try:
        ruta.relative_to(Path(VIDEO_DIR).resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="El video debe estar dentro de la carpeta video del proyecto.",
        ) from exc
    if not ruta.is_file():
        raise HTTPException(status_code=400,
                            detail=f"Video no encontrado: {ruta_video or paths.VIDEO}")
    if ruta.suffix.lower() not in _EXTENSIONES_VIDEO:
        raise HTTPException(status_code=400, detail="Formato de video no soportado.")
    return ruta


def _iniciar_analisis(ruta_video: Path, eliminar_al_final=False):
    run_id = uuid.uuid4().hex
    with _analisis_lock:
        if _estado_analisis["estado"] in {"iniciando", "procesando"}:
            return None
        _estado_analisis.update({
            "estado": "iniciando",
            "run_id": run_id,
            "progreso_pct": 0,
            "mensaje": "Preparando modelos y video.",
            "error": None,
            "video": ruta_video.name,
            "iniciado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "finalizado_en": None,
        })

    # Al comenzar se invalidan los artefactos anteriores; así un fallo nunca
    # termina presentándose como si fueran resultados del video nuevo.
    Path(JSON_METRICAS).unlink(missing_ok=True)
    Path(VISION_FRAMES_INDEX).unlink(missing_ok=True)
    Path(ANALYSIS_STATUS).unlink(missing_ok=True)
    Path(ANALYSIS_LOG).parent.mkdir(parents=True, exist_ok=True)

    def _run(video_capturado=ruta_video, run_capturado=run_id):
        cmd = [
            sys.executable, "-m", "app.interfaces.cli",
            "--no-ventana", "--video", str(video_capturado),
            "--guardar-frames", VISION_FRAMES,
            "--estado-json", ANALYSIS_STATUS,
            "--run-id", run_capturado,
        ]
        _actualizar_estado(estado="procesando",
                           mensaje="Analizando el video con YOLO.")
        try:
            with open(ANALYSIS_LOG, "w", encoding="utf-8") as log:
                proceso = subprocess.run(
                    cmd,
                    cwd=str(paths.ROOT),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            correcto = (proceso.returncode == 0
                         and Path(JSON_METRICAS).is_file()
                         and Path(VISION_FRAMES_INDEX).is_file())
            if correcto:
                _actualizar_estado(
                    estado="completado",
                    progreso_pct=100,
                    mensaje="Análisis completado correctamente.",
                    finalizado_en=time.strftime("%Y-%m-%dT%H:%M:%S"),
                )
            else:
                _actualizar_estado(
                    estado="error",
                    error=_detalle_error_log(),
                    mensaje="No fue posible completar el análisis.",
                    finalizado_en=time.strftime("%Y-%m-%dT%H:%M:%S"),
                )
        except Exception as exc:
            _actualizar_estado(
                estado="error",
                error=f"{type(exc).__name__}: {exc}",
                mensaje="No fue posible iniciar el proceso de análisis.",
                finalizado_en=time.strftime("%Y-%m-%dT%H:%M:%S"),
            )
        finally:
            if eliminar_al_final and not CONSERVAR_VIDEOS_SUBIDOS:
                video_capturado.unlink(missing_ok=True)

    threading.Thread(target=_run, daemon=True).start()
    return dict(_estado_analisis)


def _leer_metricas():
    """Lee exclusivamente el JSON real producido por el pipeline."""
    fuente = Path(JSON_METRICAS)
    if not fuente.exists():
        return None, None
    try:
        with open(fuente, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None, fuente
    return data, fuente


def _normalizar_zonas(analisis_zonas):
    """Transforma analisis_zonas al formato que consume App.jsx."""
    if not isinstance(analisis_zonas, list):
        return []
    resultado = []
    for z in analisis_zonas:
        if not isinstance(z, dict):
            continue
        id_original = z.get("id", "")
        resultado.append({
            "id": id_original,
            "nombre": id_original,
            "clasificacion": z.get("clasificacion", "fria"),
            "visitas": z.get("visitas", 0),
            "pick_ups": z.get("pick_ups", 0),
            "put_backs": z.get("put_backs", 0),
            "rejection_rate": z.get("tasa_rechazo", z.get("rejection_rate", 0)),
            "dwell_promedio_seg": z.get("dwell_promedio_seg", 0),
            "presencia": z.get("presencia", 0),
            "escala_dashboard": z.get("escala_dashboard", {}),
        })
    return resultado


@app.get("/api/estado")
def estado():
    datos, _ = _leer_metricas()
    with _analisis_lock:
        actual = dict(_estado_analisis)
    if actual["estado"] in {"iniciando", "procesando"}:
        progreso = _leer_progreso_hijo(actual.get("run_id"))
        for campo in ("progreso_pct", "frame", "total_frames"):
            if campo in progreso:
                actual[campo] = progreso[campo]
    actual.update({
        "existe_datos": Path(JSON_METRICAS).exists(),
        "json_metricas": str(JSON_METRICAS),
        "generado_en": (datos.get("generado_en") if datos else None),
        "analisis_en_curso": actual["estado"] in {"iniciando", "procesando"},
    })
    return actual


@app.get("/api/datos")
def datos():
    data, _ = _leer_metricas()
    if data is None:
        raise HTTPException(status_code=404, detail="No hay datos aún. Ejecuta /api/analizar.")
    data = dict(data)
    data["analisis_zonas"] = _normalizar_zonas(data.get("analisis_zonas"))
    return data


@app.post("/api/analizar")
def analizar(ruta_video: Optional[str] = None):
    ruta = _resolver_video_permitido(ruta_video)
    iniciado = _iniciar_analisis(ruta)
    if iniciado is None:
        return JSONResponse({"estado": "en_curso"}, status_code=409)
    return JSONResponse({
        "estado": "iniciado",
        "run_id": iniciado["run_id"],
        "mensaje": "Pipeline YOLO ejecutándose en segundo plano.",
    }, status_code=202)


# --- Subida de video ----------------------------------------------------------
@app.post("/api/video")
async def subir_video(archivo: UploadFile = File(...)):
    """Recibe un video, lo guarda y dispara el analisis YOLO en background."""
    with _analisis_lock:
        ocupado = _estado_analisis["estado"] in {"iniciando", "procesando"}
    if ocupado:
        await archivo.close()
        return JSONResponse({"estado": "en_curso"}, status_code=409)

    if not archivo.filename:
        raise HTTPException(status_code=400, detail="No se recibió ningún archivo.")
    ct = (archivo.content_type or "").lower()
    # Se aceptan videos (video/*) y el generico application/octet-stream
    # (que envian curl y algunos navegadores para .mp4/.mov/.mkv). La
    # validacion real por extension la hace _ruta_guardado_video.
    if not (ct.startswith("video/") or ct == "application/octet-stream"):
        raise HTTPException(status_code=400, detail=f"Tipo no soportado: {archivo.content_type}")

    destino = _ruta_guardado_video(archivo.filename)
    limite_mb = max(1, int(os.getenv("GONDOLA_MAX_VIDEO_MB", MAX_VIDEO_MB)))
    limite_bytes = limite_mb * 1024 * 1024
    recibidos = 0
    try:
        with open(destino, "wb") as f:
            while chunk := await archivo.read(1024 * 1024):
                recibidos += len(chunk)
                if recibidos > limite_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"El video supera el límite permitido de {limite_mb} MB.",
                    )
                f.write(chunk)
    except HTTPException:
        destino.unlink(missing_ok=True)
        raise
    except Exception:
        destino.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Error al guardar el video.")
    finally:
        await archivo.close()

    iniciado = _iniciar_analisis(destino, eliminar_al_final=True)
    if iniciado is None:
        destino.unlink(missing_ok=True)
        return JSONResponse({"estado": "en_curso"}, status_code=409)
    return JSONResponse({
        "estado": "iniciado",
        "run_id": iniciado["run_id"],
        "video": destino.name,
        "mensaje": "Video subido. Análisis YOLO ejecutándose en segundo plano.",
    }, status_code=202)


# --- Vision de las gondolas --------------------------------------------------
# El pipeline, al analizar, guarda en VISION_FRAMES los fotogramas anotados
# (zonas, etiquetas y heatmap) como JPEG + un indice JSON de la misma pasada.
# El dashboard los monta como secuencia animada (los navegadores no decodifican
# el codec mp4v del OpenCV, asi que no servimos un <video>).
_paths_vision = Path(VISION_FRAMES)
_paths_vision.mkdir(parents=True, exist_ok=True)


@app.get("/api/vision-frames")
def vision_frames():
    ruta = Path(VISION_FRAMES_INDEX)
    if not ruta.exists():
        raise HTTPException(status_code=404,
                            detail="Aún no hay fotogramas anotados. Ejecuta el análisis.")
    try:
        indice = json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        raise HTTPException(status_code=500, detail="Índice de fotogramas corrupto.")
    # Defensa: solo se listan JPEGs que existen de verdad en disco.
    indice["frames"] = [f for f in indice.get("frames", [])
                        if (_paths_vision / f).is_file()]
    return indice


app.mount("/vision-frames", StaticFiles(directory=str(_paths_vision)),
          name="vision-frames")


# --- Estaticos del frontend ------------------------------------------------
_estaticos = FRONTEND_DIST if FRONTEND_DIST.exists() else FRONTEND_PUBLIC


@app.get("/")
def index():
    index_file = _estaticos / "index.html"
    if _estaticos == FRONTEND_PUBLIC or not index_file.exists():
        return JSONResponse({
            "mensaje": "Backend YOLO activo.",
            "frontend_dev": "http://localhost:5173",
            "api_datos": "/api/datos",
            "api_analizar": "POST /api/analizar",
        })
    return FileResponse(index_file)


if _estaticos.exists():
    app.mount("/", StaticFiles(directory=str(_estaticos), html=True))
