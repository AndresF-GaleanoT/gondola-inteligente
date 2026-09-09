import json

from app import config as cfg
from app.infrastructure.vision import DetectorPoseYObjetos, CapturaVideo
from app.domain.geometria import punto_en_zona

det = DetectorPoseYObjetos()
cap = CapturaVideo()
fi = 0
resumen = {"pose_afuera": 0, "pose_en_zona": 0}
detalles = []
while True:
    ok, frame = cap.leer()
    if not ok:
        break
    fi += 1
    res = det.rastrear_personas(frame)
    objs = det.detectar_objetos(frame)
    cfg.W_VIDEO, cfg.H_VIDEO = frame.shape[1], frame.shape[0]
    zonas = cfg.escalar_zonas(frame.shape[1], frame.shape[0])
    kps_all = (res[0].keypoints.data.cpu().numpy()
               if res[0].keypoints is not None and len(res[0].keypoints) else None)
    boxes = res[0].boxes
    if boxes is None or kps_all is None or not objs.size:
        continue
    xyxy = boxes.xyxy.cpu().numpy()
    for i in range(len(xyxy)):
        kps = kps_all[i]
        caj = kps[cfg.IDX_MUNECA_IZQ], kps[cfg.IDX_MUNECA_DER]
        for idx, (x, y, conf) in ((cfg.IDX_MUNECA_IZQ, caj[0]), (cfg.IDX_MUNECA_DER, caj[1])):
            pass
        # muñecas fiables
        munecas = [(kps[cfg.IDX_MUNECA_IZQ][0], kps[cfg.IDX_MUNECA_IZQ][1])
                   for _ in [0] if kps[cfg.IDX_MUNECA_IZQ][2] >= cfg.CONF_MANO]
        munecas += [(kps[cfg.IDX_MUNECA_DER][0], kps[cfg.IDX_MUNECA_DER][1])
                    if kps[cfg.IDX_MUNECA_DER][2] >= cfg.CONF_MANO else None]
        munecas = [m for m in munecas if m]
        # objeto cerca de alguna muñeca?
        cerca = False
        for (x, y) in munecas:
            for ob in objs.tolist():
                x1, y1, x2, y2 = ob
                dx = max(x1 - x, 0, x - x2)
                dy = max(y1 - y, 0, y - y2)
                d = (dx * dx + dy * dy) ** 0.5
                tol = (cfg.MANO_OBJ_TOLERANCIA + cfg.MANO_RADIO) * (cfg.W_VIDEO / cfg.ANCHO_REF_ZONAS)
                if d <= tol:
                    cerca = True
        if not cerca:
            continue
        # zona de la persona
        zona = None
        for z in zonas:
            if any(punto_en_zona(x, y, z["agarro"]) for (x, y) in munecas):
                zona = z["id"] + " [agarro]"
                break
        for z in zonas if zona is None else []:
            if any(punto_en_zona(x, y, z["poligono"]) for (x, y) in munecas):
                zona = z["id"] + " [poligono]"
                break
        key = zona or "FUERA de zonas"
        resumen[key] = resumen.get(key, 0) + 1
        if len(detalles) < 12:
            detalles.append({
                "fi": fi,
                "zona": zona,
                "munecas": [[round(float(a), 1), round(float(b), 1)]
                             for (a, b) in munecas],
                "objects": [round(float(v), 1)
                            for ob in objs.tolist() for v in ob],
            })

cap.liberar()
print("RESUMEN (frames con producto junto a mano):")
print(json.dumps(resumen, indent=2))
print("\nMUESTRA:")
print(json.dumps(detalles, indent=1))
