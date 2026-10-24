# INFRASTRUCTURE / pipeline_runner - adaptador que ejecuta el pipeline YOLO
# como subproceso aislado (CLI) y decide si el analisis fue exitoso.
#
# Es el puerto `ejecutor` que consume AnalysisOrchestrator
# (application/analysis_orchestrator.py): el orquestador no sabe que el
# pipeline corre vía subprocess ni donde quedan sus artefactos en disco, solo
# invoca `ejecutor(ruta_video, run_id) -> (correcto, detalle_error)`.

import json
import subprocess
import sys
from pathlib import Path


class SubprocessPipelineRunner:
    """Lanza `python -m app.interfaces.cli` en un subproceso y decide el
    resultado mirando el codigo de salida y los artefactos esperados."""

    def __init__(self, proyecto_root, vision_frames_dir, json_metricas_path,
                vision_frames_index_path, analysis_status_path, analysis_log_path):
        self._root = Path(proyecto_root)
        self._vision_frames_dir = str(vision_frames_dir)
        self._json_metricas = Path(json_metricas_path)
        self._vision_frames_index = Path(vision_frames_index_path)
        self._analysis_status = str(analysis_status_path)
        self._analysis_log = Path(analysis_log_path)

    def ejecutar(self, ruta_video, run_id):
        """Corre el pipeline de forma sincrona (se invoca desde el hilo de
        fondo del orquestador). Devuelve (correcto, detalle_error)."""
        comando = [
            sys.executable, "-m", "app.interfaces.cli",
            "--no-ventana", "--video", str(ruta_video),
            "--guardar-frames", self._vision_frames_dir,
            "--estado-json", self._analysis_status,
            "--run-id", run_id,
        ]
        self._analysis_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self._analysis_log, "w", encoding="utf-8") as log:
            proceso = subprocess.run(
                comando,
                cwd=str(self._root),
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        correcto = (proceso.returncode == 0
                    and self._json_metricas.is_file()
                    and self._vision_frames_index.is_file())
        if correcto:
            return True, None
        return False, self._detalle_error_log()

    def leer_progreso(self, run_id):
        """Progreso publicado por el subproceso (ver app/interfaces/cli.py),
        solo si corresponde al run_id vigente (evita leer el de una corrida
        anterior)."""
        ruta = Path(self._analysis_status)
        if not ruta.exists() or not run_id:
            return {}
        try:
            data = json.loads(ruta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return data if data.get("run_id") == run_id else {}

    def _detalle_error_log(self):
        if not self._analysis_log.exists():
            return "El proceso YOLO terminó con error. Consulta outputs/analysis.log."
        try:
            lineas = [linea.strip() for linea in self._analysis_log.read_text(
                encoding="utf-8", errors="replace").splitlines() if linea.strip()]
        except OSError:
            return "El proceso YOLO terminó con error."
        return lineas[-1][:500] if lineas else "El proceso YOLO terminó con error."
