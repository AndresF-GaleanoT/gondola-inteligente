# INTERFACES / cli - adaptador delgado que invoca app/use_cases/procesar_video.py.
#   python -m app.interfaces.cli [--video ruta] [--no-ventana]
#   [--gt JSON --umbral-f1 0.8] [--tol N] [--no-sanity]

import argparse
import json
import sys
import time
from pathlib import Path

from ..config import JSON_METRICAS
from ..use_cases.procesar_video import procesar_video
from .validar_embudo import validar_metricas


def _escribir_estado(ruta, run_id, estado, **extra):
    """Publica progreso de forma atomica para que la API pueda consultarlo."""
    if not ruta:
        return
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    contenido = {
        "run_id": run_id,
        "estado": estado,
        "actualizado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
        **extra,
    }
    temporal = destino.with_suffix(destino.suffix + ".tmp")
    temporal.write_text(json.dumps(contenido, ensure_ascii=False),
                        encoding="utf-8")
    temporal.replace(destino)


def main():
    parser = argparse.ArgumentParser(description="Pipeline YOLO de RetailVision Edge AI (Góndola Inteligente)")
    parser.add_argument("--video", default=None, help="Ruta opcional del video a analizar")
    parser.add_argument("--no-ventana", action="store_true",
                        help="Modo headless: no abre ventana OpenCV (procesa "
                             "solo metricas). Lo usa el backend al disparar el "
                             "pipeline en background; el CLI local lo omite para "
                             "ver el render en pantalla.")
    parser.add_argument("--gt", default=None,
                        help="Ruta del JSON de ground truth para validar el "
                             "embudo tras exportar (precision/recall/F1).")
    parser.add_argument("--umbral-f1", type=float, default=None,
                        help="Exigir F1 >= este valor y fallar si no se cumple "
                             "(con --gt).")
    parser.add_argument("--tol", type=int, default=15,
                        help="Ventana de frames para el match vs GT (default 15).")
    parser.add_argument("--no-sanity", action="store_true",
                        help="Omite el chequeo de coherencia del JSON.")
    parser.add_argument("--guardar-frames", default=None,
                        help="Carpeta donde guardar los fotogramas anotados "
                             "(zonas, etiquetas y heatmap) como JPEG + indice.")
    parser.add_argument("--estado-json", default=None,
                        help="Archivo JSON opcional donde publicar el progreso.")
    parser.add_argument("--run-id", default=None,
                        help="Identificador de la ejecucion iniciado por la API.")
    args = parser.parse_args()

    def reportar(frame, total):
        porcentaje = round(frame / total * 100, 1) if total else None
        _escribir_estado(args.estado_json, args.run_id, "procesando",
                         frame=frame, total_frames=total,
                         progreso_pct=porcentaje)

    _escribir_estado(args.estado_json, args.run_id, "iniciando",
                     frame=0, total_frames=0, progreso_pct=0)
    try:
        procesar_video(
            ruta_video=args.video,
            mostrar_ventana=not args.no_ventana,
            guardar_frames=args.guardar_frames,
            emitir_progreso=reportar,
        )
    except Exception as exc:
        _escribir_estado(args.estado_json, args.run_id, "error",
                         error=f"{type(exc).__name__}: {exc}")
        raise

    _escribir_estado(args.estado_json, args.run_id, "completado",
                     progreso_pct=100)

    if args.gt:
        resultado_validacion = validar_metricas(
            json.load(open(JSON_METRICAS, encoding="utf-8")),
            ruta_gt=args.gt, tol=args.tol,
            umbral_f1=args.umbral_f1,
            sanity=not args.no_sanity,
        )
        if args.umbral_f1 is not None and not (resultado_validacion["f1_ok"] and resultado_validacion["sanity_ok"]):
            sys.exit("VALIDACION NO SUPERADA: F1 por debajo del umbral o "
                     "incoherencias de sanity.")


if __name__ == "__main__":
    main()
