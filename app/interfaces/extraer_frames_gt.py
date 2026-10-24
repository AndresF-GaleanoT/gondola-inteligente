# INTERFACES / extraer_frames_gt - saca frames de un video para anotar el GT.
#   python -m app.interfaces.extraer_frames_gt --video video/2.mp4 --cada 0.5
#   (--cada = s entre frames; guarda PNG en outputs/frames_gt/).

import argparse
import os
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUT = str(ROOT / "outputs" / "frames_gt")


def main():
    ap = argparse.ArgumentParser(description="Extrae frames para anotar GT.")
    ap.add_argument("--video", required=True, help="Ruta del video.")
    ap.add_argument("--cada", type=float, default=0.5,
                    help="Intervalo en segundos entre frames (default 0.5).")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="Directorio de salida.")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    os.makedirs(args.out, exist_ok=True)

    paso = max(1, int(round(fps * args.cada)))
    indice_frame = 1
    guardados = 0
    while indice_frame <= total:
        cap.set(cv2.CAP_PROP_POS_FRAMES, indice_frame - 1)
        ok, frame = cap.read()
        if not ok:
            break
        segundo = indice_frame / fps
        cv2.imwrite(os.path.join(args.out, f"f_{indice_frame:03d}_t{segundo:04.1f}.png"), frame)
        guardados += 1
        indice_frame += paso
    cap.release()
    print(f"OK: {guardados} frames guardados en {args.out} ({args.cada}s, fps={fps:.0f})")


if __name__ == "__main__":
    main()