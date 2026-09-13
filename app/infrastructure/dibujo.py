# INFRASTRUCTURE / dibujo - pintado de textos y etiquetas en frames (OpenCV).

import cv2


def poner_texto(img, pos, texto, color, tam=0.5):
    """Pinta un texto con brevete oscuro de fondo y lo mantiene en pantalla."""
    fuente = cv2.FONT_HERSHEY_SIMPLEX
    x, y = pos
    (ancho, alto), base = cv2.getTextSize(texto, fuente, tam, 1)
    x = max(4, min(x, img.shape[1] - ancho - 8))
    cv2.rectangle(img, (x - 2, y - alto - base), (x + ancho + 6, y + 4),
                  (0, 0, 0), -1)
    cv2.putText(img, texto, (x, y), fuente, tam, color, 1, cv2.LINE_AA)