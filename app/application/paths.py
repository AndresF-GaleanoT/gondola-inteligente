# PATHS - rutas del proyecto resueltas desde la raiz del repo.

from pathlib import Path

# El paquete 'app' vive en la raiz del repo.
APP_DIR = Path(__file__).resolve().parent.parent
ROOT = APP_DIR.parent

# --- Directorios / rutas base -------------------------------------------------
MODELS = ROOT / "models"
VIDEO_DIR = ROOT / "video"
CONFIG_DIR = ROOT / "config"
OUTPUTS = ROOT / "outputs"
FRONTEND = ROOT / "frontend"

# --- Archivos concretos --------------------------------------------------------
MODELO_POSE = str(MODELS / "yolo11n-pose.pt")
MODELO_OBJETOS = str(MODELS / "yolov8n-producto-mano.pt")
TRACKER = str(CONFIG_DIR / "tracker_store.yaml")
VIDEO = str(VIDEO_DIR / "videoBase.mp4")
JSON_METRICAS = str(OUTPUTS / "metricas_retail.json")
# Fotogramas anotados de la "vision de las gondolas": el pipeline los guarda
# como JPEG (los navegadores no decodifican el codec mp4v del OpenCV, asi que
# el dashboard los reproduce como secuencia animada en vez de un <video>).
VISION_FRAMES = str(OUTPUTS / "vision_frames")
VISION_FRAMES_INDEX = str(OUTPUTS / "vision_frames_index.json")
ANALYSIS_STATUS = str(OUTPUTS / "analysis_status.json")
ANALYSIS_LOG = str(OUTPUTS / "analysis.log")

FRONTEND_DIST = FRONTEND / "dist"
FRONTEND_PUBLIC = FRONTEND / "public"
FALLBACK_JSON = str(FRONTEND_PUBLIC / "datos.json")
