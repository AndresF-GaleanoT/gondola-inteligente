# DOMAIN / detector_objetos - puerto de deteccion de objetos en posesion.
# Implementado por infrastructure/vision.py:DetectorPoseYObjetos.

from typing import Any, Protocol

import numpy as np


class DetectorDeObjetos(Protocol):
    """Deteccion de objetos en posesion real (producto en mano) en un
    fotograma, ya filtrados por clase."""

    def detectar_objetos(self, frame: Any) -> np.ndarray:
        """Cajas xyxy de objetos en posesion."""
        ...
