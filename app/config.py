# CONFIG - constantes ajustables de la Gondola Inteligente (en un solo lugar).
#
# Las ZONAS ya NO viven en un global mutable de este modulo: el acceso
# `config.ZONAS` (y `from .config import ZONAS`) se resuelve en caliente via
# __getattr__ (al final del archivo) contra `zona_repository`, un
# ZonaRepository (puerto en application/zona_repository.py, adaptador JSON en
# infrastructure/zona_repository_json.py). Antes, guardar/restablecer zonas
# reescribia este mismo archivo por AST; ahora las zonas de fabrica viven en
# config/zonas_default.json (solo lectura) y las personalizadas en
# config/zonas_runtime.json. config.py sigue siendo el "cableado" (composition
# root) de esa dependencia, pero sin estado mutable propio.

from .application import paths
from .application import zonas as _zonas
from .infrastructure.zona_repository_json import JsonZonaRepository


# --- Dimensiones reales del video (se fijan con el primer frame) ------------
W_VIDEO = 1
H_VIDEO = 1

# --- Subida de videos (dashboard) --------------------------------------------
# Limite maximo por video subido via POST /api/video. Se puede sobrescribir con
# la variable de entorno GONDOLA_MAX_VIDEO_MB. Los videos subidos son temporales
# y se eliminan al terminar el analisis salvo que CONSERVAR_VIDEOS_SUBIDOS=True.
MAX_VIDEO_MB = 500
CONSERVAR_VIDEOS_SUBIDOS = False

# --- Zonas: calibracion de referencia ----------------------------------------
# Las zonas se calibraron a mano sobre un frame 1280x720. Para soportar videos
# de cualquier resolucion se escalan a la del video real (escalar_zonas), de
# modo que poligonos y area de "agarro" queden proporcionales al frame.
ANCHO_REF_ZONAS = 1280
ALTO_REF_ZONAS = 720

# --- Rutas y modelos ---------------------------------------------------------
MODELO_POSE = paths.MODELO_POSE
MODELO_OBJETOS = paths.MODELO_OBJETOS
CLASES_POSESION = (0, 1)
TRACKER = paths.TRACKER
VIDEO = paths.VIDEO
JSON_METRICAS = paths.JSON_METRICAS

# --- Deteccion / tracking ----------------------------------------------------
# IMGSZ alto para leer personas lejanas/pequenas; 960 es un buen balance entre
# precision y consumo (1280 casi duplicaba el coste de inferencia).
IMGSZ = 960
# El detector de producto en mano opera a 640 por defecto (base), pero las
# cajas pequenas en planos lejanos se pierden; a 960 (igual que la pose) se
# duplican las detecciones sin cambiar el coste de forma apreciable.
IMGSZ_OBJETOS = 960
CONF = 0.25
IOU = 0.45
# Procesa 1 de cada 4 frames (la mitad de inferencias que antes, ~2x mas rapido)
# sin perder el gesto: el contador de frames de la mano se suma por frame
# procesado, asi la logica de pick-up/put-back (calibrada en frames procesados)
# no se ve afectada. Bajar a 2 sube precision temporal a costa de ~2x mas tiempo.
PROCESAR_CADA_N = 4
# FPS objetivo del visor de fotogramas anotados: el pipeline guarda JPEGs a
# esta cadencia para no producir miles de imagenes innecesarias en videos
# largos (la inferencia corre a PROCESAR_CADA_N frames, mayoritariamente).
VISION_FPS_OBJETIVO = 5

# --- Zonas del layout --------------------------------------------------------
# Coordenadas en px del frame de REFERENCIA (1280x720). Se escalan en runtime
# a la resolucion real del video (ver escalar_zonas).
# Las zonas son franjas verticales (izquierda / centro / derecha) que cubren el
# area real delante de cada estante. `poligono` cubre el cuerpo de la persona;
# `agarro` marca la zona contenida donde la MANO toca el producto/percha (para
# que el gesto entre y salga del agarro y se complete el pick-up). La zona de un
# pick-up se decide priorizando la muneca (agarro) sobre el centroide del cuerpo.
#
# Las zonas de FABRICA viven en config/zonas_default.json (solo lectura, no se
# reescribe nunca). El editor web (GET/PUT /api/zonas) persiste su personalizacion
# en config/zonas_runtime.json, que el pipeline prioriza al importar. Ese
# contrato de persistencia esta detras del puerto ZonaRepository.
DEFAULT_ZONAS = str(paths.CONFIG_DIR / "zonas_default.json")
RUNTIME_ZONAS = str(paths.CONFIG_DIR / "zonas_runtime.json")

