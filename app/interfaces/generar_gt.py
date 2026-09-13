# INTERFACES / generar_gt - genera un GT candidato a partir de lo que el
# pipeline detecto, para que el humano solo REVISE/EDITE frames en vez de
# anotar el GT de cero.
#   python -m app.interfaces.generar_gt [--metricas outputs/metricas_retail.json]
#                                      [--out ground_truth/candidatos.json]
#   Luego: editar candidatos.json (frames/tipo/zona) y validar con
#   python -m app.interfaces.validar_embudo --gt ground_truth/candidatos.json

import argparse
import json
import sys
from pathlib import Path

from ..config import JSON_METRICAS
from .validar_embudo import eventos_detectados

DEFAULT_OUT = str(Path(__file__).resolve().parent.parent.parent
                  / "ground_truth" / "candidatos.json")

NOTA = (
    "Candidato generado automaticamente por el pipeline. REVISA cada evento y\n"
    "corrige el frame/tipo/zona si hace falta. Dejar 'zona' vacio (null) hace\n"
    "que el match no exija una zona concreta. Cuando quede listo, valida con:\n"
    "  python -m app.interfaces.validar_embudo --gt {out}"
)


def main():
    ap = argparse.ArgumentParser(description="Genera un GT candidato desde el "
                                             "JSON de metricas del pipeline.")
    ap.add_argument("--metricas", default=JSON_METRICAS,
                    help="JSON exportado por el pipeline.")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="Ruta de salida del GT candidato.")
    ap.add_argument("--video", default=None,
                    help="Etiqueta opcional del video (metadato del GT).")
    args = ap.parse_args()

    ruta_m = Path(args.metricas)
    if not ruta_m.exists():
        sys.exit(f"Metricas no encontradas: {ruta_m}")
    with open(ruta_m, encoding="utf-8") as f:
        metricas = json.load(f)

    eventos = eventos_detectados(metricas)
    salida = Path(args.out)
    salida.parent.mkdir(parents=True, exist_ok=True)

    gt = {
        "video": args.video
        or metricas.get("videofuente")
        or metricas.get("video")
        or "(indica el video aqui)",
        "nota": NOTA.format(out=args.out),
        "eventos": [
            {"frame": e["frame"], "tipo": e["tipo"], "zona": e.get("zona")}
            for e in sorted(eventos, key=lambda e: e["frame"])
        ],
    }
    salida.write_text(json.dumps(gt, ensure_ascii=False, indent=2),
                      encoding="utf-8")

    print(f"[OK] GT candidato guardado en {salida} ({len(eventos)} eventos).")
    if not eventos:
        print("  [AVISO] El pipeline no detecto pick-ups/put-backs: el GT queda "
              "vacio (o anota los eventos a mano revisando el video).")
    print("  Siguiente paso: revisar/editar el JSON y luego:")
    print(f"    python -m app.interfaces.validar_embudo --gt {args.out}")


if __name__ == "__main__":
    main()