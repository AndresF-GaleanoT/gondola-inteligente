# USE CASES / procesar_video - orquesta el pipeline YOLO (video + modelos,
# estados de persona, analizador de zonas, heatmap, anonimizacion, metricas).

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from .. import config as cfg
from ..config import (COLOR_ZONA, MOSTRAR_HEATMAP, MOSTRAR_RESUMEN,
                      PROCESAR_CADA_N, VIDEO, VISION_FPS_OBJETIVO)
from ..domain.analisis import HeatmapTrafico, AnalizadorZonas
from ..domain.detector_objetos import DetectorDeObjetos
from ..domain.detector_personas import DetectorDePersonas
from ..domain.persona import procesar_personas
from ..infrastructure.anonimizacion import _cajas_cabeza_rastreadas, anonimizar
from ..infrastructure.dibujo import poner_texto
from ..infrastructure.vision import DetectorPoseYObjetos, CapturaVideo
from .exportar_metricas import exportar_json_metricas


class DetectorDeEscena(DetectorDePersonas, DetectorDeObjetos, Protocol):
    """Puerto combinado que necesita este caso de uso: deteccion+tracking de
    personas Y deteccion de objetos en posesion sobre el mismo fotograma.
    `infrastructure/vision.py:DetectorPoseYObjetos` implementa ambos (tipado
    estructural: no hace falta heredar de este Protocol, basta con tener los
    metodos). Un test puede pasar cualquier objeto con esos dos metodos, sin
    cargar YOLO de verdad."""


def _ffmpeg():
    """Devuelve la ruta de ffmpeg o None si no esta disponible.

    Prioriza el binario estatico de imageio-ffmpeg (SIP, sin dependencias de
    DLLs "rotas" del entorno) y si no busca en PATH/conda.
    """
    from shutil import which
    try:
        import imageio_ffmpeg
        ruta_empaquetada = imageio_ffmpeg.get_ffmpeg_exe()
        if Path(ruta_empaquetada).is_file():
            return str(ruta_empaquetada)
    except (ImportError, RuntimeError, OSError):
        pass
    for candidato in ("ffmpeg", str(Path(sys.executable).parent / "ffmpeg"),
                      str(Path(sys.executable).parents[1] / "Library" / "bin"
                          / "ffmpeg")):
        ruta_encontrada = which(candidato) or (candidato
                                    if Path(candidato).is_file() else None)
        if ruta_encontrada:
            return ruta_encontrada
    return None


def _procesar_frame(detector: DetectorDeEscena, frame, fi, personas_estado,
                    analizador, zonas, historial, heatmap=None):
    """Deteccion + actualizacion de estado de un frame procesado.

    Devuelve (results, etiquetas). Ordena el tracking de personas ANTES que el
    detector de "objeto en mano": sin personas no puede haber objeto en mano,
    asi que se ahorra esa inference en los frames vacios (suele ser la mayoria
    de un video de pasillo/caja).
    """
    results = detector.rastrear_personas(frame)
    cajas = results[0].boxes
    n_personas = 0
    if cajas is not None and cajas.xyxy is not None:
        n_personas = len(cajas.xyxy)
        if heatmap is not None:
            heatmap.acumular(cajas.xyxy.cpu().numpy())

    if n_personas:
        cajas_objetos = detector.detectar_objetos(frame)
    else:
        cajas_objetos = np.empty((0, 4))

    etiquetas = procesar_personas(results, cajas_objetos, personas_estado,
                                  analizador, fi, zonas=zonas,
                                  historial=historial)
    return results, etiquetas


