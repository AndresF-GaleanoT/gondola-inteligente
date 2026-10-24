# DOMAIN / analisis - heatmap de trafico y analizador de zonas calientes/frias.

import numpy as np

import cv2
from .. import config as cfg
from ..config import (HEATMAP_FACTOR,
                      HEATMAP_RADIO,
                      HEATMAP_ALPHA, HEATMAP_EXPORT_CELDAS)
from .constantes import CLASIF_CALIENTE, CLASIF_TEMPLADA, CLASIF_FRIA


class HeatmapTrafico:
    """Acumula calor promedio por celda (intensidad / frames con presencia).
    En vez de una suma acumulada que infla con videos largos o gente estatica,
    el mapa se divide entre el numero de frames medidos: queda una intensidad
    promedio temporal comparable entre pasillos/videos."""

    def __init__(self, ancho, alto, factor=HEATMAP_FACTOR):
        self.w = int(ancho)
        self.h = int(alto)
        self.factor = factor
        self.mapa = np.zeros((self.h, self.w), dtype=np.float32)
        self.frames = 0

    def _pies(self, caja):
        bx1, by1, bx2, by2 = caja
        return (int((bx1 + bx2) / 2), int(by2))

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
        mapa_local = self.mapa
        alto, ancho = self.h, self.w
        for caja in cajas_xyxy:
            centro_x, centro_y = self._pies(caja)
            if not (0 <= centro_x < ancho and 0 <= centro_y < alto):
                continue
            x_ini, x_fin = max(0, centro_x - radio), min(ancho, centro_x + radio + 1)
            y_ini, y_fin = max(0, centro_y - radio), min(alto, centro_y + radio + 1)
            if x_fin <= x_ini or y_fin <= y_ini:
                continue
            rejilla_y = np.arange(y_ini, y_fin)[:, None]
            rejilla_x = np.arange(x_ini, x_fin)[None, :]
            distancia2 = (rejilla_x - centro_x) ** 2 + (rejilla_y - centro_y) ** 2
            splat = np.exp(-distancia2 / (2 * sigma ** 2)) * self.factor
            mapa_local[y_ini:y_fin, x_ini:x_fin] += splat
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
        mapa_color = cv2.applyColorMap(normalizado.astype(np.uint8), cv2.COLORMAP_JET)
        return cv2.addWeighted(img, 1 - HEATMAP_ALPHA, mapa_color, HEATMAP_ALPHA, 0)

    def exportar_grilla(self, celdas=HEATMAP_EXPORT_CELDAS):
        """Devuelve la grilla normalizada (0-100) para el dashboard, basada en
        el promedio por frame y no en la suma acumulada del video."""
        promedio = self.promedio()
        if self.h == 0 or self.w == 0 or promedio.size == 0:
            return [[0] * celdas for _ in range(celdas)]
        # Reduccion al tamano de la grilla cobriendo el frame COMPLETO.
        # (El muestreo por stride + recorte anterior descartaba el borde
        # inferior/derecho del mapa cuando h/w no eran multiplos de celdas.)
        if promedio.shape[0] < celdas or promedio.shape[1] < celdas:
            lienzo = np.zeros((celdas, celdas), dtype=np.float32)
            lienzo[:promedio.shape[0], :promedio.shape[1]] = promedio
            grilla = lienzo
        else:
            grilla = cv2.resize(promedio, (celdas, celdas),
                                interpolation=cv2.INTER_AREA)
        pico = grilla.max()
        if pico < 1e-6:
            return [[0] * celdas for _ in range(celdas)]
        return (grilla / pico * 100).round(1).tolist()


class AnalizadorZonas:
    """Acumula dinamica por zona del layout y clasifica caliente/fria."""

    def __init__(self, zonas=None):
        self.zonas = {}
        from ..config import ZONAS
        fuente = zonas if zonas is not None else ZONAS
        for definicion in fuente:
            zid = definicion["id"]
            puntos = definicion["poligono"]
            coords_x = [p[0] for p in puntos]
            coords_y = [p[1] for p in puntos]
            izq, arriba, der, abajo = min(coords_x), min(coords_y), max(coords_x), max(coords_y)
            self.zonas[zid] = {
                "id": zid,
                "poligono": [[float(p[0]), float(p[1])] for p in puntos],
                "bbox": (izq, arriba, der, abajo),
                "agarro": definicion["agarro"],
                "cx": (izq + der) / 2,
                "cy": (arriba + abajo) / 2,
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
        distancia = ((centro[0] - z["cx"]) ** 2 + (centro[1] - z["cy"]) ** 2) ** 0.5
        diagonal = max(1.0, ((z["bbox"][2] - z["bbox"][0]) ** 2 +
                          (z["bbox"][3] - z["bbox"][1]) ** 2) ** 0.5)
        z["calor"] += max(0.0, 1.0 - distancia / diagonal)

    def clasificar(self):
        """Clasifica cada zona segun su calor normalizado (caliente/fria)."""
        calores = [z["calor"] for z in self.zonas.values()]
        if not calores:
            return
        calor_max = max(calores) or 1.0
        calor_min = min(calores)
        rango = max(1e-6, calor_max - calor_min)
        for z in self.zonas.values():
            normalizado = (z["calor"] - calor_min) / rango
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
            izq, arriba, der, abajo = z["bbox"]
            salida.append({
                "id": zid,
                "bbox": [izq, arriba, der, abajo],
                "visitas": z["visitas"],
                "frames_dentro": z["frames_dentro"],
                "pick_ups": z["pick_ups"],
                "put_backs": z["put_backs"],
                "calor": round(z["calor"], 1),
                "clasificacion": z["clasificacion"],
            })
        return salida
