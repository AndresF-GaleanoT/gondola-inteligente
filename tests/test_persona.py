import unittest
import sys
from types import SimpleNamespace

import numpy as np

try:
    import cv2  # noqa: F401
except ModuleNotFoundError:
    # Las reglas probadas no renderizan; este stub permite ejecutarlas incluso
    # antes de instalar OpenCV en un entorno de integracion liviano.
    def _point_polygon_test(puntos, punto, _medir):
        xs = puntos[:, 0]
        ys = puntos[:, 1]
        return 1 if (xs.min() <= punto[0] <= xs.max()
                     and ys.min() <= punto[1] <= ys.max()) else -1

    sys.modules["cv2"] = SimpleNamespace(pointPolygonTest=_point_polygon_test)

from app.domain.persona import (
    detectar_interaccion_manos,
    nueva_persona,
)
from app.config import ACCION_ADQUIRIDO, ACCION_DEVOLVIENDO


class FlujoInteraccionTest(unittest.TestCase):
    def setUp(self):
        self.zona = {
            "id": "Estante_Izquierdo",
            "agarro": [[100, 100], [400, 100], [400, 400], [100, 400]],
        }
        self.kps_dentro = np.zeros((17, 3), dtype=float)
        self.kps_dentro[9] = [250, 250, 1]
        self.kps_dentro[10] = [250, 250, 1]
        self.kps_fuera = self.kps_dentro.copy()
        self.kps_fuera[9] = [500, 500, 1]
        self.kps_fuera[10] = [500, 500, 1]
        self.sin_objetos = np.empty((0, 4))
        self.con_objeto = np.array([[235, 235, 265, 265]], dtype=float)

    def test_toma_y_devolucion_pueden_ocurrir_para_la_misma_persona(self):
        datos = nueva_persona((250, 250))

        for frame in range(1, 6):
            detectar_interaccion_manos(
                datos, self.kps_dentro, frame, self.zona, False,
                self.sin_objetos,
            )

        detectar_interaccion_manos(
            datos, self.kps_dentro, 6, self.zona, True, self.con_objeto,
        )
        detectar_interaccion_manos(
            datos, self.kps_fuera, 7, self.zona, True, self.con_objeto,
        )
        self.assertTrue(datos["adquirido"])

        for frame in range(8, 13):
            detectar_interaccion_manos(
                datos, self.kps_dentro, frame, self.zona, False,
                self.sin_objetos,
            )

        self.assertFalse(datos["adquirido"])
        tipos = [evento["tipo"] for evento in datos["eventos"]]
        self.assertIn(ACCION_ADQUIRIDO, tipos)
        self.assertIn(ACCION_DEVOLVIENDO, tipos)

    def test_confirma_toma_aunque_el_objeto_aparezca_despues_del_contacto(self):
        datos = nueva_persona((250, 250))
        for frame in (1, 3):
            detectar_interaccion_manos(
                datos, self.kps_dentro, frame, self.zona, False,
                self.sin_objetos,
            )

        # La mano ya salio del agarro y el detector responde con retraso.
        for frame in (5, 7):
            detectar_interaccion_manos(
                datos, self.kps_fuera, frame, None, True, self.con_objeto,
            )

        self.assertTrue(datos["adquirido"])
        picks = [e for e in datos["eventos"] if e["tipo"] == ACCION_ADQUIRIDO]
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["zona"], self.zona["id"])

    def test_un_destello_de_objeto_no_genera_toma(self):
        datos = nueva_persona((250, 250))
        for frame in (1, 3):
            detectar_interaccion_manos(
                datos, self.kps_dentro, frame, self.zona, False,
                self.sin_objetos,
            )
        detectar_interaccion_manos(
            datos, self.kps_fuera, 5, None, True, self.con_objeto,
        )
        detectar_interaccion_manos(
            datos, self.kps_fuera, 7, None, False, self.sin_objetos,
        )

        picks = [e for e in datos["eventos"] if e["tipo"] == ACCION_ADQUIRIDO]
        self.assertEqual(picks, [])

    def test_una_racha_de_objeto_solo_cuenta_una_toma(self):
        datos = nueva_persona((250, 250))
        for frame in (1, 3):
            detectar_interaccion_manos(
                datos, self.kps_dentro, frame, self.zona, False,
                self.sin_objetos,
            )
        for frame in range(5, 25, 2):
            detectar_interaccion_manos(
                datos, self.kps_fuera, frame, None, True, self.con_objeto,
            )

        picks = [e for e in datos["eventos"] if e["tipo"] == ACCION_ADQUIRIDO]
        self.assertEqual(len(picks), 1)

    def test_la_misma_persona_puede_realizar_una_segunda_toma(self):
        datos = nueva_persona((250, 250))

        for frame in (1, 3):
            detectar_interaccion_manos(
                datos, self.kps_dentro, frame, self.zona, False,
                self.sin_objetos,
            )
        for frame in (5, 7):
            detectar_interaccion_manos(
                datos, self.kps_fuera, frame, None, True, self.con_objeto,
            )

        # El objeto deja de verse lejos del estante: rearme sin devolucion.
        for frame in (9, 11, 13, 15, 17):
            detectar_interaccion_manos(
                datos, self.kps_fuera, frame, None, False, self.sin_objetos,
            )

        for frame in (19, 21):
            detectar_interaccion_manos(
                datos, self.kps_dentro, frame, self.zona, False,
                self.sin_objetos,
            )
        for frame in (23, 25):
            detectar_interaccion_manos(
                datos, self.kps_fuera, frame, None, True, self.con_objeto,
            )

        picks = [e for e in datos["eventos"] if e["tipo"] == ACCION_ADQUIRIDO]
        self.assertEqual(len(picks), 2)


if __name__ == "__main__":
    unittest.main()
