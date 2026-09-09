import json

import numpy as np

from app import config as cfg
from app.infrastructure.vision import DetectorPoseYObjetos, CapturaVideo
from app.domain.persona import detectar_posesion_objeto, muneca_confiable
from app.domain.geometria import punto_en_zona

det = DetectorPoseYObjetos()
names = {int(k): str(v) for k, v in det.model_objs.names.items()}
print("clases modelo objetos:", names)
print("es_posesion:", det.es_posesion)

cap = CapturaVideo()
fps = cap.fps
stats = {"total": 0, "con_objeto": 0, "manos": 0, "tiene_objeto": 0,
         "mano_en_agarro": 0, "agarro_y_objeto": 0}
por_clase = {}
fi = 0
while True:
    ok, frame = cap.leer()
    if not ok:
        break
    fi += 1
    res = det.rastrear_personas(frame)
    objs = det.detectar_objetos(frame)
    stats["total"] += 1
    if objs.size:
        stats["con_objeto"] += 1
        # clases
        res_o = det.model_objs(frame, conf=cfg.CONF_OBJETOS, verbose=False)
        if res_o[0].boxes is not None and len(res_o[0].boxes):
            for c in res_o[0].boxes.cls.cpu().numpy().astype(int):
                por_clase[int(c)] = por_clase.get(int(c), 0) + 1
    boxes = res[0].boxes
    kps_all = (res[0].keypoints.data.cpu().numpy()
               if res[0].keypoints is not None and len(res[0].keypoints) else None)
    if boxes is None or kps_all is None:
        continue
    xyxy = boxes.xyxy.cpu().numpy()
    cfg.W_VIDEO, cfg.H_VIDEO = frame.shape[1], frame.shape[0]
    zonas = cfg.escalar_zonas(frame.shape[1], frame.shape[0])
    for i in range(len(xyxy)):
        kps = kps_all[i]
        to = detectar_posesion_objeto(kps, objs)
        if to:
            stats["tiene_objeto"] += 1
        izq = muneca_confiable(kps, cfg.IDX_MUNECA_IZQ)
        der = muneca_confiable(kps, cfg.IDX_MUNECA_DER)
        manos = [p for p in (izq, der) if p]
        if manos:
            stats["manos"] += 1
        en_agarro = any(
            p is not None
            and any(punto_en_zona(p[0], p[1], z["agarro"]) for z in zonas)
            for p in (izq, der))
        if en_agarro:
            stats["mano_en_agarro"] += 1
        if en_agarro and to:
            stats["agarro_y_objeto"] += 1

cap.liberar()
print("frames:", fi, "fps:", fps)
print(json.dumps(stats))
print("detecciones por clase:", por_clase)