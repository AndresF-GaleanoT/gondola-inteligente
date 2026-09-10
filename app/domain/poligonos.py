# DOMAIN / poligonos - geometria de poligonos pura (sin dependencias externas).


def orientacion(a, b, c):
    """Signo del doble area orientada abc (regla de productos vectoriales)."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segmentos_cruzan(p1, p2, p3, p4):
    """True si los segmentos [p1-p2] y [p3-p4] se cruzan en su interior."""
    d1 = orientacion(p3, p4, p1)
    d2 = orientacion(p3, p4, p2)
    d3 = orientacion(p1, p2, p3)
    d4 = orientacion(p1, p2, p4)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
            ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def es_poligono_valido(pts):
    """Poligono simple (dos o mas aristas no se cruzan) y con area > 0."""
    n = len(pts)
    if n < 3:
        return False
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        for j in range(i + 1, n):
            c = pts[j]
            d = pts[(j + 1) % n]
            if c == a or c == b or d == a or d == b:
                continue
            if segmentos_cruzan(a, b, c, d):
                return False
    area = sum(pts[i][0] * pts[(i + 1) % n][1]
               - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    return abs(area) > 0


def punto_en_poligono(x, y, poligono):
    """True si (x, y) cae dentro del poligono (incluido el borde)."""
    x = float(x)
    y = float(y)
    dentro = False
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                dentro = not dentro
        if min(x1, x2) <= x <= max(x1, x2) and \
                min(y1, y2) <= y <= max(y1, y2) and \
                abs((x2 - x1) * (y1 - y) - (x1 - x) * (y2 - y1)) < 1e-9:
            return True
    return dentro