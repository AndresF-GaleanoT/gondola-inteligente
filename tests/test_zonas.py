import json
import tempfile
import unittest
from pathlib import Path

from app.application import zonas
from app.config import ALTO_REF_ZONAS, ANCHO_REF_ZONAS, _ZONAS_DEFAULT

UNO = [{"id": "Z1",
        "poligono": [[10, 0], [50, 0], [50, 100], [10, 100]],
        "agarro": [[12, 2], [48, 2], [48, 90], [12, 90]]}]


class ZonasTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.base = Path(self._dir.name)
        self.runtime = self.base / "zonas_runtime.json"
        self.fuente = self.base / "config.py"

    def tearDown(self):
        self._dir.cleanup()

    def _escribir_fuente(self, lista=None):
        cuerpo = zonas._formatear_literal("_ZONAS_DEFAULT",
                                          _ZONAS_DEFAULT if lista is None
                                          else lista)
        self.fuente.write_text("# cabecera\n" + cuerpo + "# pie\n",
                               encoding="utf-8")

    def test_validar_zonas_rechaza_coordenadas_fuera(self):
        con_fuera = [dict(UNO[0], poligono=[[10, 0], [50, 0], [50, 5000], [10, 100]])]
        with self.assertRaises(ValueError):
            zonas.validar_zonas(con_fuera, ANCHO_REF_ZONAS, ALTO_REF_ZONAS)

    def test_validar_zonas_rechaza_autocruzado(self):
        cruzado = [dict(UNO[0], poligono=[[0, 0], [100, 100], [0, 100], [100, 0]])]
        with self.assertRaises(ValueError):
            zonas.validar_zonas(cruzado, ANCHO_REF_ZONAS, ALTO_REF_ZONAS)

    def test_guardar_zonas_escribe_runtime_y_literal(self):
        self._escribir_fuente()
        guardadas = zonas.guardar_zonas(UNO, ANCHO_REF_ZONAS, ALTO_REF_ZONAS,
                                        self.runtime, self.fuente)
        self.assertEqual(guardadas, UNO)
        self.assertEqual(json.loads(self.runtime.read_text(encoding="utf-8")),
                         UNO)
        contenido = self.fuente.read_text(encoding="utf-8")
        self.assertIn("[10, 0], [50, 0], [50, 100]", contenido)
        self.assertIn("# cabecera", contenido)
        self.assertIn("# pie", contenido)

    def test_guardar_zonas_no_escribe_si_invalidas(self):
        self._escribir_fuente()
        malas = [[], None]
        for mal in malas:
            with self.assertRaises(ValueError):
                zonas.guardar_zonas(mal, ANCHO_REF_ZONAS, ALTO_REF_ZONAS,
                                    self.runtime, self.fuente)
            self.assertFalse(self.runtime.exists())

    def test_cargar_prioriza_runtime_valido(self):
        self.runtime.write_text(json.dumps(UNO), encoding="utf-8")
        cargadas = zonas.cargar_zonas(self.runtime, _ZONAS_DEFAULT,
                                      ANCHO_REF_ZONAS, ALTO_REF_ZONAS)
        self.assertEqual(cargadas, UNO)

    def test_cargar_descarta_runtime_corrupto(self):
        self.runtime.write_text("{no es json", encoding="utf-8")
        cargadas = zonas.cargar_zonas(self.runtime, _ZONAS_DEFAULT,
                                      ANCHO_REF_ZONAS, ALTO_REF_ZONAS)
        self.assertEqual(cargadas, _ZONAS_DEFAULT)

    def test_restablecer_borra_runtime_y_restaura_literal(self):
        self._escribir_fuente(UNO)
        self.runtime.write_text(json.dumps(UNO), encoding="utf-8")
        restauradas = zonas.restablecer_zonas(_ZONAS_DEFAULT, self.runtime,
                                              self.fuente)
        self.assertEqual(restauradas, _ZONAS_DEFAULT)
        self.assertFalse(self.runtime.exists())
        contenido = self.fuente.read_text(encoding="utf-8")
        self.assertIn("Estante_Izquierdo", contenido)
        self.assertIn("# pie", contenido)

    def test_escalar_zonas_a_mitad_de_resolucion(self):
        escaladas = zonas.escalar_zonas(UNO, 640, 360, 1280, 720)
        self.assertEqual(escaladas[0]["poligono"], [[5, 0], [25, 0], [25, 50], [5, 50]])

    def test_escalar_zonas_misma_referencia_devuelve_original(self):
        resultado = zonas.escalar_zonas(UNO, 1280, 720, 1280, 720)
        self.assertIs(resultado, UNO)


if __name__ == "__main__":
    unittest.main()