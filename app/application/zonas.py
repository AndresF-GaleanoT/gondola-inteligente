# APPLICATION / zonas - persistencia y validacion de zonas de calibracion.
# Funciones puras (rutas y dimensiones explicitas) para poder testearlas sin
# tocar la configuracion real del proyecto. No conocen el concepto de
# "repositorio": eso lo agrega el adaptador en infrastructure/zona_repository_json.py.

import json
from pathlib import Path

from ..domain.poligonos import es_poligono_valido


def validar_zonas(zonas, ancho, alto):
    """Valida la estructura de las zonas del editor. Lanza ValueError con el
    detalle si algo no cuadra (coordenadas fuera del frame de referencia,
    vertices no enteros, autointerseccion o area nula)."""
    if not isinstance(zonas, list) or not zonas:
        raise ValueError("Se requiere una lista no vacía de zonas.")
    ids_vistos = set()
    for zona in zonas:
        if not isinstance(zona, dict) or not zona.get("id"):
            raise ValueError("Cada zona necesita un id.")
        zid = zona["id"]
        if not isinstance(zid, str) or not zid.strip():
            raise ValueError("Cada zona necesita un id de texto.")
        if zid in ids_vistos:
            raise ValueError("Hay zonas con el id repetido: %s" % zid)
        ids_vistos.add(zid)
        for clave in ("poligono", "agarro"):
            vertices = zona.get(clave)
            if not isinstance(vertices, list) or len(vertices) != 4:
                raise ValueError("Zona %s: '%s' debe tener 4 vértices."
                                 % (zid, clave))
            for vertice in vertices:
                es_valido = (isinstance(vertice, (list, tuple)) and len(vertice) == 2
                      and all(isinstance(c, int) and not isinstance(c, bool)
                              for c in vertice))
                if not es_valido or not (0 <= vertice[0] <= ancho and 0 <= vertice[1] <= alto):
                    raise ValueError(
                        "Zona %s: '%s' tiene vértices inválidos (esperaba "
                        "enteros dentro de %dx%d): %r"
                        % (zid, clave, ancho, alto, vertices))
            if not es_poligono_valido(vertices):
                raise ValueError(
                    "Zona %s: el polígono '%s' se auto-cruza o su área es 0."
                    % (zid, clave))
    return zonas


def guardar_zonas(zonas, ancho, alto, ruta_runtime):
    """Persiste las zonas del editor en el JSON de runtime. Devuelve la lista
    validada. No toca ningun archivo de codigo fuente: las zonas de fabrica
    viven en su propio JSON de solo lectura (ver infrastructure/zona_repository_json.py)."""
    zonas_validas = validar_zonas(zonas, ancho, alto)
    ruta = Path(ruta_runtime)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(zonas_validas, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return zonas_validas


def restablecer_zonas(predeterminadas, ruta_runtime):
    """Vuelve a las zonas de fabrica: borra el runtime y devuelve las
    predeterminadas (el JSON de fabrica nunca se modifica)."""
    Path(ruta_runtime).unlink(missing_ok=True)
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
    escala_x, escala_y = ancho / ancho_ref, alto / alto_ref
    zonas_escaladas = []
    for zona in zonas:
        zona_copia = dict(zona)
        zona_copia["poligono"] = [[round(x * escala_x), round(y * escala_y)]
                           for x, y in zona["poligono"]]
        zona_copia["agarro"] = [[round(x * escala_x), round(y * escala_y)]
                         for x, y in zona["agarro"]]
        zonas_escaladas.append(zona_copia)
    return zonas_escaladas
