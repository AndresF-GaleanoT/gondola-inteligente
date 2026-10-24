import json
import tempfile
import unittest
from pathlib import Path

from app.application import zonas
from app.config import ALTO_REF_ZONAS, ANCHO_REF_ZONAS
from app.infrastructure.zona_repository_json import JsonZonaRepository

UNO = [{"id": "Z1",
        "poligono": [[10, 0], [50, 0], [50, 100], [10, 100]],
        "agarro": [[12, 2], [48, 2], [48, 90], [12, 90]]}]

PREDETERMINADAS = [{"id": "Z0",
                    "poligono": [[0, 0], [40, 0], [40, 80], [0, 80]],
                    "agarro": [[2, 2], [38, 2], [38, 70], [2, 70]]}]


class ZonasTest(unittest.TestCase):
    """Funciones puras de app/application/zonas.py (sin AST, sin tocar .py)."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.runtime = Path(self._dir.name) / "zonas_runtime.json"

    def tearDown(self):
        self._dir.cleanup()

    def test_validar_zonas_rechaza_coordenadas_fuera(self):
        con_fuera = [dict(UNO[0], poligono=[[10, 0], [50, 0], [50, 5000], [10, 100]])]
        with self.assertRaises(ValueError):
            zonas.validar_zonas(con_fuera, ANCHO_REF_ZONAS, ALTO_REF_ZONAS)

    def test_validar_zonas_rechaza_autocruzado(self):
        cruzado = [dict(UNO[0], poligono=[[0, 0], [100, 100], [0, 100], [100, 0]])]
        with self.assertRaises(ValueError):
            zonas.validar_zonas(cruzado, ANCHO_REF_ZONAS, ALTO_REF_ZONAS)

    def test_guardar_zonas_escribe_solo_el_runtime(self):
        guardadas = zonas.guardar_zonas(UNO, ANCHO_REF_ZONAS, ALTO_REF_ZONAS,
                                        self.runtime)
        self.assertEqual(guardadas, UNO)
        self.assertEqual(json.loads(self.runtime.read_text(encoding="utf-8")),
                         UNO)

    def test_guardar_zonas_no_escribe_si_invalidas(self):
        malas = [[], None]
        for mal in malas:
            with self.assertRaises(ValueError):
                zonas.guardar_zonas(mal, ANCHO_REF_ZONAS, ALTO_REF_ZONAS,
                                    self.runtime)
            self.assertFalse(self.runtime.exists())

    def test_cargar_prioriza_runtime_valido(self):
        self.runtime.write_text(json.dumps(UNO), encoding="utf-8")
        cargadas = zonas.cargar_zonas(self.runtime, PREDETERMINADAS,
                                      ANCHO_REF_ZONAS, ALTO_REF_ZONAS)
        self.assertEqual(cargadas, UNO)

    def test_cargar_descarta_runtime_corrupto(self):
        self.runtime.write_text("{no es json", encoding="utf-8")
        cargadas = zonas.cargar_zonas(self.runtime, PREDETERMINADAS,
                                      ANCHO_REF_ZONAS, ALTO_REF_ZONAS)
        self.assertEqual(cargadas, PREDETERMINADAS)

    def test_restablecer_borra_runtime_y_devuelve_predeterminadas(self):
        self.runtime.write_text(json.dumps(UNO), encoding="utf-8")
        restauradas = zonas.restablecer_zonas(PREDETERMINADAS, self.runtime)
        self.assertEqual(restauradas, PREDETERMINADAS)
        self.assertFalse(self.runtime.exists())

    def test_escalar_zonas_a_mitad_de_resolucion(self):
        escaladas = zonas.escalar_zonas(UNO, 640, 360, 1280, 720)
        self.assertEqual(escaladas[0]["poligono"], [[5, 0], [25, 0], [25, 50], [5, 50]])

    def test_escalar_zonas_misma_referencia_devuelve_original(self):
        resultado = zonas.escalar_zonas(UNO, 1280, 720, 1280, 720)
        self.assertIs(resultado, UNO)


class JsonZonaRepositoryTest(unittest.TestCase):
    """Adaptador del puerto ZonaRepository: ningun archivo .py se toca aqui,
    solo el JSON de runtime (el de fabrica es de solo lectura)."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        base = Path(self._dir.name)
        self.runtime = base / "zonas_runtime.json"
        self.default = base / "zonas_default.json"
        self.default.write_text(json.dumps(PREDETERMINADAS), encoding="utf-8")
        self.repo = JsonZonaRepository(self.runtime, self.default,
                                       ANCHO_REF_ZONAS, ALTO_REF_ZONAS)

    def tearDown(self):
        self._dir.cleanup()

    def test_obtener_sin_runtime_devuelve_predeterminadas(self):
        self.assertEqual(self.repo.obtener(), PREDETERMINADAS)
        self.assertEqual(self.repo.fuente(), "default")

    def test_guardar_persiste_y_pasa_a_fuente_runtime(self):
        guardadas = self.repo.guardar(UNO)
        self.assertEqual(guardadas, UNO)
        self.assertEqual(self.repo.obtener(), UNO)
        self.assertEqual(self.repo.fuente(), "runtime")
        # El archivo de fabrica nunca se modifica.
        self.assertEqual(json.loads(self.default.read_text(encoding="utf-8")),
                         PREDETERMINADAS)

    def test_restablecer_vuelve_a_predeterminadas(self):
        self.repo.guardar(UNO)
        restauradas = self.repo.restablecer()
        self.assertEqual(restauradas, PREDETERMINADAS)
        self.assertEqual(self.repo.fuente(), "default")

    def test_guardar_invalidas_lanza_y_no_persiste(self):
        with self.assertRaises(ValueError):
            self.repo.guardar([])
        self.assertEqual(self.repo.fuente(), "default")


if __name__ == "__main__":
    unittest.main()
