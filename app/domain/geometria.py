# DOMAIN / geometria - helpers geometricos puros (poligonos de zona).

from .poligonos import punto_en_poligono


def punto_en_zona(x, y, zona):
    """True si (x, y) cae dentro de la zona (rectangulo o poligono)."""
    if isinstance(zona, (list, tuple)) and len(zona) > 0 \
            and isinstance(zona[0], (list, tuple)):
        return punto_en_poligono(x, y, zona)
    x1, y1, x2, y2 = zona
    return x1 <= x <= x2 and y1 <= y <= y2