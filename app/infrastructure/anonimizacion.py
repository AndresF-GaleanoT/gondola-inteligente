# INFRASTRUCTURE / anonimizacion - mosaico de rostros (privacidad, Ley 1581/2012).

import cv2

from ..config import (CONF_CABEZA_KP, CABEZA_ANCHO, CABEZA_ALTO,
                      CABEZA_CENTRO_Y, SUAVIZADO_CABEZA, TAM_BLUR,
                      SIGMA_BLUR, CONF, IOU, IMGSZ, MODELO_POSE)


def difuminar_caja(img, x1, y1, x2, y2):
    """Desenfoca la region indicada del frame (anonimizacion de cara)."""
    xi1 = max(0, int(x1)); yi1 = max(0, int(y1))
    xi2 = min(img.shape[1], int(x2)); yi2 = min(img.shape[0], int(y2))
    if xi2 <= xi1 or yi2 <= yi1:
        return
    recorte = img[yi1:yi2, xi1:xi2]
    if recorte.size == 0:
        return
    img[yi1:yi2, xi1:xi2] = cv2.GaussianBlur(recorte,
                                             (TAM_BLUR, TAM_BLUR), SIGMA_BLUR)


def _mejor_punto_cabeza(kps):
    """Elige el mejor keypoint de cabeza (nariz u oido) con su confianza."""
    mejor = None
    mejor_conf = CONF_CABEZA_KP
    for idx in (0, 3, 4):
        x, y, conf = kps[idx]
        if conf > mejor_conf:
            mejor = (float(x), float(y))
            mejor_conf = float(conf)
    return mejor, mejor_conf


def _bbox_cabeza(caja, punto=None):
    """Rectangulo de la cabeza derivado de la caja de cuerpo + keypoint."""
    px1, py1, px2, py2 = caja
    ancho_bbox = px2 - px1
    alto_bbox = py2 - py1
    if punto is not None:
        lado = ancho_bbox * CABEZA_ANCHO
        x1, y1 = punto[0] - lado / 2, punto[1] - lado / 2
        x2, y2 = punto[0] + lado / 2, punto[1] + lado / 2
    else:
        cx = (px1 + px2) / 2
        cy = py1 + alto_bbox * CABEZA_CENTRO_Y
        x1 = cx - ancho_bbox * CABEZA_ANCHO / 2
        y1 = cy - alto_bbox * CABEZA_ALTO / 2
        x2 = cx + ancho_bbox * CABEZA_ANCHO / 2
        y2 = cy + alto_bbox * CABEZA_ALTO / 2
    return (x1, y1, x2, y2)


def _cajas_cabeza_rastreadas(results, cabeza_suave):
    """Calcula las cajas de cabeza de cada persona con suavizado temporal."""
    cajas = results[0].boxes
    if cajas is None or cajas.id is None:
        return []
    puntos = (results[0].keypoints.data.cpu().numpy()
              if results[0].keypoints is not None
              and len(results[0].keypoints) else None)
    salida = []
    activos = set()
    for i, caja in enumerate(cajas.xyxy.cpu().numpy()):
        tid = int(cajas.id[i])
        activos.add(tid)
        punto, conf = (_mejor_punto_cabeza(puntos[i])
                       if puntos is not None else (None, 0.0))
        nueva = _bbox_cabeza(caja, punto)
        previo = cabeza_suave.get(tid)
        if previo is None:
            cabeza_suave[tid] = nueva
            salida.append(nueva)
        else:
            a = SUAVIZADO_CABEZA
            suave = tuple(a * n + (1 - a) * p for n, p in zip(nueva, previo))
            cabeza_suave[tid] = suave
            salida.append(suave)
    for tid in [t for t in cabeza_suave if t not in activos]:
        del cabeza_suave[tid]
    return salida


def anonimizar(img, cajas_cabeza):
    """Difumina todas las cajas de cabeza presentes en el frame."""
    for cx1, cy1, cx2, cy2 in cajas_cabeza:
        x1 = max(0, int(cx1)); y1 = max(0, int(cy1))
        x2 = min(img.shape[1], int(cx2)); y2 = min(img.shape[0], int(cy2))
        if x2 > x1 and y2 > y1:
            difuminar_caja(img, x1, y1, x2, y2)


_detector_pose = None


def _pose():
    """Detector de pose de personas (carga perezosa, cacheado entre vistas)."""
    global _detector_pose
    if _detector_pose is None:
        from ultralytics import YOLO
        _detector_pose = YOLO(MODELO_POSE)
    return _detector_pose


def cajas_cabeza_frame(results):
    """Cajas de cabeza por persona para un fotograma suelto (sin tracking)."""
    cajas = results[0].boxes
    if cajas is None:
        return []
    puntos = (results[0].keypoints.data.cpu().numpy()
              if results[0].keypoints is not None
              and len(results[0].keypoints) else None)
    salida = []
    for i, caja in enumerate(cajas.xyxy.cpu().numpy()):
        punto, _ = (_mejor_punto_cabeza(puntos[i])
                    if puntos is not None else (None, 0.0))
        salida.append(_bbox_cabeza(caja, punto))
    return salida


def anonimizar_preview(frame):
    """Anonimiza los rostros de un fotograma suelto (vista previa de la
    calibracion de zonas) para no exponer identidades antes del analisis."""
    try:
        resultados = _pose()(frame, conf=CONF, iou=IOU, imgsz=IMGSZ,
                             verbose=False)
    except Exception:
        return
    anonimizar(frame, cajas_cabeza_frame(resultados))
