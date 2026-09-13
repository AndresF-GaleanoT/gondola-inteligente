# DOMAIN / analisis - heatmap de trafico y analizador de zonas calientes/frias.

import numpy as np

import cv2
from .. import config as cfg
from ..config import (HEATMAP_FACTOR,
                      HEATMAP_RADIO,
                      HEATMAP_ALPHA, HEATMAP_EXPORT_CELDAS,
                      CLASIF_CALIENTE, CLASIF_TEMPLADA, CLASIF_FRIA)


class HeatmapTrafico:
    """Acumula calor promedio por celda (intensidad / frames con presencia).
    En vez de una suma acumulada que infla con videos largos o gente estatica,
    el mapa se divide entre el numero de frames medidos: queda una intensidad
    promedio temporal comparable entre pasillos/videos."""

    def __init__(self, ancho, alto, factor=HEATMAP_FACTOR):
        self.h = int(alto)
        self.w = int(ancho)
        self.factor = factor
        self.mapa = np.zeros((self.h, self.w), dtype=np.float32)
        self.frames = 0

    def _pies(self, caja):
        x1, y1, x2, y2 = caja
        return (int((x1 + x2) / 2), int(y2))

    def acumular(self, cajas_xyxy):
        if cajas_xyxy is None or len(cajas_xyxy) == 0:
            return
        self.frames += 1
        # Splat gaussiano LOCAL: la gaussiana pesa ~99.7% dentro de 3*sigma, asi
        # que basta con acumular en un parche de +/-3*HEATMAP_RADIO alrededor del
        # pie, en vez de barrer toda la imagen por cada persona (antes ~180 ms/frame
        # en 1280x720; ahora suele bajar de 1 ms/frame). El resultado numerico es
        # practicamente identico (la cola fuera de 3*sigma es despreciable).
        sigma = HEATMAP_RADIO
        radio = int(round(3 * sigma))
        m = self.mapa
        h, w = self.h, self.w
        for caja in cajas_xyxy:
            cx, cy = self._pies(caja)
            if not (0 <= cx < w and 0 <= cy < h):
                continue
            x0, x1 = max(0, cx - radio), min(w, cx + radio + 1)
            y0, y1 = max(0, cy - radio), min(h, cy + radio + 1)
            if x1 <= x0 or y1 <= y0:
                continue
            gy = np.arange(y0, y1)[:, None]
            gx = np.arange(x0, x1)[None, :]
            d2 = (gx - cx) ** 2 + (gy - cy) ** 2
            splat = np.exp(-d2 / (2 * sigma ** 2)) * self.factor
            m[y0:y1, x0:x1] += splat
        # SIN clamp creciente (antes `min(m, 255*frames)`): el tope crecia con el
        # numero de frames y hacia que el mapa se saturara a 255 en videos largos
        # (todo "caliente"). El mapa acumula la suma; la normalizacion correcta
        # ocurre en promedio()/exportar_grilla() dividiendo por los frames.
        # Nota: con 3*sigma la suma queda cortada en <0.3% respecto a la
        # gaussiana completa, por lo que los valores son practicamente identicos.

    def promedio(self):
        """Mapa promedio (por frame con presencia)."""
        return self.mapa / max(1, self.frames)

    def overlay(self, img):
        if self.frames == 0:
            return img
        normalizado = cv2.normalize(self.promedio(), None, 0, 255, cv2.NORM_MINMAX)
        color = cv2.applyColorMap(normalizado.astype(np.uint8), cv2.COLORMAP_JET)
        return cv2.addWeighted(img, 1 - HEATMAP_ALPHA, color, HEATMAP_ALPHA, 0)

    def exportar_grilla(self, celdas=HEATMAP_EXPORT_CELDAS):
        """Devuelve la grilla normalizada (0-100) para el dashboard, basada en
        el promedio por frame y no en la suma acumulada del video."""
        prom = self.promedio()
        if self.h == 0 or self.w == 0 or prom.size == 0:
            return [[0] * celdas for _ in range(celdas)]
        # Reduccion al tamano de la grilla cobriendo el frame COMPLETO.
        # (El muestreo por stride + recorte anterior descartaba el borde
        # inferior/derecho del mapa cuando h/w no eran multiplos de celdas.)
        if prom.shape[0] < celdas or prom.shape[1] < celdas:
            p = np.zeros((celdas, celdas), dtype=np.float32)
            p[:prom.shape[0], :prom.shape[1]] = prom
            grilla = p
        else:
            grilla = cv2.resize(prom, (celdas, celdas),
                                interpolation=cv2.INTER_AREA)
        mx = grilla.max()
        if mx < 1e-6:
            return [[0] * celdas for _ in range(celdas)]
        return (grilla / mx * 100).round(1).tolist()


