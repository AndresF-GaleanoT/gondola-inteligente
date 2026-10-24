# DOMAIN / detector_personas - puerto de deteccion+tracking de personas.
# El dominio y los casos de uso dependen de este contrato (Protocol,
# tipado estructural: no hace falta heredar de el), no de que el adaptador
# real use YOLO. Implementado por infrastructure/vision.py:DetectorPoseYObjetos.

from typing import Any, Protocol


class DetectorDePersonas(Protocol):
    """Deteccion + tracking de personas (pose) en un fotograma."""

    def rastrear_personas(self, frame: Any) -> Any:
        """Devuelve resultados con `.boxes` (cajas + ids de tracking) y
        `.keypoints` (pose), consumidos por domain.persona.procesar_personas."""
        ...
