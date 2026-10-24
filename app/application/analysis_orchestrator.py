# APPLICATION / analysis_orchestrator - ciclo de vida de un analisis de video.
#
# Antes este estado vivia como variables sueltas del modulo
# interfaces/api.py (_estado_analisis, _LISTO_ANALIZAR,
# _ULTIMO_VIDEO_ANALIZADO + un threading.Lock), mutadas con `global` desde los
# handlers HTTP. Eso tenia dos problemas: (1) con mas de un worker de uvicorn
# cada proceso ve su propio estado, y (2) los tests solo podian "resetear" el
# estado poke-ando los globals del modulo (api._LISTO_ANALIZAR = None), lo que
# acopla los tests a la implementacion y comparte estado mutable entre ellos.
#
# AnalysisOrchestrator encapsula ese estado en una instancia explicita,
# inyectada en la API via FastAPI Depends(). Un test puede construir su propia
# instancia (o usar `app.dependency_overrides`) en vez de tocar globals.
#
# No sabe COMO se corre el pipeline de verdad (eso es un detalle de
# infraestructura: ver infrastructure/pipeline_runner.py); recibe ese
# comportamiento inyectado como `ejecutor` (puerto: Callable[[video, run_id],
# tuple[bool, str | None]]).

import json
import threading
import time
import uuid
from pathlib import Path


