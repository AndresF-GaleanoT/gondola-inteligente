# DOMAIN / constantes - vocabulario de dominio (acciones, colores de render y
# clasificacion de zonas). Vive en domain/ y no importa nada externo: antes
# estas constantes estaban en app/config.py, lo que hacia que el dominio
# dependiera de la capa de configuracion/aplicacion (violacion de la regla de
# dependencia). config.py las reexporta para no romper a quien ya las importa
# desde ahi.

# --- Colores de render por accion (BGR, para overlay de OpenCV) -------------
COLOR_INSPECCIONANDO = (0, 165, 255)
COLOR_LLEGANDO = (0, 255, 255)
COLOR_TRANSITANDO = (255, 0, 0)
COLOR_ZONA = (0, 255, 0)
COLOR_MANO_EN_ESTANTE = (0, 255, 255)
COLOR_DEVOLVIENDO = (255, 0, 255)
COLOR_ADQUIRIDO = (0, 255, 127)

# --- Acciones/estados de la maquina de estados del cliente -------------------
ACCION_INSPECCIONANDO = "Inspeccionar Producto"
ACCION_LLEGANDO = "Alcanzar Estante"
ACCION_TRANSITANDO = "En Tránsito"
ACCION_MANO_EN_ESTANTE = "Mano en Estante"
ACCION_DEVOLVIENDO = "Devolver el producto"
ACCION_ADQUIRIDO = "Producto Adquirido"

# --- Clasificacion de zonas calientes/frias -----------------------------------
CLASIF_CALIENTE = "caliente"
CLASIF_TEMPLADA = "templada"
CLASIF_FRIA = "fria"
