# INFRASTRUCTURE / zona_repository_json - adaptador JSON del puerto
# ZonaRepository (ver app/application/zona_repository.py).
#
# Reemplaza el antiguo esquema donde app/config.py reescribia su propio
# codigo fuente (AST) para "recordar" las zonas guardadas: ahora las zonas de
# fabrica viven en un JSON de solo lectura y las personalizadas en un JSON de
# runtime. Ningun archivo .py se toca en tiempo de ejecucion.

import json
from pathlib import Path

from ..application import zonas as _zonas


class JsonZonaRepository:
    """Zonas de fabrica en `ruta_default` (JSON, solo lectura) + zonas
    personalizadas en `ruta_runtime` (JSON, las escribe el editor web)."""

    def __init__(self, ruta_runtime, ruta_default, ancho_ref, alto_ref):
        self._ruta_runtime = Path(ruta_runtime)
        self._ruta_default = Path(ruta_default)
        self._ancho_ref = ancho_ref
        self._alto_ref = alto_ref

    def _predeterminadas(self):
        return json.loads(self._ruta_default.read_text(encoding="utf-8"))

    def obtener(self):
        return _zonas.cargar_zonas(self._ruta_runtime, self._predeterminadas(),
                                   self._ancho_ref, self._alto_ref)

    def fuente(self):
        return "runtime" if self._ruta_runtime.exists() else "default"

    def guardar(self, zonas):
        return _zonas.guardar_zonas(zonas, self._ancho_ref, self._alto_ref,
                                    self._ruta_runtime)

    def restablecer(self):
        return _zonas.restablecer_zonas(self._predeterminadas(), self._ruta_runtime)
