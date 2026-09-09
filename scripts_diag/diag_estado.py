import numpy as np

from app import config as cfg
from app.infrastructure.vision import DetectorPoseYObjetos, CapturaVideo
from app.domain.persona import (
    nueva_persona, centro_de_caja, detectar_posesion_objeto, muneca_confiable,
    clasificar,
)
from app.domain.geometria import punto_en_zona

det = DetectorPoseYObjetos()
cap = CapturaVideo()
personas = {}
fi = 0
info = []
while True:
    ok, frame = cap.leer()
    if not ok:
        break
    fi += 1
    res = det.rastrear_personas(frame)
    objs = det.detectar_objetos(frame)
    cfg.W_VIDEO, cfg.H_VIDEO = frame.shape[1], frame.shape[0]
    zonas = cfg.escalar_zonas(frame.shape[1], frame.shape[0])
    boxes = res[0].boxes
    kps_all = (res[0].keypoints.data.cpu().numpy()
               if res[0].keypoints is not None and len(res[0].keypoints) else None)
    if boxes is None or boxes.id is None or kps_all is None:
        continue
    xyxy = boxes.xyxy.cpu().numpy()
    for i in range(len(xyxy)):
        tid = int(boxes.id[i])
        if tid not in personas:
            personas[tid] = nueva_persona(centro_de_caja(xyxy[i]), fi)
        d = personas[tid]
        kps = kps_all[i]
        to = detectar_posesion_objeto(kps, objs)
        # decidir zona por muneca
        zona = None
        for idx in (cfg.IDX_MUNECA_IZQ, cfg.IDX_MUNECA_DER):
            m = muneca_confiable(kps, idx)
            if m is None:
                continue
            for z in zonas:
                if punto_en_zona(m[0], m[1], z["agarro"]):
                    zona = z
                    break
            if zona:
                break
        if zona is None:
            centro = centro_de_caja(xyxy[i])
            for z in zonas:
                if punto_en_zona(centro[0], centro[1], z["poligono"]):
                    zona = z
                    break
        d["tiene_objeto_prev"] = False
        if zona is not None and to:
            info.append({"fi": fi, "tid": tid, "zona": zona["id"],
                         "accion": d["accion"], "retirado": d.get("retirado"),
                         "mano_dentro": d.get("mano_dentro"), "adquirido": d.get("adquirido")})
        # minimo de transiciones para mantener el estado razonable
        accion, color = clasificar(d, centro_de_caja(xyxy[i]), zona, fi, to)
        d["tiene_objeto_prev"] = bool(to)

cap.liberar()
print("frames con (zona asignada + tiene_objeto):", len(info))
# agrupar por zona
from collections import Counter
print(Counter(i["zona"] for i in info))
print("primeras 18:")
for i in info[:18]:
    print(i)