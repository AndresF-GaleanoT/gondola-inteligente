import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError as exc:
    raise unittest.SkipTest("FastAPI no está instalado en este entorno") from exc

from app.interfaces import api


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app)

    def test_estado_publica_un_estado_explicito(self):
        respuesta = self.client.get("/api/estado")
        self.assertEqual(respuesta.status_code, 200)
        cuerpo = respuesta.json()
        self.assertIn(cuerpo["estado"], {
            "inactivo", "iniciando", "procesando", "completado", "error",
        })
        self.assertIn("analisis_en_curso", cuerpo)

    def test_datos_no_disfraza_el_demo_como_resultado_real(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(api, "JSON_METRICAS", str(Path(tmp) / "sin_datos.json")):
            respuesta = self.client.get("/api/datos")
        self.assertEqual(respuesta.status_code, 404)

    def test_rechaza_extension_que_no_es_video(self):
        respuesta = self.client.post(
            "/api/video",
            files={"archivo": ("datos.txt", b"contenido", "video/mp4")},
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_video_valido_inicia_en_background(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "video.mp4"
            estado = {"run_id": "prueba-1"}
            with patch.object(api, "_ruta_guardado_video", return_value=destino), \
                    patch.object(api, "_iniciar_analisis", return_value=estado):
                respuesta = self.client.post(
                    "/api/video",
                    files={"archivo": ("video.mp4", b"video", "video/mp4")},
                )
        self.assertEqual(respuesta.status_code, 202)
        self.assertEqual(respuesta.json()["run_id"], "prueba-1")


if __name__ == "__main__":
    unittest.main()
