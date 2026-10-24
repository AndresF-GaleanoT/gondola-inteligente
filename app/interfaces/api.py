# INTERFACES / api - capa de entrega FastAPI.
#   GET /api/estado   GET /api/datos   POST /api/analizar   POST /api/video
#   GET/PUT /api/zonas   POST /api/zonas/restablecer
#   GET /api/vision-frames  (indice de los fotogramas anotados del pipeline)
#   GET /vision-frames/*   (JPEGs anotados, para el "visor" del dashboard)
#   * / sirve el frontend estatico (dist/ o public/).
# El flujo web es: subir video -> obtener un fotograma de VISTA PREVIA (con
# rostros anonimizados) -> calibrar las zonas en la web -> POST /api/analizar.
# Asi los poligonos que dibuja el usuario llegan al modelo YOLO en el analisis.

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from ..application import paths
from ..application.analysis_orchestrator import AnalysisOrchestrator
from .. import config
from ..config import MAX_VIDEO_MB, CONSERVAR_VIDEOS_SUBIDOS
from ..application.paths import JSON_METRICAS, FRONTEND_DIST, \
    FRONTEND_PUBLIC, VIDEO_DIR, VISION_FRAMES, \
    VISION_FRAMES_INDEX, ANALYSIS_STATUS, ANALYSIS_LOG
from ..infrastructure.anonimizacion import anonimizar_preview
from ..infrastructure.pipeline_runner import SubprocessPipelineRunner

# Los nombres mostrados ("Góndola izquierda/…") los define la WEB
# (frontend/src/domain/zones.js), no el backend: aqui viajan ids crudos.