zona_repository = JsonZonaRepository(RUNTIME_ZONAS, DEFAULT_ZONAS,
                                      ANCHO_REF_ZONAS, ALTO_REF_ZONAS)


def validar_zonas(zonas):
    """Valida las zonas del editor contra el frame de referencia."""
    return _zonas.validar_zonas(zonas, ANCHO_REF_ZONAS, ALTO_REF_ZONAS)


def guardar_zonas(zonas):
    """Persiste las zonas del editor (vía zona_repository) y devuelve la lista
    validada."""
    return zona_repository.guardar(zonas)


def restablecer_zonas():
    """Vuelve a las zonas de fabrica (vía zona_repository)."""
    return zona_repository.restablecer()


def escalar_zonas(ancho, alto):
    """Escala las zonas vigentes (calibradas a ANCHO_REF_ZONAS x ALTO_REF_ZONAS)
    hasta la resolucion real del video. Si coincide con la referencia se
    devuelve la lista original tal cual (mismo comportamiento que antes).

    El area de "agarro" es un POLIGONO (como en la config original): se escala
    punto a punto para conservar su forma. Antes se reducia a su bounding-box
    (rectangulo), lo que agrandaba la zona de gesto en videos de otra resolucion.
    """
    return _zonas.escalar_zonas(zona_repository.obtener(), ancho, alto,
                                ANCHO_REF_ZONAS, ALTO_REF_ZONAS)


def __getattr__(nombre):
    """Resuelve `config.ZONAS` (y `from app.config import ZONAS`) en caliente
    contra zona_repository, en vez de cachear un global que quedaba
    desactualizado hasta la proxima reescritura manual (PEP 562)."""
    if nombre == "ZONAS":
        return zona_repository.obtener()
    raise AttributeError(f"module {__name__!r} has no attribute {nombre!r}")

# --- Clasificacion de comportamiento ----------------------------------------
QUIETO_PARA_VER = 30
UMBRAL_QUIETO = 20
SALIDA_VIENDO = 45

SUAVIZADO_CENTRO = 0.5
BORRAR_ID_TRAS = 90
VENTANA_SALIDA_OBJETO = 48
# Deduplica pick-ups: si se registra otro pick-up en la MISMA zona dentro de
# esta ventana de frames, se considera el mismo evento (los trackers pueden
# dividir un unico evento en varios IDs en el mismo instante).
VENTANA_DEDUPE_PICKUP = 25
# Ventana tras un pick-up dentro de la cual una mano vuelve al estante VACIA
# (sin producto) cuenta como devolucion (put-back). Despues de esta ventana se
# trata como una nueva visita y no como una devolucion: evita falsos put-backs
# cuando el cliente regresa al mismo estante mucho despues de tomar.
VENTANA_DEVOLUCION = 300

# Separacion minima (frames) entre la toma y un put-back por gesto. Evita que
# la propia posada que confirmo la toma se interprete tambien como devolucion;
# coincide con la confirmacion minima de contacto sostenido.
MIN_DEVOLUCION_INICIO = 6

COMPONER_TRAYECTORIA_CADA = 10
# Cota superior de puntos de trayectoria por persona (el video puede tener
# miles de frames; mas alla de esto la trayectoria no aporta al dashboard).
MAX_TRAYECTORIA_PUNTOS = 200
HEATMAP_EXPORT_CELDAS = 96

# --- Anonimizacion (Ley 1581 de 2012 - Colombia) ----------------------------
# Kernel 61x61 (con sigma 24) sigue siendo GRANDE comparado con el rostro
# (~55-70 px de ancho): borra identidad al 100%, pero cuesta ~40% menos CPU
# que el antiguo 99x99 (~30 ms/frame con 8 cabezas en 720p).
TAM_BLUR = 61
SIGMA_BLUR = 24
CONF_CABEZA_KP = 0.30
CABEZA_ANCHO = 0.45
CABEZA_ALTO = 0.40
CABEZA_CENTRO_Y = 0.50
SUAVIZADO_CABEZA = 0.5

