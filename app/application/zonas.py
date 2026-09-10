# APPLICATION / zonas - persistencia y validacion de zonas de calibracion.
# Funciones puras (rutas y dimensiones explicitas) para poder testearlas sin
# tocar la configuracion real del proyecto.

import ast
import json
from pathlib import Path

from ..domain.poligonos import es_poligono_valido


def validar_zonas(zonas, ancho, alto):
    """Valida la estructura de las zonas del editor. Lanza ValueError con el
    detalle si algo no cuadra (coordenadas fuera del frame de referencia,
    vertices no enteros, autointerseccion o area nula)."""
    if not isinstance(zonas, list) or not zonas:
        raise ValueError("Se requiere una lista no vacía de zonas.")
    ids = set()
    for z in zonas:
        if not isinstance(z, dict) or not z.get("id"):
            raise ValueError("Cada zona necesita un id.")
        zid = z["id"]
        if not isinstance(zid, str) or not zid.strip():
            raise ValueError("Cada zona necesita un id de texto.")
        if zid in ids:
            raise ValueError("Hay zonas con el id repetido: %s" % zid)
        ids.add(zid)
        for clave in ("poligono", "agarro"):
            pts = z.get(clave)
            if not isinstance(pts, list) or len(pts) != 4:
                raise ValueError("Zona %s: '%s' debe tener 4 vértices."
                                 % (zid, clave))
            for p in pts:
                ok = (isinstance(p, (list, tuple)) and len(p) == 2
                      and all(isinstance(c, int) and not isinstance(c, bool)
                              for c in p))
                if not ok or not (0 <= p[0] <= ancho and 0 <= p[1] <= alto):
                    raise ValueError(
                        "Zona %s: '%s' tiene vértices inválidos (esperaba "
                        "enteros dentro de %dx%d): %r"
                        % (zid, clave, ancho, alto, pts))
            if not es_poligono_valido(pts):
                raise ValueError(
                    "Zona %s: el polígono '%s' se auto-cruza o su área es 0."
                    % (zid, clave))
    return zonas


def _formatear_literal(nombre, zonas):
    """Serializa un literal de zonas en el estilo compacto de la configuracion:
    cada poligono/agarro en una linea con sus 4 vertices."""
    partes = []
    for z in zonas:
        partes.append("    {\n        \"id\": \"%s\",\n" % z["id"])
        for clave in ("poligono", "agarro"):
            pts = ", ".join("[%d, %d]" % (x, y) for x, y in z[clave])
            partes.append("        \"%s\": [%s],\n" % (clave, pts))
        partes.append("    },\n")
    return "%s = [\n" % nombre + "".join(partes) + "]\n"


def _reescribir_literal(nombre, zonas, ruta_fuente):
    """Reescribe el literal `nombre` del archivo fuente (write-back a la
    configuracion). Conserva el resto del archivo intacto."""
    ruta = Path(ruta_fuente)
    fuente = ruta.read_text(encoding="utf-8")
    try:
        arbol = ast.parse(fuente)
    except SyntaxError:
        return
    nodo = None
    for n in ast.walk(arbol):
        if isinstance(n, ast.Assign):
            targets = {t.id for t in n.targets if isinstance(t, ast.Name)}
            if nombre in targets:
                nodo = n
                break
    if nodo is None:
        return
    texto = _formatear_literal(nombre, zonas)
    lineas = fuente.splitlines(keepends=True)
    columna = lineas[nodo.lineno - 1].index(nombre)
    lineas[nodo.lineno - 1] = lineas[nodo.lineno - 1][:columna] + texto
    for i in range(nodo.lineno, nodo.end_lineno):
        lineas[i] = ""
    ruta.write_text("".join(lineas), encoding="utf-8")


def guardar_zonas(zonas, ancho, alto, ruta_runtime, ruta_fuente,
                  nombre_literal="_ZONAS_DEFAULT"):
    """Persiste las zonas del editor: runtime JSON (lo consume el pipeline) y
    write-back al literal de la configuracion. Devuelve la lista validada."""
    zonas = validar_zonas(zonas, ancho, alto)
    ruta = Path(ruta_runtime)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(zonas, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    _reescribir_literal(nombre_literal, zonas, ruta_fuente)
    return zonas


def restablecer_zonas(predeterminadas, ruta_runtime, ruta_fuente,
                      nombre_literal="_ZONAS_DEFAULT"):
    """Vuelve a las zonas de fabrica: borra el runtime, restaura el literal por
    defecto y devuelve las predeterminadas."""
    Path(ruta_runtime).unlink(missing_ok=True)
    _reescribir_literal(nombre_literal, predeterminadas, ruta_fuente)
    return predeterminadas


def cargar_zonas(ruta_runtime, predeterminadas, ancho, alto):
    """Zonas vigentes: el runtime del editor si existe (y es valido); si no,
    las predeterminadas."""
    ruta = Path(ruta_runtime)
    if ruta.exists():
        try:
            return validar_zonas(json.loads(ruta.read_text(encoding="utf-8")),
                                 ancho, alto)
        except (ValueError, json.JSONDecodeError, OSError):
            pass
    return predeterminadas


def escalar_zonas(zonas, ancho, alto, ancho_ref, alto_ref):
    """Escala las zonas (calibradas a ancho_ref x alto_ref) hasta la resolucion
    real del video. Si coincide con la referencia se devuelve la lista original
    tal cual (mismo comportamiento que antes).

    El area de "agarro" es un POLIGONO (como en la config original): se escala
    punto a punto para conservar su forma. Antes se reducia a su bounding-box
    (rectangulo), lo que agrandaba la zona de gesto en videos de otra resolucion.
    """
    if ancho == ancho_ref and alto == alto_ref:
        return zonas
    fx, fy = ancho / ancho_ref, alto / alto_ref
    zonas_escaladas = []
    for z in zonas:
        zon = dict(z)
        zon["poligono"] = [[round(x * fx), round(y * fy)]
                           for x, y in z["poligono"]]
        zon["agarro"] = [[round(x * fx), round(y * fy)]
                         for x, y in z["agarro"]]
        zonas_escaladas.append(zon)
    return zonas_escaladas