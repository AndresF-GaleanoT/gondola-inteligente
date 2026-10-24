# DOMAIN / geometria - utilidades geometricas puras para zonas de interes.

from .poligonos import punto_en_poligono


def punto_en_zona(x, y, zona):
    """Indica si el punto (x, y) cae dentro de la zona, sea rectangulo o poligono."""
    es_poligono = (
        isinstance(zona, (list, tuple))
        and len(zona) > 0
        and isinstance(zona[0], (list, tuple))
    )
    if es_poligono:
        return punto_en_poligono(x, y, zona)
    izquierda, arriba, derecha, abajo = zona
    return izquierda <= x <= derecha and arriba <= y <= abajo
