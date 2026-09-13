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
from .. import config
from ..config import MAX_VIDEO_MB, CONSERVAR_VIDEOS_SUBIDOS
from ..application.paths import JSON_METRICAS, FRONTEND_DIST, \
    FRONTEND_PUBLIC, VIDEO_DIR, VISION_FRAMES, \
    VISION_FRAMES_INDEX, ANALYSIS_STATUS, ANALYSIS_LOG
from ..infrastructure.anonimizacion import anonimizar_preview

# Los nombres mostrados ("Góndola izquierda/…") los define la WEB
# (frontend/src/domain/zones.js), no el backend: aqui viajan ids crudos.

app = FastAPI(title="Góndola Inteligente - Backend YOLO")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv(
        "GONDOLA_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",") if o.strip()],
    allow_methods=["GET", "POST", "PUT"],
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

# Video subido por la web, a la espera del analisis: se muestra un fotograma
# de vista previa para calibrar las zonas y recien POST /api/analizar dispara
# el pipeline (asi las zonas editadas llegan al modelo).
_LISTO_ANALIZAR = None

# Ultimo video analizado: se retiene para poder relanzar el analisis cuando el
# usuario re-edita las zonas (sin tener que subir/elegir el video de nuevo).
_ULTIMO_VIDEO_ANALIZADO = None

# El "ultimo video analizado" tambien se persiste a disco: el estado en memoria
# se pierde al reiniciar el servidor y, sin el, re-editar las zonas no podria
# relanzar el analisis sobre el mismo video. El dashboard revisa este archivo
# para restaurar el analisis al arrancar tras un reinicio.
_REGISTRO_ULTIMO_VIDEO = Path(paths.OUTPUTS) / "ultimo_video_analizado.json"


def _persistir_ultimo_video(ruta_video):
    try:
        _REGISTRO_ULTIMO_VIDEO.parent.mkdir(parents=True, exist_ok=True)
        _REGISTRO_ULTIMO_VIDEO.write_text(
            json.dumps({"video": str(ruta_video)}, ensure_ascii=False),
            encoding="utf-8")
    except OSError:
        pass


def _recuperar_ultimo_video():
    """Devuelve el ultimo video analizado persistido en disco, solo si sigue
    existiendo."""
    try:
        if not _REGISTRO_ULTIMO_VIDEO.is_file():
            return None
        ruta = Path(json.loads(
            _REGISTRO_ULTIMO_VIDEO.read_text(encoding="utf-8")).get("video", ""))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return str(ruta) if ruta.is_file() else None

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


def _info_listo_para_analizar():
    """Informacion del video pendiente de analisis, solo si sigue disponible
    en disco (el dashboard la restaura si se recarga la pagina)."""
    if not _LISTO_ANALIZAR:
        return None
    video = _LISTO_ANALIZAR["video"]
    preview = _LISTO_ANALIZAR["preview"]
    if not video.is_file():
        return None
    return {
        "video": video.name,
        "preview": preview.name if preview and preview.is_file() else None,
    }


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


def _iniciar_analisis(ruta_video: Path, eliminar_al_final=False):
    global _ULTIMO_VIDEO_ANALIZADO
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
        # Retener el video analizado para permitir re-analisis al re-editar
        # zonas: se conserva el ultimo y se descarta el retenido anterior (solo
        # si es un video subido, nunca el video base del proyecto).
        if (_ULTIMO_VIDEO_ANALIZADO is not None
                and _ULTIMO_VIDEO_ANALIZADO != ruta_video
                and not CONSERVAR_VIDEOS_SUBIDOS):
            try:
                _ULTIMO_VIDEO_ANALIZADO.relative_to(_VIDEOS_SUBIDOS)
            except ValueError:
                pass
            else:
                _ULTIMO_VIDEO_ANALIZADO.unlink(missing_ok=True)
        _ULTIMO_VIDEO_ANALIZADO = ruta_video
    _persistir_ultimo_video(ruta_video)

    # Al comenzar se invalidan los artefactos anteriores; así un fallo nunca
    # termina presentándose como si fueran resultados del video nuevo.
    _limpiar_artefactos_previos()
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

    threading.Thread(target=_run, daemon=True).start()
    return dict(_estado_analisis)


def _ultimo_video_disponible():
    """Ultimo video apto para re-analizar: primero el de memoria, y si el
    servidor se reinicio, el persistido en disco."""
    global _ULTIMO_VIDEO_ANALIZADO
    if (_ULTIMO_VIDEO_ANALIZADO is not None
            and Path(_ULTIMO_VIDEO_ANALIZADO).is_file()):
        return _ULTIMO_VIDEO_ANALIZADO
    recuperado = _recuperar_ultimo_video()
    if recuperado is not None:
        _ULTIMO_VIDEO_ANALIZADO = recuperado
        return recuperado
    return None


def _reanalizar_si_corresponde():
    """Relanza el analisis sobre el ultimo video analizado cuando el usuario
    re-edita las zonas. No hace nada si hay un video pendiente de calibrar, si
    ya hay un analisis en curso o si todavia no se analizo ningun video."""
    if _LISTO_ANALIZAR is not None:
        return False
    ruta = _ultimo_video_disponible()
    if ruta is None:
        return False
    with _analisis_lock:
        if _estado_analisis["estado"] in {"iniciando", "procesando"}:
            return False
    return _iniciar_analisis(Path(ruta)) is not None


def _reanalizar_o_invalidar():
    """Al re-editar las zonas, el analisis anterior queda obsoleto: se relanza
    sobre el ultimo video analizado cuando es posible y, si no, se invalidan
    las metricas existentes para que el dashboard no muestre resultados viejos
    con los poligonos nuevos.

    Devuelve (reanalizando, metricas_reiniciadas)."""
    if _reanalizar_si_corresponde():
        return True, False
    if _LISTO_ANALIZAR is not None:
        # Hay un video pendiente de calibrar: la vista previa vive en la misma
        # carpeta que los fotogramas anotados y no debe tocarse aqui. Las
        # metricas que queden se sobrescribiran con el proximo analisis.
        return False, False
    with _analisis_lock:
        en_curso = _estado_analisis["estado"] in {"iniciando", "procesando"}
    if not en_curso and Path(JSON_METRICAS).exists():
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
        "listo_para_analizar": _info_listo_para_analizar(),
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
    global _LISTO_ANALIZAR
    if ruta_video:
        ruta = _resolver_video_permitido(ruta_video)
        eliminar_al_final = False
    elif _LISTO_ANALIZAR:
        ruta = _LISTO_ANALIZAR["video"]
        if _LISTO_ANALIZAR["preview"]:
            _LISTO_ANALIZAR["preview"].unlink(missing_ok=True)
        _LISTO_ANALIZAR = None
        eliminar_al_final = True
    elif (_ULTIMO_VIDEO_ANALIZADO is not None
            and Path(_ULTIMO_VIDEO_ANALIZADO).is_file()):
        ruta = _ULTIMO_VIDEO_ANALIZADO
        eliminar_al_final = False
    else:
        ruta = _resolver_video_permitido(None)
        eliminar_al_final = False
    iniciado = _iniciar_analisis(ruta, eliminar_al_final=eliminar_al_final)
    if iniciado is None:
        return JSONResponse({"estado": "en_curso"}, status_code=409)
    return JSONResponse({
        "estado": "iniciado",
        "run_id": iniciado["run_id"],
        "mensaje": "Pipeline YOLO ejecutándose en segundo plano.",
    }, status_code=202)


# --- Reinicio de metricas web -------------------------------------------------
@app.post("/api/reiniciar")
def reiniciar_analisis():
    """Reinicia las metricas del dashboard: invalida los artefactos del
    analisis actual (metricas, fotogramas, indice, estado) y descarta el video
    pendiente y la referencia al ultimo analizado. Las zonas calibradas se
    conservan. Si hay un analisis en curso responde 409."""
    global _LISTO_ANALIZAR, _ULTIMO_VIDEO_ANALIZADO
    with _analisis_lock:
        en_curso = _estado_analisis["estado"] in {"iniciando", "procesando"}
    if en_curso:
        return JSONResponse({"estado": "en_curso"}, status_code=409)

    if _LISTO_ANALIZAR:
        try:
            if _LISTO_ANALIZAR["preview"]:
                _LISTO_ANALIZAR["preview"].unlink(missing_ok=True)
        except OSError:
            pass
        _LISTO_ANALIZAR = None
    _ULTIMO_VIDEO_ANALIZADO = None
    try:
        _REGISTRO_ULTIMO_VIDEO.unlink(missing_ok=True)
    except OSError:
        pass
    with _analisis_lock:
        _estado_analisis.update({
            "estado": "inactivo",
            "run_id": None,
            "progreso_pct": 0,
            "mensaje": "Sin análisis en curso.",
            "error": None,
            "iniciado_en": None,
            "finalizado_en": None,
        })
    _limpiar_artefactos_previos()
    return {
        "estado": "reiniciado",
        "mensaje": "Métricas y escenas anteriores limpiadas.",
    }


# --- Subida de video ----------------------------------------------------------
@app.post("/api/video")
async def subir_video(archivo: UploadFile = File(...)):
    """Recibe un video, lo guarda y prepara un fotograma de vista previa para
    calibrar las zonas en la web. El analisis YOLO NO arranca aqui: se dispara
    con POST /api/analizar una vez calibradas las zonas."""
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

    global _LISTO_ANALIZAR
    if _LISTO_ANALIZAR:
        if _LISTO_ANALIZAR["preview"]:
            _LISTO_ANALIZAR["preview"].unlink(missing_ok=True)
        _LISTO_ANALIZAR["video"].unlink(missing_ok=True)
    _limpiar_artefactos_previos()
    preview = _extraer_preview(destino)
    _LISTO_ANALIZAR = {"video": destino, "preview": preview}
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
    return [{"id": z["id"], "poligono": z["poligono"],
             "agarro": z["agarro"]} for z in zonas]


@app.get("/api/zonas")
def leer_zonas():
    return {
        "zonas": _zonas_para_api(config.ZONAS),
        "fuente": "runtime" if Path(config.RUNTIME_ZONAS).exists()
        else "default",
        "referencia": [config.ANCHO_REF_ZONAS, config.ALTO_REF_ZONAS],
    }


@app.put("/api/zonas")
def guardar_zonas_api(cuerpo: dict):
    try:
        guardadas = config.guardar_zonas(cuerpo.get("zonas"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    reanalizando, reiniciadas = _reanalizar_o_invalidar()
    return {
        "zonas": _zonas_para_api(guardadas),
        "fuente": "runtime",
        "reanalizando": reanalizando,
        "metricas_reiniciadas": reiniciadas,
    }


@app.post("/api/zonas/restablecer")
def restablecer_zonas_api():
    restablecidas = config.restablecer_zonas()
    reanalizando, reiniciadas = _reanalizar_o_invalidar()
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