class AnalizadorZonas:
    """Acumula dinamica por zona del layout y clasifica caliente/fria."""

    def __init__(self, zonas=None):
        self.zonas = {}
        from ..config import ZONAS
        fuente = zonas if zonas is not None else ZONAS
        for z in fuente:
            zid = z["id"]
            puntos = z["poligono"]
            xs = [p[0] for p in puntos]
            ys = [p[1] for p in puntos]
            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
            self.zonas[zid] = {
                "id": zid,
                "poligono": [[float(p[0]), float(p[1])] for p in puntos],
                "bbox": (x1, y1, x2, y2),
                "agarro": z["agarro"],
                "cx": (x1 + x2) / 2,
                "cy": (y1 + y2) / 2,
                "visitas": 0,
                "frames_dentro": 0,
                "calor": 0.0,
                "pick_ups": 0,
                "put_backs": 0,
                "ultimo_pickup_frame": None,
                "ultimo_putback_frame": None,
                "clasificacion": CLASIF_TEMPLADA,
            }

    def actualizar(self, centro, zona):
        """Actualiza counters de zona por la presencia actual de una persona."""
        if zona is None:
            return
        z = self.zonas[zona["id"]]
        # Se suma el paso real del pipeline: con PROCESAR_CADA_N>1 el pipeline
        # solo llama por OBTENER frame procesado (1 de cada N), asi que el
        # contador debe reflejar los frames de VIDEO que la persona estuvo en
        # la zona (si no, dwell_promedio_seg quedaba a la mitad).
        z["frames_dentro"] += cfg.PROCESAR_CADA_N
        dist = ((centro[0] - z["cx"]) ** 2 + (centro[1] - z["cy"]) ** 2) ** 0.5
        denom = max(1.0, ((z["bbox"][2] - z["bbox"][0]) ** 2 +
                          (z["bbox"][3] - z["bbox"][1]) ** 2) ** 0.5)
        z["calor"] += max(0.0, 1.0 - dist / denom)

    def clasificar(self):
        """Clasifica cada zona segun su calor normalizado (caliente/fria)."""
        calores = [z["calor"] for z in self.zonas.values()]
        if not calores:
            return
        max_calor = max(calores) or 1.0
        min_calor = min(calores)
        rango = max(1e-6, max_calor - min_calor)
        for z in self.zonas.values():
            normalizado = (z["calor"] - min_calor) / rango
            if normalizado > 0.66:
                z["clasificacion"] = CLASIF_CALIENTE
            elif normalizado > 0.33:
                z["clasificacion"] = CLASIF_TEMPLADA
            else:
                z["clasificacion"] = CLASIF_FRIA

    def resumen(self, fps):
        self.clasificar()
        resultado = []
        for z in self.zonas.values():
            visitas = z["visitas"] or 1
            resultado.append({
                "id": z["id"],
                "centro_px": [round(z["cx"]), round(z["cy"])],
                "escala_dashboard": {
                    "x": round(z["cx"] / cfg.W_VIDEO, 4),
                    "y": round(z["cy"] / cfg.H_VIDEO, 4),
                },
                "visitas": z["visitas"],
                "dwell_promedio_seg": round(z["frames_dentro"] / visitas / fps, 2),
                "presencia": round(z["calor"], 1),
                "clasificacion": z["clasificacion"],
                "pick_ups": z["pick_ups"],
                "put_backs": z["put_backs"],
                "tasa_rechazo": round(z["put_backs"] / z["pick_ups"], 2) if z["pick_ups"] else 0,
            })
        return resultado

    def exportar(self):
        """Dict directo de zonas para consumo del dashboard (sin escala)."""
        self.clasificar()
        salida = []
        for z in self.zonas.values():
            zid = z["id"]
            x1, y1, x2, y2 = z["bbox"]
            salida.append({
                "id": zid,
                "bbox": [x1, y1, x2, y2],
                "visitas": z["visitas"],
                "frames_dentro": z["frames_dentro"],
                "pick_ups": z["pick_ups"],
                "put_backs": z["put_backs"],
                "calor": round(z["calor"], 1),
                "clasificacion": z["clasificacion"],
            })
        return salida
