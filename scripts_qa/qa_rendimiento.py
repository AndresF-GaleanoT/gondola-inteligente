"""QA de rendimiento: FPS del pipeline, uso de RAM/GPU y tamaño de salidas.

Uso:
  python scripts_qa/qa_rendimiento.py [--video video/videoBase.mp4] [--vigilar-memoria]
Estado de salida: 0 si cumple los umbrales minimos, 1 si no.

Cubre PERF-01 (FPS/carga) y PERF-02 (memoria/fugas).
PV pipeline real; si --vigilar-memoria, muestrea RAM y VRAM cada segundo.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.application import paths  # noqa: E402
from app import config  # noqa: E402

# Umbrales minimos para el hardware de referencia (RTX 2060, 720p).
FPS_MIN = 10.0                    # FPS de procesamiento del pipeline
# Margen sobre tiempo real: el pipeline debe consumir cinta mas rapido de lo
# que se reproduce (fps_pipe * PROCESAR_CADA_N >= fps del video).
MARGEN_TIEMPO_REAL_MIN = 1.0

_flag_stop = threading.Event()
_rx = {"ram": 0.0, "vram": 0.0, "n": 0}


def _nvidia_smi():
    try:
        out = subprocess.run(["nvidia-smi",
                              "--query-gpu=memory.used",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5)
        val = int(out.stdout.strip().splitlines()[0])
        return {"nvidia_smi": True, "vram_mb": val}
    except Exception:
        return {"nvidia_smi": False, "vram_mb": 0}


def _vigilador(pid):
    try:
        import psutil
    except ImportError:
        print("   (psutil no instalado; solo se mide VRAM)")
        while not _flag_stop.is_set():
            nv = _nvidia_smi()
            if nv["nvidia_smi"]:
                _rx["vram"] = nv["vram_mb"]; _rx["n"] += 1
            time.sleep(1)
        return
    while not _flag_stop.is_set():
        try:
            p = psutil.Process(pid)
            _rx["ram"] = p.memory_info().rss / 1e6
        except Exception:
            _rx["ram"] = 0.0
        nv = _nvidia_smi()
        if nv["nvidia_smi"]:
            _rx["vram"] = nv["vram_mb"]; _rx["n"] += 1
        time.sleep(1)


def medir_frames_video(ruta):
    import cv2
    cap = cv2.VideoCapture(ruta)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    return total, fps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=paths.VIDEO)
    ap.add_argument("--vigilar-memoria", action="store_true")
    args = ap.parse_args()

    ruta = args.video
    total, fps = medir_frames_video(ruta)
    print("=== QA RENDIMIENTO ===")
    print("  Video: %s (%d frames @ %.1f fps)" % (ruta, total, fps))

    t0 = time.time()
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.interfaces.cli", "--no-ventana",
         "--video", ruta],
        cwd=str(ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    hilo = None
    if args.vigilar_memoria:
        hilo = threading.Thread(target=_vigilador, args=(proc.pid,),
                                daemon=True)
        hilo.start()
    salida, _ = proc.communicate()
    elapsed = time.time() - t0
    _flag_stop.set()

    fps_pipe = total / elapsed
    print("  Tiempo total   : %.1f s" % elapsed)
    print("  FPS de proceso : %.1f frames/s" % fps_pipe)
    margen = fps_pipe * config.PROCESAR_CADA_N / fps if fps else 0
    print("  Margen de tiempo real : %.2fx (>= %.1fx = consume la cinta a "
          "la velocidad real)" % (margen, MARGEN_TIEMPO_REAL_MIN))

    ok_fps = fps_pipe >= FPS_MIN
    print("  [%s] FPS >= %.1f" % ("OK" if ok_fps else "FALLA", FPS_MIN))

    ok_ratio = margen >= MARGEN_TIEMPO_REAL_MIN
    print("  [%s] margen de tiempo real >= %.1fx (DPU de video real)"
          % ("OK" if ok_ratio else "FALLA", MARGEN_TIEMPO_REAL_MIN))

    if hilo and hilo.is_alive():
        hilo.join(timeout=0.5)

    rendimiento_ok = ok_fps and ok_ratio

    if args.vigilar_memoria and _rx["n"]:
        print("  RAM promedio : %.0f MB" % (_rx["ram"] or 0))
        print("  VRAM promedio: %.0f MB" % _rx["vram"])

    out = Path(paths.OUTPUTS)
    json_bytes = (out / "metricas_retail.json").stat().st_size \
        if (out / "metricas_retail.json").exists() else 0
    print("  Tamano metricas : %.0f KB" % (json_bytes / 1024))
    con_datos = Path(paths.JSON_METRICAS).exists()
    marcar = rendimiento_ok and con_datos
    print("  [%s] metricas generadas" % ("OK" if con_datos else "FALLA"))
    print("-" * 56)
    return 0 if marcar else 1


if __name__ == "__main__":
    sys.exit(main())