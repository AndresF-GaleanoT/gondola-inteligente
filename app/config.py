# CONFIG - constantes ajustables de la Gondola Inteligente (en un solo lugar).

from .application import paths


# --- Dimensiones reales del video (se fijan con el primer frame) ------------
W_VIDEO = 1
H_VIDEO = 1

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
CONF = 0.25
IOU = 0.45
# Procesa 1 de cada 2 frames (la mitad de inferencias) sin perder el gesto:
# el contador de frames de la mano se suma por frame procesado, asi la logica
# de pick-up/put-back (calibrada en frames procesados) no se ve afectada.
PROCESAR_CADA_N = 2

# El visor web no necesita almacenar todos los frames procesados. Cinco FPS
# conservan fluidez y reducen de forma importante el uso de disco/red.
VISION_FPS_OBJETIVO = 5

# Limite defensivo para videos recibidos por la API. Puede cambiarse con la
# variable de entorno GONDOLA_MAX_VIDEO_MB sin editar el codigo.
MAX_VIDEO_MB = 500

# Los videos subidos se usan como archivos temporales y se borran al terminar.
CONSERVAR_VIDEOS_SUBIDOS = False

# --- Zonas del layout --------------------------------------------------------
# Coordenadas en px del frame de REFERENCIA (1280x720). NO MODIFICAR sin
# recalibrar el video. Se escalan en runtime a la resolucion real (ver
# escalar_zonas).
# Las zonas son franjas verticales (izquierda / centro / derecha) que cubren el
# area real delante de cada estante. `poligono` cubre el cuerpo de la persona;
# `agarro` marca la zona contenida donde la MANO toca el producto/percha (para
# que el gesto entre y salga del agarro y se complete el pick-up). La zona de un
# pick-up se decide priorizando la muneca (agarro) sobre el centroide del cuerpo.
ZONAS = [
    {
        "id": "Estante_Izquierdo",
        # Area amplia del pasillo para contar presencia por centro corporal.
        "visita": [[0, 0], [500, 0], [500, 720], [0, 720]],
        "poligono": [[350, 30], [422, 30], [300, 630], [100, 630]],
        "agarro": [
            [230, 90],   # Ajustado un 5-10% hacia adentro desde las esquinas superiores e inferiores
            [390, 90],
            [270, 570],
            [130, 570]
        ],
    },
    {
        "id": "Estante_Central",
        "visita": [[500, 0], [820, 0], [820, 720], [500, 720]],
        "poligono": [[589, 43], [700, 40], [762, 634], [538, 634]],
        "agarro": [
            [600, 100],
            [680, 100],
            [720, 570],
            [570, 570]
        ],
    },
    {
        "id": "Estante_Derecho",
        "visita": [[820, 0], [1280, 0], [1280, 720], [820, 720]],
        "poligono": [[830, 43], [930, 43], [1200, 634], [1000, 634]],
        "agarro": [
            [850, 100],
            [910, 100],
            [1160, 570],
            [1030, 570]
            ],
    },
]


def escalar_zonas(ancho, alto):
    """Escala las zonas (calibradas a ANCHO_REF_ZONAS x ALTO_REF_ZONAS) hasta
    la resolucion real del video. Si coincide con la referencia se devuelve la
    lista original tal cual (mismo comportamiento que antes).

    El area de "agarro" es un POLIGONO (como en la config original): se escala
    punto a punto para conservar su forma. Antes se reducia a su bounding-box
    (rectangulo), lo que agrandaba la zona de gesto en videos de otra resolucion.
    """
    if ancho == ANCHO_REF_ZONAS and alto == ALTO_REF_ZONAS:
        return ZONAS
    fx, fy = ancho / ANCHO_REF_ZONAS, alto / ALTO_REF_ZONAS
    zonas_escaladas = []
    for z in ZONAS:
        zon = dict(z)
        zon["poligono"] = [[round(x * fx), round(y * fy)] for x, y in z["poligono"]]
        zon["agarro"] = [[round(x * fx), round(y * fy)] for x, y in z["agarro"]]
        zon["visita"] = [[round(x * fx), round(y * fy)] for x, y in z["visita"]]
        zonas_escaladas.append(zon)
    return zonas_escaladas

