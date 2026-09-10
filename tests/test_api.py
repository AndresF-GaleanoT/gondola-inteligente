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

    def tearDown(self):
        api._LISTO_ANALIZAR = None

    def test_estado_publica_un_estado_explicito(self):
        respuesta = self.client.get("/api/estado")
        self.assertEqual(respuesta.status_code, 200)
        cuerpo = respuesta.json()
        self.assertIn(cuerpo["estado"], {
            "inactivo", "iniciando", "procesando", "completado", "error",
        })
        self.assertIn("analisis_en_curso", cuerpo)
        self.assertIn("listo_para_analizar", cuerpo)

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

    def test_video_valido_queda_listo_para_analizar_sin_disparar(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "video.mp4"
            with patch.object(api, "_ruta_guardado_video", return_value=destino), \
                    patch.object(api, "_extraer_preview", side_effect=lambda v: None), \
                    patch.object(api, "_iniciar_analisis") as iniciar:
                respuesta = self.client.post(
                    "/api/video",
                    files={"archivo": ("video.mp4", b"video", "video/mp4")},
                )
        self.assertEqual(respuesta.status_code, 200)
        cuerpo = respuesta.json()
        self.assertEqual(cuerpo["estado"], "listo_para_analizar")
        self.assertEqual(cuerpo["video"], "video.mp4")
        self.assertIsNone(cuerpo["preview"])
        iniciar.assert_not_called()
        self.assertIsNotNone(api._LISTO_ANALIZAR)

    def test_estado_publica_el_video_listo_para_analizar(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "pend.mp4"
            preview = Path(tmp) / "pv.jpg"
            video.write_bytes(b"v")
            preview.write_bytes(b"p")
            api._LISTO_ANALIZAR = {"video": video, "preview": preview}
            respuesta = self.client.get("/api/estado")
        self.assertEqual(respuesta.status_code, 200)
        cuerpo = respuesta.json()
        self.assertEqual(cuerpo["listo_para_analizar"],
                         {"video": "pend.mp4", "preview": "pv.jpg"})

    def test_estado_no_publica_preview_eliminada_en_disco(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "pend.mp4"
            preview = Path(tmp) / "pv.jpg"
            video.write_bytes(b"v")
            api._LISTO_ANALIZAR = {"video": video, "preview": preview}
            respuesta = self.client.get("/api/estado")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["listo_para_analizar"],
                         {"video": "pend.mp4", "preview": None})

    def test_analizar_usa_el_video_pendiente_al_omitir_ruta(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "pend.mp4"
            video.write_bytes(b"v")
            api._LISTO_ANALIZAR = {"video": video, "preview": None}
            estado = {"run_id": "prueba-2"}
            with patch.object(api, "_iniciar_analisis", return_value=estado) as iniciar:
                respuesta = self.client.post("/api/analizar")
        self.assertEqual(respuesta.status_code, 202)
        self.assertEqual(respuesta.json()["run_id"], "prueba-2")
        iniciar.assert_called_once_with(video, eliminar_al_final=True)
        self.assertIsNone(api._LISTO_ANALIZAR)


class ZonasApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app)

    def tearDown(self):
        # Siempre se deja la configuracion en valores de fabrica y sin runtime.
        self.client.post("/api/zonas/restablecer")

    def test_lista_zonas_con_formato_y_referencia(self):
        respuesta = self.client.get("/api/zonas")
        self.assertEqual(respuesta.status_code, 200)
        cuerpo = respuesta.json()
        self.assertEqual(cuerpo["referencia"], [1280, 720])
        self.assertIn(cuerpo["fuente"], {"default", "runtime"})
        self.assertEqual({z["id"] for z in cuerpo["zonas"]},
                         {"Estante_Izquierdo", "Estante_Central",
                          "Estante_Derecho"})
        for z in cuerpo["zonas"]:
            self.assertEqual(len(z["poligono"]), 4)
            self.assertEqual(len(z["agarro"]), 4)

    def test_persiste_edicion_y_restablece(self):
        # Parte de una base conocida (fábrica), sin depender de ediciones previas.
        self.client.post("/api/zonas/restablecer")
        inicial = self.client.get("/api/zonas").json()
        zonas = inicial["zonas"]
        zonas[0]["poligono"][0] = [390, 12]
        guardado = self.client.put("/api/zonas", json={"zonas": zonas})
        self.assertEqual(guardado.status_code, 200)
        self.assertEqual(guardado.json()["fuente"], "runtime")
        leidas = self.client.get("/api/zonas").json()
        self.assertEqual(leidas["zonas"][0]["poligono"][0], [390, 12])
        self.assertEqual(leidas["fuente"], "runtime")
        self.assertTrue(Path("config/zonas_runtime.json").exists())
        restauradas = self.client.post("/api/zonas/restablecer")
        self.assertEqual(restauradas.status_code, 200)
        self.assertEqual(restauradas.json()["fuente"], "default")
        self.assertFalse(Path("config/zonas_runtime.json").exists())

    def test_rechaza_zonas_invalidas(self):
        invalidas = [
            {"id": "Zona_uno", "poligono": [[0, 0], [0, 0], [1, 0], [1, 0]],
             "agarro": [[0, 0], [1, 0], [2, 0], [3, 0]]},
        ]
        respuesta = self.client.put("/api/zonas", json={"zonas": invalidas})
        self.assertEqual(respuesta.status_code, 400)

    def test_rechaza_vertices_fuera_del_frame(self):
        zonas = self.client.get("/api/zonas").json()["zonas"]
        zonas[0]["poligono"][0] = [1290, 0]
        respuesta = self.client.put("/api/zonas", json={"zonas": zonas})
        self.assertEqual(respuesta.status_code, 400)


if __name__ == "__main__":
    unittest.main()
