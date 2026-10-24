import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from app.application.analysis_orchestrator import AnalysisOrchestrator


class EjecutorFalso:
    """Ejecutor de pipeline de prueba: no corre ningun subproceso, solo
    registra la llamada y devuelve el resultado configurado. Permite probar
    el AnalysisOrchestrator aislado de FastAPI y del subproceso real."""

    def __init__(self, resultado=(True, None)):
        self.resultado = resultado
        self.llamadas = []

    def __call__(self, ruta_video, run_id):
        self.llamadas.append((ruta_video, run_id))
        return self.resultado


class EjecutorBloqueante:
    """Ejecutor que no termina hasta que el test lo libera explicitamente
    (`liberar()`), para poder probar deterministicamente el caso "ya hay un
    analisis en curso" sin depender de una carrera entre hilos."""

    def __init__(self):
        self.listo_para_terminar = threading.Event()
        self.en_ejecucion = threading.Event()

    def __call__(self, ruta_video, run_id):
        self.en_ejecucion.set()
        self.listo_para_terminar.wait(timeout=5)
        return True, None

    def liberar(self):
        self.listo_para_terminar.set()


class AnalysisOrchestratorTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        base = Path(self._dir.name)
        self.registro = base / "ultimo_video_analizado.json"
        self.videos_subidos = base / "subidos"
        self.videos_subidos.mkdir()
        self.limpiezas = []
        self.ejecutor = EjecutorFalso()
        self.orq = AnalysisOrchestrator(
            ejecutor=self.ejecutor,
            registro_ultimo_video=self.registro,
            videos_subidos_dir=self.videos_subidos,
            limpiar_artefactos=lambda: self.limpiezas.append(1),
        )
        self.video = self.videos_subidos / "clip.mp4"
        self.video.write_bytes(b"v")

    def tearDown(self):
        self._dir.cleanup()

    def _esperar_hilo(self, intentos=50):
        for _ in range(intentos):
            if self.orq.estado_actual()["estado"] in {"completado", "error"}:
                return
            time.sleep(0.01)
        self.fail("El analisis en segundo plano no terminó a tiempo.")

    def test_estado_inicial_inactivo(self):
        estado = self.orq.estado_actual()
        self.assertEqual(estado["estado"], "inactivo")
        self.assertFalse(self.orq.en_curso())

    def test_iniciar_analisis_corre_el_ejecutor_y_marca_completado(self):
        # El EjecutorFalso es sincrono/instantaneo: el hilo de fondo puede
        # terminar antes de que el assert se ejecute, asi que no se fija un
        # estado transitorio concreto (iniciando/procesando), solo que el
        # ciclo se completo correctamente.
        iniciado = self.orq.iniciar_analisis(self.video)
        self.assertIsNotNone(iniciado)
        self._esperar_hilo()
        self.assertEqual(self.orq.estado_actual()["estado"], "completado")
        self.assertEqual(self.ejecutor.llamadas[0][0], self.video)
        self.assertEqual(self.orq.ultimo_video_analizado, self.video)
        # Limpia artefactos previos y persiste el ultimo video analizado.
        self.assertEqual(len(self.limpiezas), 1)
        self.assertEqual(json.loads(self.registro.read_text(encoding="utf-8")),
                         {"video": str(self.video)})

    def test_iniciar_analisis_rechaza_si_ya_hay_uno_en_curso(self):
        bloqueante = EjecutorBloqueante()
        orq = AnalysisOrchestrator(
            ejecutor=bloqueante,
            registro_ultimo_video=self.registro,
            videos_subidos_dir=self.videos_subidos,
            limpiar_artefactos=lambda: None,
        )
        orq.iniciar_analisis(self.video)
        self.assertTrue(bloqueante.en_ejecucion.wait(timeout=5))
        try:
            segundo = orq.iniciar_analisis(self.video)
            self.assertIsNone(segundo)
        finally:
            bloqueante.liberar()

    def test_ejecutor_que_falla_marca_estado_error(self):
        orq = AnalysisOrchestrator(
            ejecutor=EjecutorFalso((False, "el modelo no cargó")),
            registro_ultimo_video=self.registro,
            videos_subidos_dir=self.videos_subidos,
            limpiar_artefactos=lambda: None,
        )
        orq.iniciar_analisis(self.video)
        for _ in range(50):
            if orq.estado_actual()["estado"] == "error":
                break
            time.sleep(0.01)
        estado = orq.estado_actual()
        self.assertEqual(estado["estado"], "error")
        self.assertEqual(estado["error"], "el modelo no cargó")

    def test_ejecutor_que_lanza_excepcion_marca_estado_error(self):
        def ejecutor_roto(ruta_video, run_id):
            raise RuntimeError("yolo no disponible")

        orq = AnalysisOrchestrator(
            ejecutor=ejecutor_roto,
            registro_ultimo_video=self.registro,
            videos_subidos_dir=self.videos_subidos,
            limpiar_artefactos=lambda: None,
        )
        orq.iniciar_analisis(self.video)
        for _ in range(50):
            if orq.estado_actual()["estado"] == "error":
                break
            time.sleep(0.01)
        self.assertIn("yolo no disponible", orq.estado_actual()["error"])

    def test_reanalizar_si_corresponde_usa_el_ultimo_video_analizado(self):
        self.orq.iniciar_analisis(self.video)
        self._esperar_hilo()
        reanalizado = self.orq.reanalizar_si_corresponde()
        self.assertTrue(reanalizado)
        self._esperar_hilo()
        self.assertEqual(len(self.ejecutor.llamadas), 2)

    def test_reanalizar_si_corresponde_no_hace_nada_sin_video_previo(self):
        self.assertFalse(self.orq.reanalizar_si_corresponde())

    def test_reanalizar_si_corresponde_no_hace_nada_con_video_pendiente(self):
        self.orq.iniciar_analisis(self.video)
        self._esperar_hilo()
        self.orq.listo_analizar = {"video": self.video, "preview": None}
        self.assertFalse(self.orq.reanalizar_si_corresponde())

    def test_ultimo_video_disponible_se_recupera_de_disco_tras_reinicio(self):
        self.orq.persistir_ultimo_video(self.video)
        orq_nuevo = AnalysisOrchestrator(
            ejecutor=self.ejecutor,
            registro_ultimo_video=self.registro,
            videos_subidos_dir=self.videos_subidos,
            limpiar_artefactos=lambda: None,
        )
        self.assertIsNone(orq_nuevo.ultimo_video_analizado)
        self.assertEqual(orq_nuevo.ultimo_video_disponible(), str(self.video))

    def test_reiniciar_borra_video_pendiente_y_estado(self):
        preview = self.videos_subidos / "preview.jpg"
        preview.write_bytes(b"p")
        self.orq.listo_analizar = {"video": self.video, "preview": preview}
        self.orq.ultimo_video_analizado = self.video
        self.orq.persistir_ultimo_video(self.video)

        self.orq.reiniciar()

        self.assertIsNone(self.orq.listo_analizar)
        self.assertIsNone(self.orq.ultimo_video_analizado)
        self.assertFalse(preview.exists())
        self.assertFalse(self.registro.exists())
        self.assertEqual(self.orq.estado_actual()["estado"], "inactivo")

    def test_iniciar_analisis_descarta_el_video_subido_anterior(self):
        otro_video = self.videos_subidos / "anterior.mp4"
        otro_video.write_bytes(b"v")
        self.orq.ultimo_video_analizado = otro_video

        self.orq.iniciar_analisis(self.video)
        self._esperar_hilo()

        self.assertFalse(otro_video.exists())
        self.assertEqual(self.orq.ultimo_video_analizado, self.video)


if __name__ == "__main__":
    unittest.main()