def procesar_video(mostrar_ventana=True, ruta_video=None, emitir_marco=None,
                   guardar_frames=None, emitir_progreso=None):
    """Ejecuta el pipeline completo y devuelve un dict-resumen de metricas.

    `ruta_video` permite procesar un video distinto al configurado por
    defecto (por ejemplo uno subido desde la web). Si es None se usa `VIDEO`.

    `emitir_marco` es un callback opcional que recibe cada fotograma anotado
    (anonimizado, con plot YOLO, zonas y etiquetas) aunque no haya ventana;
    lo usa la API para servicios en vivo.

    `guardar_frames` es una carpeta opcional donde guardar los fotogramas ya
    anotados (zonas, agarro, etiquetas y heatmap) como JPEG + un indice JSON
    junto a la carpeta; el dashboard los reproduce como secuencia animada
    ("vision de las gondolas").
    """
    detector: DetectorDeEscena = DetectorPoseYObjetos()
    cap = CapturaVideo(ruta_video=ruta_video or VIDEO)

    fps = cap.fps
    total_frames = cap.total_frames
    # La inferencia se hace cada PROCESAR_CADA_N frames, pero el visor se
    # limita a VISION_FPS_OBJETIVO para no producir miles de JPEG innecesarios.
    saltos_por_imagen = max(1, round(fps / VISION_FPS_OBJETIVO /
                                     PROCESAR_CADA_N))
    paso_guardado = saltos_por_imagen * PROCESAR_CADA_N
    personas_estado = {}
    # Personas que el tracker dejo de ver (BORRAR_ID_TRAS): se conservan aqui
    # para no perder sus eventos/trayectoria del detalle por persona.
    personas_historial = {}
    cabeza_suave = {}
    analizador = None
    zonas = cfg.ZONAS
    frames_guardados = []

    if guardar_frames:
        # Carpeta limpia: si de un analisis previo quedaron mas JPEGs que del
        # actual, los sobrantes seguirian colgando del indice.
        carpeta = Path(guardar_frames)
        if carpeta.exists():
            shutil.rmtree(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)

    fi = 0
    ultimo_progreso = 0
    ultimo_marco = None
    # El heatmap como overlay solo tiene sentido con render visual (ventana,
    # stream o fotogramas guardados); en headless puro se acumula para las
    # metricas.
    render_visual = mostrar_ventana or emitir_marco is not None \
        or guardar_frames is not None
    mostrar_heatmap = MOSTRAR_HEATMAP and render_visual
    heatmap = None

    while True:
        ok, frame = cap.leer()
        if not ok:
            break
        fi += 1

        if emitir_progreso is not None and (
                fi == 1 or fi - ultimo_progreso >= max(1, round(fps))):
            emitir_progreso(fi, total_frames)
            ultimo_progreso = fi

        if ultimo_marco is None or (fi - 1) % PROCESAR_CADA_N == 0:
            if heatmap is None:
                # Primer frame procesado: se fija la resolucion real del video y
                # se escalan las zonas (calibradas a 1280x720) a ese tamaño.
                cfg.W_VIDEO, cfg.H_VIDEO = frame.shape[1], frame.shape[0]
                zonas = cfg.escalar_zonas(frame.shape[1], frame.shape[0])
                analizador = AnalizadorZonas(zonas)
                heatmap = HeatmapTrafico(frame.shape[1], frame.shape[0])

            results, etiquetas = _procesar_frame(
                detector, frame, fi, personas_estado, analizador, zonas,
                personas_historial, heatmap=heatmap)

            if render_visual:
                # Render para pantalla y/o stream: anonimizado, plot de YOLO,
                # zonas, etiquetas y overlay del heatmap. En headless puro se
                # omite (no se abre cv2.imshow ni se paga ese coste visual).
                cajas_cabeza = _cajas_cabeza_rastreadas(results, cabeza_suave)
                anonimizar(frame, cajas_cabeza)

                marco = results[0].plot(img=frame, kpt_line=False, kpt_radius=0)

                for zona in zonas:
                    vertices = np.array(zona["poligono"], dtype=np.int32)
                    cv2.polylines(marco, [vertices], True, COLOR_ZONA, 2)
                    cv2.putText(marco, zona["id"], (int(vertices[:, 0].min()) + 4,
                                                  int(vertices[:, 1].min()) + 16),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_ZONA, 1)

                for pos, texto, color in etiquetas:
                    poner_texto(marco, pos, texto, color)

                if mostrar_heatmap:
                    marco = heatmap.overlay(marco)

                if guardar_frames and (fi - 1) % paso_guardado == 0:
                    nombre = f"f_{fi:05d}.jpg"
                    guardado = cv2.imwrite(
                        str(Path(guardar_frames) / nombre), marco,
                        [cv2.IMWRITE_JPEG_QUALITY, 80],
                    )
                    if guardado:
                        frames_guardados.append(nombre)

                if mostrar_ventana:
                    ultimo_marco = marco
                else:
                    # Headless con render (guardar_frames/emitir_marco): marca
                    # el frame como "ya procesado" para que PROCESAR_CADA_N no
                    # se rompa y el pipeline no duplique trabajo.
                    ultimo_marco = frame
                if emitir_marco is not None:
                    emitir_marco(marco)
            else:
                ultimo_marco = frame

        if mostrar_ventana:
            cv2.imshow("Deteccion Robusta - Pose + Objetos", ultimo_marco)
            tecla = cv2.waitKey(1) & 0xFF
            if tecla == ord("q"):
                break
            if tecla == ord("h"):
                mostrar_heatmap = not mostrar_heatmap

    cap.liberar()
    cv2.destroyAllWindows()

    if emitir_progreso is not None:
        emitir_progreso(total_frames or fi, total_frames or fi)

    if guardar_frames:
        # Indice que consume el dashboard: lista de fotogramas y la cadencia
        # real del video (para reproducir la secuencia a velocidad correcta).
        indice = {
            "fps": fps,
            "stride": paso_guardado,
            "frames": frames_guardados,
        }

        # Ademas del slideshow de fotogramas se codifica un MP4 (H.264) con
        # "como el modelo ve": los JPEG anotados se renumeran de forma
        # secuencial (la numeracion del pipeline tiene saltos de stride) y se
        # pasan a ffmpeg. Si ffmpeg no esta disponible o falla, el dashboard
        # replica la secuencia con los fotogramas directo (sin video).
        if frames_guardados:
            nombre_video = "escena_anotada.mp4"
            ruta_video = Path(guardar_frames) / nombre_video
            tmp = Path(guardar_frames) / "_video_tmp"
            try:
                tmp.mkdir(parents=True, exist_ok=True)
                for orden, nombre in enumerate(frames_guardados, start=1):
                    shutil.copy2(Path(guardar_frames) / nombre,
                                 tmp / ("f_%08d.jpg" % orden))
                ejecutable = _ffmpeg()
                if ejecutable is not None:
                    proceso = subprocess.run(
                        [ejecutable, "-y", "-loglevel", "error",
                         "-framerate", str(fps / paso_guardado),
                         "-i", str(tmp / "f_%08d.jpg"),
                         "-c:v", "libx264", "-preset", "veryfast",
                         "-crf", "23", "-pix_fmt", "yuv420p",
                         "-movflags", "+faststart", str(ruta_video)],
                        capture_output=True, timeout=300)
                    if proceso.returncode == 0 and ruta_video.exists() \
                            and ruta_video.stat().st_size > 0:
                        indice["video"] = nombre_video
                    else:
                        ruta_video.unlink(missing_ok=True)
            except (OSError, subprocess.TimeoutExpired):
                ruta_video.unlink(missing_ok=True)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        ruta_indice = Path(guardar_frames).parent / "vision_frames_index.json"
        ruta_indice.write_text(json.dumps(indice, ensure_ascii=False), encoding="utf-8")

    if MOSTRAR_RESUMEN:
        if analizador is None:
            # Video sin frames procesables: no hay nada que exportar.
            print("[AVISO] Video sin frames procesables; no se exportaron metricas.")
        else:
            # Se exporta el detalle de TODAS las personas: las activas y las
            # historicas (las que el tracker dejo de ver hace BORRAR_ID_TRAS
            # frames). El historial va primero para que la deduplicacion global
            # de eventos conserve el frame mas temprano (coherente con los
            # contadores por zona).
            exportar_json_metricas({**personas_historial, **personas_estado},
                                   analizador, heatmap, fps)

    return {"total_personas_registradas": len(personas_estado)
            + len(personas_historial)}
