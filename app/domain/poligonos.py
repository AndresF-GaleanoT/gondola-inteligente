# DOMAIN / poligonos - geometria de poligonos pura (sin dependencias externas).


def orientacion(a, b, c):
    """Signo del doble area orientada abc (regla de productos vectoriales)."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segmentos_cruzan(p1, p2, p3, p4):
    """True si los segmentos [p1-p2] y [p3-p4] se cruzan en su interior."""
    signo1 = orientacion(p3, p4, p1)
    signo2 = orientacion(p3, p4, p2)
    signo3 = orientacion(p1, p2, p3)
    signo4 = orientacion(p1, p2, p4)
    cruzan_ab = (signo1 > 0 and signo2 < 0) or (signo1 < 0 and signo2 > 0)
    cruzan_cd = (signo3 > 0 and signo4 < 0) or (signo3 < 0 and signo4 > 0)
    return cruzan_ab and cruzan_cd


def es_poligono_valido(pts):
    """Poligono simple (dos o mas aristas no se cruzan) y con area > 0."""
    total_vertices = len(pts)
    if total_vertices < 3:
        return False
    for indice_a in range(total_vertices):
        vertice_a = pts[indice_a]
        vertice_b = pts[(indice_a + 1) % total_vertices]
        for indice_c in range(indice_a + 1, total_vertices):
            vertice_c = pts[indice_c]
            vertice_d = pts[(indice_c + 1) % total_vertices]
            comparten_vertice = vertice_c in (vertice_a, vertice_b) or vertice_d in (vertice_a, vertice_b)
            if comparten_vertice:
                continue
            if segmentos_cruzan(vertice_a, vertice_b, vertice_c, vertice_d):
                return False
    area_doble = sum(
        pts[k][0] * pts[(k + 1) % total_vertices][1]
        - pts[(k + 1) % total_vertices][0] * pts[k][1]
        for k in range(total_vertices)
    )
    return abs(area_doble) > 0


def punto_en_poligono(x, y, poligono):
    """True si (x, y) cae dentro del poligono (incluido el borde)."""
    px = float(x)
    py = float(y)
    esta_dentro = False
    total_vertices = len(poligono)
    for indice in range(total_vertices):
        vx1, vy1 = poligono[indice]
        vx2, vy2 = poligono[(indice + 1) % total_vertices]
        cruza_altura = (vy1 > py) != (vy2 > py)
        if cruza_altura:
            interseccion_x = (vx2 - vx1) * (py - vy1) / (vy2 - vy1) + vx1
            if px < interseccion_x:
                esta_dentro = not esta_dentro
        sobre_el_borde = (
            min(vx1, vx2) <= px <= max(vx1, vx2)
            and min(vy1, vy2) <= py <= max(vy1, vy2)
            and abs((vx2 - vx1) * (vy1 - py) - (vx1 - px) * (vy2 - vy1)) < 1e-9
        )
        if sobre_el_borde:
            return True
    return esta_dentro