# --- Colores y etiquetas de accion -------------------------------------------
# Vocabulario de dominio: vive en domain/constantes.py (el dominio no debe
# depender de config) y se reexporta aqui para no romper a quien ya importaba
# estos nombres desde app.config.
from .domain.constantes import (  # noqa: E402,F401
    COLOR_INSPECCIONANDO, COLOR_LLEGANDO, COLOR_TRANSITANDO, COLOR_ZONA,
    COLOR_MANO_EN_ESTANTE, COLOR_DEVOLVIENDO, COLOR_ADQUIRIDO,
    ACCION_INSPECCIONANDO, ACCION_LLEGANDO, ACCION_TRANSITANDO,
    ACCION_MANO_EN_ESTANTE, ACCION_DEVOLVIENDO, ACCION_ADQUIRIDO,
)

# --- Gesto de interaccion (pick-up / put-back) -------------------------------
IDX_MUNECA_IZQ = 9
IDX_MUNECA_DER = 10
CONF_MANO = 0.30
MANO_EN_ZONA_PARA_RETIRAR = 2
CONF_OBJETOS = 0.30
MANO_RADIO = 70
MANO_OBJ_TOLERANCIA = 95
# Respaldo por GESTO (pick-up): si el detector de producto fine-tuned no
# reconoce el objeto, un contacto sostenido de la muneca con el area de agarro
# durante esta cantidad de observaciones confirma la toma (la muneca que solo
# cruza el poligono o un destello de unos frames no cuentan). Ver
# detectar_interaccion_manos en app/domain/persona.py.
MANO_EN_ZONA_CONFIRMA_GESTO = 6
# Posesion "relajada": el producto esta dentro del radio de alcance real de la
# mano (tolerancia + radio). En planos frontales el solape estricto muñeca-caja
# es raro (los dedos no cubren la caja), asi que este margen detecta el agarre
# sin exigir que la muñeca toque la caja.
MANO_OBJ_TOLERANCIA_RELAJADA = MANO_OBJ_TOLERANCIA + MANO_RADIO
# Flanco de posesion: si la muneca toca/queda junto a una caja de "producto"
# (tiene_objeto) y la persona esta dentro de una zona, se registra la TOMA
# aunque la muneca no este formalmente dentro del poligono de agarro (en planos
# reales el agarro suele quedar corto respecto al alcance real de la mano).
POSESION_DISPARA_PICKUP = True
# Observaciones consecutivas de producto (frames procesados con caja visible)
# necesarias para confirmar una TOMA y descartar destellos del detector.
OBJETO_OBSERVACIONES_CONFIRMAR = 2
# Ventana (en frames procesados) en la que se conserva el historial reciente de
# posesion para confirmar la toma; frames mas viejos no cuentan.
VENTANA_CONFIRMACION_OBJETO = 16
# Observaciones sin producto necesarias para permitir una nueva toma de la
# misma persona tras la anterior (evita doble conteo por parpadeo).
OBJETO_OBSERVACIONES_REARMAR = 5
# Frames con la mano fuera del area de agarro que deben acumularse para
# considerar "nuevo contacto" y poder armar una devolucion/pick-up siguiente.
MANO_FUERA_PARA_NUEVO_CONTACTO = 4
# Ventana (frames procesados) en la que el producto debe haberse visto AL
# ENTRAR al estante para validar una candidata de devolucion.
VENTANA_OBJETO_AL_ENTRAR = 6

MOSTRAR_RESUMEN = True

# --- Heatmap de trafico ------------------------------------------------------
MOSTRAR_HEATMAP = True
HEATMAP_FACTOR = 12.0
HEATMAP_RADIO = 26
HEATMAP_ALPHA = 0.45

# --- Clasificacion de zonas calientes/frias ----------------------------------
# (tambien vocabulario de dominio; ver nota junto a las constantes de accion)
from .domain.constantes import CLASIF_CALIENTE, CLASIF_TEMPLADA, CLASIF_FRIA  # noqa: E402,F401
