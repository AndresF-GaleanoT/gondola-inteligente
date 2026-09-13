import unittest

from app.domain.geometria import punto_en_zona
from app.domain.poligonos import es_poligono_valido, punto_en_poligono


class PoligonosTest(unittest.TestCase):
    def test_punto_en_poligono_cuadrilatero(self):
        cuad = [[0, 0], [100, 0], [100, 100], [0, 100]]
        self.assertTrue(punto_en_poligono(50, 50, cuad))
        self.assertTrue(punto_en_poligono(0, 0, cuad))
        self.assertTrue(punto_en_poligono(100, 100, cuad))
        self.assertFalse(punto_en_poligono(150, 50, cuad))
        self.assertFalse(punto_en_poligono(-1, -1, cuad))

    def test_punto_en_poligono_trapecio(self):
        trapecio = [[200, 0], [400, 0], [300, 500], [100, 500]]
        self.assertTrue(punto_en_poligono(250, 200, trapecio))
        self.assertFalse(punto_en_poligono(350, 300, trapecio))

    def test_poligono_autocruzado_invalido(self):
        cruzado = [[0, 0], [100, 100], [0, 100], [100, 0]]
        self.assertFalse(es_poligono_valido(cruzado))

    def test_poligono_convexo_valido(self):
        convexo = [[0, 0], [100, 0], [100, 100], [0, 100]]
        self.assertTrue(es_poligono_valido(convexo))

    def test_area_cero_invalida(self):
        self.assertFalse(es_poligono_valido([[0, 0], [10, 0], [5, 0], [2, 0]]))

    def test_menos_de_tres_puntos_invalido(self):
        self.assertFalse(es_poligono_valido([[0, 0], [10, 0]]))

    def test_punto_en_zona_rectangulo(self):
        self.assertTrue(punto_en_zona(50, 50, (0, 0, 100, 100)))
        self.assertTrue(punto_en_zona(0, 0, (0, 0, 100, 100)))
        self.assertFalse(punto_en_zona(150, 50, (0, 0, 100, 100)))

    def test_punto_en_zona_poligono_equivale_a_punto_en_poligono(self):
        zona = [[0, 0], [100, 0], [100, 100], [0, 100]]
        self.assertTrue(punto_en_zona(25, 25, zona))
        self.assertFalse(punto_en_zona(125, 25, zona))


if __name__ == "__main__":
    unittest.main()