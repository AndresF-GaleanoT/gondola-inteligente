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
    fi = 1
    n = 0
    while fi <= total:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi - 1)
        ok, frame = cap.read()
        if not ok:
            break
        t = fi / fps
        cv2.imwrite(os.path.join(args.out, f"f_{fi:03d}_t{t:04.1f}.png"), frame)
        n += 1
        fi += paso
    cap.release()
    print(f"OK: {n} frames guardados en {args.out} ({args.cada}s, fps={fps:.0f})")


if __name__ == "__main__":
    main()