# --- Clasificacion de comportamiento ----------------------------------------
QUIETO_PARA_VER = 30
UMBRAL_QUIETO = 20
SALIDA_VIENDO = 45

SUAVIZADO_CENTRO = 0.5
BORRAR_ID_TRAS = 90
VENTANA_SALIDA_OBJETO = 48
# Correlacion temporal del gesto. El detector de "producto en mano" suele
# responder despues de que la muneca ya abandono el poligono del estante.
# Se conserva el ultimo contacto durante 2 s (48 frames a 24 FPS), se exigen
# dos observaciones positivas para filtrar destellos y cinco negativas para
# permitir una nueva toma de la misma persona.
OBJETO_OBSERVACIONES_CONFIRMAR = 2
# Las observaciones positivas no tienen que ser consecutivas: el detector de
# producto suele parpadear entre fotogramas. Dos aciertos dentro de esta
# ventana confirman la posesion sin convertir un unico destello en una toma.
VENTANA_CONFIRMACION_OBJETO = 16
OBJETO_OBSERVACIONES_REARMAR = 5
# Una devolucion solo puede empezar en un contacto NUEVO con el estante y con
# el producto visible al entrar. Esto evita confundir la perdida de deteccion
# posterior a una toma con una devolucion real.
MANO_FUERA_PARA_NUEVO_CONTACTO = 4
VENTANA_OBJETO_AL_ENTRAR = 6
# Deduplica pick-ups: si se registra otro pick-up en la MISMA zona dentro de
# esta ventana de frames, se considera el mismo evento (los trackers pueden
# dividir un unico evento en varios IDs en el mismo instante).
VENTANA_DEDUPE_PICKUP = 25

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
COLOR_INSPECCIONANDO = (0, 165, 255)
COLOR_LLEGANDO = (0, 255, 255)
COLOR_TRANSITANDO = (255, 0, 0)
COLOR_ZONA = (0, 255, 0)
COLOR_MANO_EN_ESTANTE = (0, 255, 255)
COLOR_DEVOLVIENDO = (255, 0, 255)
COLOR_ADQUIRIDO = (0, 255, 127)

ACCION_INSPECCIONANDO = "Inspeccionar Producto"
ACCION_LLEGANDO = "Alcanzar Estante"
ACCION_TRANSITANDO = "En Tránsito"
ACCION_MANO_EN_ESTANTE = "Mano en Estante"
ACCION_DEVOLVIENDO = "Devolver el producto"
ACCION_ADQUIRIDO = "Producto Adquirido"

# --- Gesto de interaccion (pick-up / put-back) -------------------------------
IDX_MUNECA_IZQ = 9
IDX_MUNECA_DER = 10
CONF_MANO = 0.30
MANO_EN_ZONA_PARA_RETIRAR = 2
# Respaldo cuando el modelo de producto no reconoce el SKU: un contacto
# sostenido de la muneca con la gondola confirma una toma por gesto.
MANO_EN_ZONA_CONFIRMA_GESTO = 6
CONF_OBJETOS = 0.30
MANO_RADIO = 70
MANO_OBJ_TOLERANCIA = 95
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

MOSTRAR_RESUMEN = True

# --- Heatmap de trafico ------------------------------------------------------
MOSTRAR_HEATMAP = True
HEATMAP_FACTOR = 12.0
HEATMAP_RADIO = 26
HEATMAP_ALPHA = 0.45

# --- Clasificacion de zonas calientes/frias ----------------------------------
CLASIF_CALIENTE = "caliente"
CLASIF_TEMPLADA = "templada"
CLASIF_FRIA = "fria"
