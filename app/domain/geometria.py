# DOMAIN / geometria - helpers geometricos puros (poligonos de zona, textos).

import cv2
import numpy as np


def punto_en_zona(x, y, zona):
    """True si (x, y) cae dentro de la zona (rectangulo o poligono)."""
    if isinstance(zona, (list, tuple)) and len(zona) > 0 \
            and isinstance(zona[0], (list, tuple)):
        pts = np.array([tuple(map(float, p)) for p in zona], dtype=np.float32)
        return cv2.pointPolygonTest(pts, (float(x), float(y)), False) >= 0
    x1, y1, x2, y2 = zona
    return x1 <= x <= x2 and y1 <= y <= y2


def poner_texto(img, pos, texto, color, tam=0.5):
    """Pinta un texto con brevete oscuro de fondo y lo mantiene en pantalla."""
    fuente = cv2.FONT_HERSHEY_SIMPLEX
    x, y = pos
    (ancho, alto), base = cv2.getTextSize(texto, fuente, tam, 1)
    x = max(4, min(x, img.shape[1] - ancho - 8))
    cv2.rectangle(img, (x - 2, y - alto - base), (x + ancho + 6, y + 4),
                  (0, 0, 0), -1)
    cv2.putText(img, texto, (x, y), fuente, tam, color, 1, cv2.LINE_AA)