app = FastAPI(title="RetailVision Edge AI - Backend YOLO")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv(
        "GONDOLA_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",") if o.strip()],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)

_VIDEOS_SUBIDOS = VIDEO_DIR / "subidos"

# El estado del analisis en curso, el video pendiente de calibrar y el ultimo
# video analizado vivian como variables de este modulo (globals mutados con
# `global` desde cada handler). Ahora ese estado esta encapsulado en un
# AnalysisOrchestrator (application/analysis_orchestrator.py) inyectado via
# Depends(): cada handler lo recibe como parametro en vez de tocar globals,
# y los tests pueden anular `obtener_orquestador` (app.dependency_overrides)
# para aislar el estado entre casos sin poke-ar atributos del modulo.
_pipeline_runner = SubprocessPipelineRunner(
    proyecto_root=paths.ROOT,
    vision_frames_dir=VISION_FRAMES,
    json_metricas_path=JSON_METRICAS,
    vision_frames_index_path=VISION_FRAMES_INDEX,
    analysis_status_path=ANALYSIS_STATUS,
    analysis_log_path=ANALYSIS_LOG,
)

orquestador = AnalysisOrchestrator(
    ejecutor=_pipeline_runner.ejecutar,
    registro_ultimo_video=Path(paths.OUTPUTS) / "ultimo_video_analizado.json",
    videos_subidos_dir=_VIDEOS_SUBIDOS,
    # lambda (no la referencia directa) para que un test que parchea
    # `api._limpiar_artefactos_previos` siga afectando al orquestador: el
    # nombre se resuelve en el namespace del modulo en cada llamada, no al
    # construir el orquestador.
    limpiar_artefactos=lambda: _limpiar_artefactos_previos(),
    conservar_videos_subidos=CONSERVAR_VIDEOS_SUBIDOS,
)


def obtener_orquestador() -> AnalysisOrchestrator:
    return orquestador


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


def _extraer_preview(video: Path):
    """Extrae un fotograma del video como vista previa para calibrar las zonas
    en la web antes del analisis, con los rostros ANONIMIZADOS (privacidad).
    Busca ~2s dentro del video; si falla o es muy corto usa el primer
    fotograma. Devuelve None si no se pudo extraer (la subida igual queda
    lista para analizar)."""
    try:
        import cv2
    except Exception:
        return None
    cap = cv2.VideoCapture(str(video))
    try:
        if not cap.set(cv2.CAP_PROP_POS_MSEC, 2000):
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, frame = cap.read()
        if not ok or frame is None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        if not ok or frame is None:
            return None
        anonimizar_preview(frame)
        _paths_vision.mkdir(parents=True, exist_ok=True)
        nombre = f"preview_{uuid.uuid4().hex[:8]}.jpg"
        ruta = _paths_vision / nombre
        if not cv2.imwrite(str(ruta), frame, [cv2.IMWRITE_JPEG_QUALITY, 88]):
            return None
        return ruta
    finally:
        cap.release()


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


def _limpiar_artefactos_previos():
    """Borra metricas, indice, estado y fotogramas del analisis anterior para
    que una nueva subida/analisis no mezcle resultados viejos con los nuevos.

    En Windows un archivo puede estar momentaneamente bloqueado (reproductor de
    video abierto, antivirus): se limpia lo que se pueda y el resto lo
    sobrescribe el nuevo analisis en cuanto quede libre.
    """
    for ruta in (Path(JSON_METRICAS), Path(VISION_FRAMES_INDEX),
                 Path(ANALYSIS_STATUS)):
        try:
            ruta.unlink(missing_ok=True)
        except OSError:
            pass
    ruta = Path(VISION_FRAMES)
    if ruta.exists():
        shutil.rmtree(ruta, ignore_errors=True)
    ruta.mkdir(parents=True, exist_ok=True)


def _reanalizar_o_invalidar(orq: AnalysisOrchestrator):
    """Al re-editar las zonas, el analisis anterior queda obsoleto: se relanza
    sobre el ultimo video analizado cuando es posible (orq.reanalizar_si_corresponde,
    que internamente llama a orq.iniciar_analisis) y, si no, se invalidan las
    metricas existentes para que el dashboard no muestre resultados viejos con
    los poligonos nuevos.

    Devuelve (reanalizando, metricas_reiniciadas)."""
    if orq.reanalizar_si_corresponde():
        return True, False
    if orq.listo_analizar is not None:
        # Hay un video pendiente de calibrar: la vista previa vive en la misma
        # carpeta que los fotogramas anotados y no debe tocarse aqui. Las
        # metricas que queden se sobrescribiran con el proximo analisis.
        return False, False
    if not orq.en_curso() and Path(JSON_METRICAS).exists():
        # Sin video para re-procesar pero con metricas obsoletas: se limpian
        # los artefactos para forzar a regenerar el analisis.
        _limpiar_artefactos_previos()
        return False, True
    return False, False


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
    for zona in analisis_zonas:
        if not isinstance(zona, dict):
            continue
        id_original = zona.get("id", "")
        resultado.append({
            "id": id_original,
            "nombre": id_original,
            "clasificacion": zona.get("clasificacion", "fria"),
            "visitas": zona.get("visitas", 0),
            "pick_ups": zona.get("pick_ups", 0),
            "put_backs": zona.get("put_backs", 0),
            "rejection_rate": zona.get("tasa_rechazo", zona.get("rejection_rate", 0)),
            "dwell_promedio_seg": zona.get("dwell_promedio_seg", 0),
            "presencia": zona.get("presencia", 0),
            "escala_dashboard": zona.get("escala_dashboard", {}),
        })
    return resultado


@app.get("/api/estado")
def estado(orq: AnalysisOrchestrator = Depends(obtener_orquestador)):
    datos, _ = _leer_metricas()
    actual = orq.estado_actual()
    if actual["estado"] in {"iniciando", "procesando"}:
        progreso = _pipeline_runner.leer_progreso(actual.get("run_id"))
        for campo in ("progreso_pct", "frame", "total_frames"):
            if campo in progreso:
                actual[campo] = progreso[campo]
    actual.update({
        "existe_datos": Path(JSON_METRICAS).exists(),
        "json_metricas": str(JSON_METRICAS),
        "generado_en": (datos.get("generado_en") if datos else None),
        "analisis_en_curso": actual["estado"] in {"iniciando", "procesando"},
        "listo_para_analizar": orq.info_listo_para_analizar(),
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
def analizar(ruta_video: Optional[str] = None,
            orq: AnalysisOrchestrator = Depends(obtener_orquestador)):
    if ruta_video:
        ruta = _resolver_video_permitido(ruta_video)
    elif orq.listo_analizar:
        ruta = orq.listo_analizar["video"]
        if orq.listo_analizar["preview"]:
            orq.listo_analizar["preview"].unlink(missing_ok=True)
        orq.listo_analizar = None
    elif (orq.ultimo_video_analizado is not None
            and Path(orq.ultimo_video_analizado).is_file()):
        ruta = orq.ultimo_video_analizado
    else:
        ruta = _resolver_video_permitido(None)
    iniciado = orq.iniciar_analisis(ruta)
    if iniciado is None:
        return JSONResponse({"estado": "en_curso"}, status_code=409)
    return JSONResponse({
        "estado": "iniciado",
        "run_id": iniciado["run_id"],
        "mensaje": "Pipeline YOLO ejecutándose en segundo plano.",
    }, status_code=202)


# --- Reinicio de metricas web -------------------------------------------------
@app.post("/api/reiniciar")
def reiniciar_analisis(orq: AnalysisOrchestrator = Depends(obtener_orquestador)):
    """Reinicia las metricas del dashboard: invalida los artefactos del
    analisis actual (metricas, fotogramas, indice, estado) y descarta el video
    pendiente y la referencia al ultimo analizado. Las zonas calibradas se
    conservan. Si hay un analisis en curso responde 409."""
    if orq.en_curso():
        return JSONResponse({"estado": "en_curso"}, status_code=409)
    orq.reiniciar()
    _limpiar_artefactos_previos()
    return {
        "estado": "reiniciado",
        "mensaje": "Métricas y escenas anteriores limpiadas.",
    }


# --- Subida de video ----------------------------------------------------------
@app.post("/api/video")
async def subir_video(archivo: UploadFile = File(...),
                      orq: AnalysisOrchestrator = Depends(obtener_orquestador)):
    """Recibe un video, lo guarda y prepara un fotograma de vista previa para
    calibrar las zonas en la web. El analisis YOLO NO arranca aqui: se dispara
    con POST /api/analizar una vez calibradas las zonas."""
    if orq.en_curso():
        await archivo.close()
        return JSONResponse({"estado": "en_curso"}, status_code=409)

    if not archivo.filename:
        raise HTTPException(status_code=400, detail="No se recibió ningún archivo.")
    tipo_contenido = (archivo.content_type or "").lower()
    # Se aceptan videos (video/*) y el generico application/octet-stream
    # (que envian curl y algunos navegadores para .mp4/.mov/.mkv). La
    # validacion real por extension la hace _ruta_guardado_video.
    if not (tipo_contenido.startswith("video/") or tipo_contenido == "application/octet-stream"):
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

    if orq.listo_analizar:
        if orq.listo_analizar["preview"]:
            orq.listo_analizar["preview"].unlink(missing_ok=True)
        orq.listo_analizar["video"].unlink(missing_ok=True)
    _limpiar_artefactos_previos()
    preview = _extraer_preview(destino)
    orq.listo_analizar = {"video": destino, "preview": preview}
    return JSONResponse({
        "estado": "listo_para_analizar",
        "video": destino.name,
        "preview": preview.name if preview else None,
        "mensaje": "Video cargado. Calibra las zonas sobre la vista previa "
                   "y luego ejecuta el análisis.",
    }, status_code=200)


# --- Editor de zonas ----------------------------------------------------------
# GET /api/zonas devuelve las zonas vigentes (poligono + agarro) en el frame de
# referencia (1280x720) y su origen. PUT /api/zonas las persiste en
# config/zonas_runtime.json y las escribe de vuelta en app/config.py; POST
# /api/zonas/restablecer vuelve a las de fabrica.

def _zonas_para_api(zonas):
    return [{"id": zona["id"], "poligono": zona["poligono"],
             "agarro": zona["agarro"]} for zona in zonas]


@app.get("/api/zonas")
def leer_zonas():
    return {
        "zonas": _zonas_para_api(config.zona_repository.obtener()),
        "fuente": config.zona_repository.fuente(),
        "referencia": [config.ANCHO_REF_ZONAS, config.ALTO_REF_ZONAS],
    }


@app.put("/api/zonas")
def guardar_zonas_api(cuerpo: dict,
                      orq: AnalysisOrchestrator = Depends(obtener_orquestador)):
    try:
        guardadas = config.guardar_zonas(cuerpo.get("zonas"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    reanalizando, reiniciadas = _reanalizar_o_invalidar(orq)
    return {
        "zonas": _zonas_para_api(guardadas),
        "fuente": "runtime",
        "reanalizando": reanalizando,
        "metricas_reiniciadas": reiniciadas,
    }


@app.post("/api/zonas/restablecer")
def restablecer_zonas_api(orq: AnalysisOrchestrator = Depends(obtener_orquestador)):
    restablecidas = config.restablecer_zonas()
    reanalizando, reiniciadas = _reanalizar_o_invalidar(orq)
    return {
        "zonas": _zonas_para_api(restablecidas),
        "fuente": "default",
        "reanalizando": reanalizando,
        "metricas_reiniciadas": reiniciadas,
    }


# --- Vision de las gondolas --------------------------------------------------
# El pipeline, al analizar, guarda en VISION_FRAMES los fotogramas anotados
# (zonas, etiquetas y heatmap) como JPEG + un indice JSON de la misma pasada.
# Si ffmpeg esta disponible tambien codifica "escena_anotada.mp4" (H.264,
# decodificable por el navegador) y el indice lo referencia en "video"; si no,
# el dashboard replica la secuencia como animacion de fotogramas.
_paths_vision = Path(VISION_FRAMES)
_paths_vision.mkdir(parents=True, exist_ok=True)
# Las previews son efimeras: al arrancar/reiniciar se limpian las huerfanas
# que pudieran haber quedado de procesos anteriores.
for _p in _paths_vision.glob("preview_*.jpg"):
    try:
        _p.unlink(missing_ok=True)
    except OSError:
        pass


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