class AnalysisOrchestrator:
    """Orquesta el analisis en curso, el video pendiente de calibrar zonas
    (`listo_analizar`) y el ultimo video analizado (para poder relanzar el
    analisis cuando se re-editan las zonas sin re-subir el video)."""

    def __init__(self, ejecutor, registro_ultimo_video, videos_subidos_dir,
                limpiar_artefactos, conservar_videos_subidos=False):
        self._ejecutor = ejecutor
        self._limpiar_artefactos = limpiar_artefactos
        self._registro_ultimo_video = Path(registro_ultimo_video)
        self._videos_subidos_dir = Path(videos_subidos_dir)
        self._conservar_videos_subidos = conservar_videos_subidos
        self._lock = threading.Lock()
        self._estado = self._estado_inactivo()
        # Video subido por la web, a la espera del analisis: se muestra un
        # fotograma de vista previa para calibrar las zonas y recien
        # POST /api/analizar dispara el pipeline.
        self.listo_analizar = None
        # Ultimo video analizado: se retiene para poder relanzar el analisis
        # cuando el usuario re-edita las zonas (sin volver a subirlo).
        self.ultimo_video_analizado = None

    @staticmethod
    def _estado_inactivo():
        return {
            "estado": "inactivo",
            "run_id": None,
            "progreso_pct": 0,
            "mensaje": "Sin análisis en curso.",
            "error": None,
            "iniciado_en": None,
            "finalizado_en": None,
        }

    # --- estado en memoria del analisis en curso --------------------------------
    def estado_actual(self):
        with self._lock:
            return dict(self._estado)

    def en_curso(self):
        with self._lock:
            return self._estado["estado"] in {"iniciando", "procesando"}

    def _actualizar_estado(self, **cambios):
        with self._lock:
            self._estado.update(cambios)

    # --- "ultimo video analizado", persistido para sobrevivir a un reinicio -----
    def persistir_ultimo_video(self, ruta_video):
        try:
            self._registro_ultimo_video.parent.mkdir(parents=True, exist_ok=True)
            self._registro_ultimo_video.write_text(
                json.dumps({"video": str(ruta_video)}, ensure_ascii=False),
                encoding="utf-8")
        except OSError:
            pass

    def recuperar_ultimo_video(self):
        """Devuelve el ultimo video analizado persistido en disco, solo si
        sigue existiendo."""
        try:
            if not self._registro_ultimo_video.is_file():
                return None
            ruta = Path(json.loads(
                self._registro_ultimo_video.read_text(encoding="utf-8")
            ).get("video", ""))
        except (OSError, json.JSONDecodeError, ValueError):
            return None
        return str(ruta) if ruta.is_file() else None

    def ultimo_video_disponible(self):
        """Ultimo video apto para re-analizar: primero el de memoria, y si el
        servidor se reinicio, el persistido en disco."""
        if (self.ultimo_video_analizado is not None
                and Path(self.ultimo_video_analizado).is_file()):
            return self.ultimo_video_analizado
        recuperado = self.recuperar_ultimo_video()
        if recuperado is not None:
            self.ultimo_video_analizado = recuperado
            return recuperado
        return None

    # --- video pendiente de calibrar ---------------------------------------------
    def info_listo_para_analizar(self):
        """Informacion del video pendiente de analisis, solo si sigue
        disponible en disco (el dashboard la restaura si se recarga la pagina)."""
        if not self.listo_analizar:
            return None
        video = self.listo_analizar["video"]
        preview = self.listo_analizar["preview"]
        if not video.is_file():
            return None
        return {
            "video": video.name,
            "preview": preview.name if preview and preview.is_file() else None,
        }

    # --- ciclo de vida del analisis -----------------------------------------------
    def iniciar_analisis(self, ruta_video):
        """Lanza el pipeline en segundo plano. Devuelve el estado inicial, o
        None si ya hay un analisis en curso (el llamador decide que responder)."""
        run_id = uuid.uuid4().hex
        with self._lock:
            if self._estado["estado"] in {"iniciando", "procesando"}:
                return None
            self._estado.update({
                "estado": "iniciando",
                "run_id": run_id,
                "progreso_pct": 0,
                "mensaje": "Preparando modelos y video.",
                "error": None,
                "video": ruta_video.name,
                "iniciado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "finalizado_en": None,
            })
            # Retener el video analizado para permitir re-analisis al re-editar
            # zonas: se conserva el ultimo y se descarta el retenido anterior
            # (solo si es un video subido, nunca el video base del proyecto).
            if (self.ultimo_video_analizado is not None
                    and self.ultimo_video_analizado != ruta_video
                    and not self._conservar_videos_subidos):
                try:
                    Path(self.ultimo_video_analizado).relative_to(self._videos_subidos_dir)
                except ValueError:
                    pass
                else:
                    Path(self.ultimo_video_analizado).unlink(missing_ok=True)
            self.ultimo_video_analizado = ruta_video
        self.persistir_ultimo_video(ruta_video)

        # Al comenzar se invalidan los artefactos anteriores; asi un fallo
        # nunca termina presentandose como si fueran resultados del video nuevo.
        self._limpiar_artefactos()

        def _run(video_capturado=ruta_video, run_capturado=run_id):
            self._actualizar_estado(estado="procesando",
                                    mensaje="Analizando el video con YOLO.")
            try:
                correcto, detalle_error = self._ejecutor(video_capturado, run_capturado)
            except Exception as exc:
                self._actualizar_estado(
                    estado="error",
                    error=f"{type(exc).__name__}: {exc}",
                    mensaje="No fue posible iniciar el proceso de análisis.",
                    finalizado_en=time.strftime("%Y-%m-%dT%H:%M:%S"),
                )
                return
            if correcto:
                self._actualizar_estado(
                    estado="completado",
                    progreso_pct=100,
                    mensaje="Análisis completado correctamente.",
                    finalizado_en=time.strftime("%Y-%m-%dT%H:%M:%S"),
                )
            else:
                self._actualizar_estado(
                    estado="error",
                    error=detalle_error,
                    mensaje="No fue posible completar el análisis.",
                    finalizado_en=time.strftime("%Y-%m-%dT%H:%M:%S"),
                )

        threading.Thread(target=_run, daemon=True).start()
        return self.estado_actual()

    def reanalizar_si_corresponde(self):
        """Relanza el analisis sobre el ultimo video analizado cuando el
        usuario re-edita las zonas. No hace nada si hay un video pendiente de
        calibrar, si ya hay un analisis en curso o si todavia no se analizo
        ningun video."""
        if self.listo_analizar is not None:
            return False
        ruta = self.ultimo_video_disponible()
        if ruta is None:
            return False
        if self.en_curso():
            return False
        return self.iniciar_analisis(Path(ruta)) is not None

    def reiniciar(self):
        """Invalida el video pendiente de calibrar, el ultimo analizado y el
        estado del analisis en memoria. No borra artefactos en disco (metricas,
        fotogramas): eso lo decide el llamador."""
        if self.listo_analizar:
            try:
                if self.listo_analizar["preview"]:
                    self.listo_analizar["preview"].unlink(missing_ok=True)
            except OSError:
                pass
            self.listo_analizar = None
        self.ultimo_video_analizado = None
        try:
            self._registro_ultimo_video.unlink(missing_ok=True)
        except OSError:
            pass
        with self._lock:
            self._estado = self._estado_inactivo()
