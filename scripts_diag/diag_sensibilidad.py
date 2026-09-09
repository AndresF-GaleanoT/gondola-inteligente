import numpy as np

from app import config as cfg
from app.infrastructure.vision import DetectorPoseYObjetos, CapturaVideo
from app.domain.persona import detectar_posesion_objeto, muneca_confiable
from app.domain.geometria import punto_en_zona

det = DetectorPoseYObjetos()
cap = CapturaVideo()
fi = 0
stats = {"frames": 0, "cajas_obj": 0, "pose_estricta": 0,
         "muneca_en_agarro": 0, "pose_estricta_en_agarro": 0}
reparto_conf = {}
while True:
    ok, frame = cap.leer()
    if not ok:
        break
    fi += 1
    cfg.W_VIDEO, cfg.H_VIDEO = frame.shape[1], frame.shape[0]
    zonas = cfg.escalar_zonas(frame.shape[1], frame.shape[0])
    res = det.rastrear_personas(frame)
    # detectar objetos con varias CONF para comparar
    r = det.model_objs(frame, conf=0.25, verbose=False)
    for c in [0.25, 0.30, 0.40]:
        if r[0].boxes is None:
            continue
        n = int((r[0].boxes.conf >= c).sum())
        reparto_conf[c] = reparto_conf.get(c, 0) + n
    objs = det.detectar_objetos(frame)  # usa CONF_OBJETOS real
    stats["frames"] += 1
    if objs.size:
        stats["cajas_obj"] += 1
    kps_all = (res[0].keypoints.data.cpu().numpy()
               if res[0].keypoints is not None and len(res[0].keypoints) else None)
    boxes = res[0].boxes
    if boxes is None or kps_all is None:
        continue
    xyxy = boxes.xyxy.cpu().numpy()
    for i in range(len(xyxy)):
        kps = kps_all[i]
        if detectar_posesion_objeto(kps, objs):
            stats["pose_estricta"] += 1
            for idx in (cfg.IDX_MUNECA_IZQ, cfg.IDX_MUNECA_DER):
                m = muneca_confiable(kps, idx)
                if m and any(punto_en_zona(m[0], m[1], z["agarro"]) for z in zonas):
                    stats["pose_estricta_en_agarro"] += 1
                    break
        for idx in (cfg.IDX_MUNECA_IZQ, cfg.IDX_MUNECA_DER):
            m = muneca_confiable(kps, idx)
            if m and any(punto_en_zona(m[0], m[1], z["agarro"]) for z in zonas):
                stats["muneca_en_agarro"] += 1
                break

cap.liberar()
print("frames:", stats["frames"])
print("frames con alguna caja de objeto:", stats["cajas_obj"])
print("frames con ponencia estricta:", stats["pose_estricta"])
print("  -> y muneca en agarro:", stats["pose_estricta_en_agarro"])
print("frames con muneca en agarro:", stats["muneca_en_agarro"])
print("cajas acumuladas por CONF (cajas/frame >= conf):", reparto_conf)