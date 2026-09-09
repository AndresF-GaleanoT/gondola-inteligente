# INFRASTRUCTURE / vision - adaptadores a YOLO y captura de video
# (aisla la dependencia de ultralytics/cv2 del resto de la aplicacion).

import cv2
import numpy as np

from ..config import (MODELO_POSE, MODELO_OBJETOS, TRACKER, VIDEO,
                      IMGSZ, CONF, IOU, CONF_OBJETOS, CLASES_POSESION)


class DetectorPoseYObjetos:
    """Carga los dos modelos YOLO (pose de personas + estado de producto)."""

    def __init__(self):
        from ultralytics import YOLO
        self.model_pose = YOLO(MODELO_POSE)
        self.model_objs = YOLO(MODELO_OBJETOS)
        self.es_posesion = self._es_modelo_posesion(self.model_objs)

    @staticmethod
    def _es_modelo_posesion(modelo):
        """True si el detector de objetos es el fine-tune de estados de producto
        (tiene la clase 'Object In Hand'), en cuyo caso solo cuentan las clases
        de posesion; False si es el yolov8n COCO generico (se excluye 'person')."""
        names = getattr(modelo, "names", None) or {}
        return "Object In Hand" in [str(n) for n in names.values()]

    def detectar_objetos(self, frame):
        """Devuelve cajas de objetos en posesion real (filtradas por clase)."""
        res_objs = self.model_objs(frame, conf=CONF_OBJETOS, verbose=False)
        cajas_objetos = np.array([])
        if res_objs[0].boxes is not None and len(res_objs[0].boxes):
            b = res_objs[0].boxes
            xyxy = b.xyxy.cpu().numpy()
            cls = b.cls.cpu().numpy().astype(int)
            if self.es_posesion:
                keep = [c in CLASES_POSESION for c in cls]
            else:
                keep = [c != 0 for c in cls]
            cajas_objetos = xyxy[keep]
        return cajas_objetos

    def rastrear_personas(self, frame):
        """Detecta y rastrea personas (solo clase persona) con pose y track."""
        return self.model_pose.track(frame, persist=True, tracker=TRACKER,
                                     classes=0, conf=CONF, iou=IOU,
                                     imgsz=IMGSZ)


class CapturaVideo:
    """Wrapper del videocapturer de OpenCV."""

    def __init__(self, ruta_video=VIDEO):
        self.cap = cv2.VideoCapture(ruta_video)
        if not self.cap.isOpened():
            self.cap.release()
            raise FileNotFoundError(
                f"No se pudo abrir el video: {ruta_video}")

    @property
    def fps(self):
        return self.cap.get(cv2.CAP_PROP_FPS) or 30.0

    @property
    def total_frames(self):
        return max(0, int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)))

    def leer(self):
        return self.cap.read()

    def liberar(self):
        self.cap.release()
