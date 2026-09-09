# DOMAIN / persona - maquina de estados del cliente y deteccion de interacciones
# (permanencia, alcance al estante, pick-up / put-back).

import numpy as np

from .. import config
from ..config import (ACCION_ADQUIRIDO, ACCION_DEVOLVIENDO,
                      ACCION_INSPECCIONANDO, ACCION_LLEGANDO,
                      ACCION_MANO_EN_ESTANTE, ACCION_TRANSITANDO,
                      COLOR_ADQUIRIDO, COLOR_DEVOLVIENDO,
                      COLOR_INSPECCIONANDO, COLOR_LLEGANDO,
                      COLOR_MANO_EN_ESTANTE, COLOR_TRANSITANDO,
                      IDX_MUNECA_IZQ, IDX_MUNECA_DER, CONF_MANO,
                      MANO_RADIO, MANO_OBJ_TOLERANCIA,
                      MANO_OBJ_TOLERANCIA_RELAJADA,
                      MANO_EN_ZONA_PARA_RETIRAR,
                      MANO_EN_ZONA_CONFIRMA_GESTO, QUIETO_PARA_VER,
                      OBJETO_OBSERVACIONES_CONFIRMAR,
                      OBJETO_OBSERVACIONES_REARMAR,
                      VENTANA_CONFIRMACION_OBJETO,
                      MANO_FUERA_PARA_NUEVO_CONTACTO,
                      VENTANA_OBJETO_AL_ENTRAR,
                      POSESION_DISPARA_PICKUP,
                      UMBRAL_QUIETO, SALIDA_VIENDO, SUAVIZADO_CENTRO,
                      BORRAR_ID_TRAS, COMPONER_TRAYECTORIA_CADA,
                      MAX_TRAYECTORIA_PUNTOS, PROCESAR_CADA_N,
                      VENTANA_SALIDA_OBJETO, VENTANA_DEDUPE_PICKUP, ZONAS)
from .geometria import punto_en_zona


def nueva_persona(centro, fi=0):
    return {
        "frames_quieto": 0,
        "ultimo_centro": centro,
        "accion": ACCION_TRANSITANDO,
        "zona_actual": None,
        "inicio_estante": fi,
        "fin_estante": fi,
        "tiempo_viendo": 0,
        "viendo_desde": None,
        "compro": False,
        "mano_en_zona": 0,
        "mano_estante_frame": None,
        "retirado": False,
        "devolviendo": False,
        "adquirido": False,
        "alcance": False,
        "mano_dentro": False,
        "tiene_objeto_prev": False,
        "posesion_prev": False,
        "posesion_racha": 0,
        "frames_posesion_recientes": [],
        "sin_posesion_racha": 0,
        "pickup_armado": True,
        "pickup_gesto_registrado": False,
        "ultimo_pickup_frame": None,
        "ultimo_contacto_frame": None,
        "ultima_zona_contacto": None,
        "contacto_desde_pickup": False,
        "mano_fuera_racha": 0,
        "nuevo_contacto_armado": False,
        "devolucion_candidata": False,
        "ultimo_frame_posesion": None,
        "zona_anterior": None,
        "ultima_zona": None,
        "eventos": [],
        "trayectoria": [],
    }


def registrar_evento(datos, tipo, fi, zona_id):
    if (datos["eventos"] and
            datos["eventos"][-1]["tipo"] == tipo and
            datos["eventos"][-1]["frame"] >= fi - 1):
        return
    datos["eventos"].append({"tipo": tipo, "frame": fi, "zona": zona_id})


def solapamiento_cajas(caja1, caja2):
    x1_1, y1_1, x2_1, y2_1 = caja1
    x1_2, y1_2, x2_2, y2_2 = caja2
    xi1 = max(x1_1, x1_2)
    yi1 = max(y1_1, y1_2)
    xi2 = min(x2_1, x2_2)
    yi2 = min(y2_1, y2_2)
    return not (xi2 < xi1 or yi2 < yi1)


def _dist_muneca_a_bbox(muneca, bbox):
    """Distancia del punto muneca al rectangulo del objeto (0 si esta dentro)."""
    x, y = muneca
    x1, y1, x2, y2 = bbox
    dx = max(x1 - x, 0, x - x2)
    dy = max(y1 - y, 0, y - y2)
    return float((dx ** 2 + dy ** 2) ** 0.5)


def detectar_posesion_objeto(kps, cajas_objetos):
    """True si alguna muneca se solapa o queda muy cerca de un objeto (en mano).

    Estos son los "frames verdaderos" del gesto: la pose aporta la muneca y el
    detector de objetos una caja de producto solapada/near a ella.
    """
    if kps is None or cajas_objetos is None or cajas_objetos.size == 0:
        return False
    # Radios/tolerancias estan en px calibrados a 720p: se escalan con la
    # resolucion real del video (W_VIDEO se fija en el primer frame).
    escala = config.W_VIDEO / config.ANCHO_REF_ZONAS if config.W_VIDEO > 1 else 1.0
    radio = MANO_RADIO * escala
    tolerancia = MANO_OBJ_TOLERANCIA * escala
    for idx in (IDX_MUNECA_IZQ, IDX_MUNECA_DER):
        x, y, conf = kps[idx]
        if conf >= CONF_MANO:
            caja_mano = (x - radio, y - radio, x + radio, y + radio)
            for obj_box in cajas_objetos:
                if solapamiento_cajas(caja_mano, obj_box):
                    return True
                if _dist_muneca_a_bbox((x, y), obj_box) <= tolerancia:
                    return True
    return False


def detectar_posesion_relajada(kps, cajas_objetos):
    """Criterio de posesion ampliado: la muñeca llega a la caja dentro del radio
    de alcance real (MANO_OBJ_TOLERANCIA + MANO_RADIO). El solape estricto
    muñeca-caja es raro en planos frontales porque los dedos no cubren la caja;
    este margen captura el agarre igualmente, y solo se usa como flanco
    (de False a True) junto con la pertenencia a una zona para no inflar."""
    if kps is None or cajas_objetos is None or cajas_objetos.size == 0:
        return False
    escala = config.W_VIDEO / config.ANCHO_REF_ZONAS if config.W_VIDEO > 1 else 1.0
    tolerancia = MANO_OBJ_TOLERANCIA_RELAJADA * escala
    for idx in (IDX_MUNECA_IZQ, IDX_MUNECA_DER):
        x, y, conf = kps[idx]
        if conf >= CONF_MANO:
            for obj_box in cajas_objetos:
                if _dist_muneca_a_bbox((x, y), obj_box) <= tolerancia:
                    return True
    return False


def clasificar(datos, centro, zona, fi, tiene_objeto):
    """Transicion de estado de alto nivel (permanencia / adquisicion)."""
    en_zona = zona is not None

    if not en_zona:
        if datos.get("adquirido", False):
            return ACCION_ADQUIRIDO, COLOR_ADQUIRIDO

        if datos["accion"] != ACCION_TRANSITANDO:
            registrar_evento(datos, ACCION_TRANSITANDO, fi, None)
            datos["accion"] = ACCION_TRANSITANDO
        datos["zona_actual"] = None
        datos["mano_dentro"] = False
        return ACCION_TRANSITANDO, COLOR_TRANSITANDO

    if datos["adquirido"]:
        return ACCION_ADQUIRIDO, COLOR_ADQUIRIDO

    datos["zona_actual"] = zona["id"]
    ultimo_x, ultimo_y = datos["ultimo_centro"]
    movimiento = abs(centro[0] - ultimo_x) + abs(centro[1] - ultimo_y)

    if datos["accion"] == ACCION_INSPECCIONANDO:
        datos["frames_quieto"] = 0 if movimiento > SALIDA_VIENDO \
            else datos["frames_quieto"] + 1
    else:
        quieto = movimiento < UMBRAL_QUIETO
        datos["frames_quieto"] = datos["frames_quieto"] + 1 if quieto else 0

    if datos.get("retirado", False):
        # La toma se confirma cuando la mano sale del area de agarro con el
        # producto. Mientras siga dentro no se cierra el estado, pues hacerlo
        # aqui impedia reconocer una devolucion posterior.
        return ACCION_INSPECCIONANDO, COLOR_INSPECCIONANDO
    if datos.get("devolviendo", False):
        return ACCION_DEVOLVIENDO, COLOR_DEVOLVIENDO
    if datos.get("mano_dentro", False):
        return ACCION_MANO_EN_ESTANTE, COLOR_MANO_EN_ESTANTE

    accion_previa = datos["accion"]
    if datos["frames_quieto"] > QUIETO_PARA_VER:
        datos["accion"], color = ACCION_INSPECCIONANDO, COLOR_INSPECCIONANDO
    else:
        datos["accion"], color = ACCION_LLEGANDO, COLOR_LLEGANDO

    if datos["accion"] != accion_previa:
        registrar_evento(datos, datos["accion"], fi, zona["id"])

    return datos["accion"], color


def centro_de_caja(caja):
    x1, y1, x2, y2 = caja
    return (int((x1 + x2) / 2), int((y1 + y2) / 2))


def zona_de_visita(centro, zonas):
    """Zona de presencia segun el centro corporal, no segun la muneca.

    Las areas de visita cubren los tres pasillos visibles. Los poligonos de
    agarro permanecen separados y se usan exclusivamente para interacciones.
    """
    for zona in zonas:
        area = zona.get("visita", zona["poligono"])
        if punto_en_zona(centro[0], centro[1], area):
            return zona
    return None


def suavizar(puntos, previo, factor):
    if previo is None:
        return puntos
    return tuple(int(factor * n + (1 - factor) * p)
                 for n, p in zip(puntos, previo))


def muneca_confiable(kps, idx):
    x, y, conf = kps[idx]
    if conf < CONF_MANO:
        return None
    return (float(x), float(y))


def detectar_interaccion_manos(datos, kps, fi, zona, tiene_objeto,
                               cajas_objetos=None):
    """Maquina de estados de la mano (disparada por FLANCOS).

    El gesto se arma con frames verdaderos: la MUNECA (pose) dentro del area de
    agarro durante MANO_EN_ZONA_PARA_RETIRAR frames. La TOMA (pick-up) exige
    ademas que una caja de producto quede solapada/cerca de la muneca
    (tiene_objeto) al retirar la mano; la DEVOLUCION exige haber tomado antes
    (retirado) y volver con la mano vacia al estante. La exactitud contra un
    ground truth se mide con `python -m app.interfaces.validar_embudo`.
    """
    # La senal de posesion se estabiliza temporalmente. Es habitual que el
    # detector encuentre el producto uno o varios frames DESPUES de que la
    # muneca haya salido del estante; por eso no se exige simultaneidad.
    posesion = tiene_objeto or detectar_posesion_relajada(kps, cajas_objetos)
    frames_posesion = datos.setdefault("frames_posesion_recientes", [])
    if posesion:
        datos["posesion_racha"] = datos.get("posesion_racha", 0) + 1
        datos["sin_posesion_racha"] = 0
        datos["ultimo_frame_posesion"] = fi
        frames_posesion.append(fi)
    else:
        datos["posesion_racha"] = 0
        datos["sin_posesion_racha"] = datos.get("sin_posesion_racha", 0) + 1
    frames_posesion[:] = [
        frame for frame in frames_posesion
        if fi - frame <= VENTANA_CONFIRMACION_OBJETO
    ]
    datos["posesion_prev"] = bool(posesion)

    izq = muneca_confiable(kps, IDX_MUNECA_IZQ)
    der = muneca_confiable(kps, IDX_MUNECA_DER)
    mano_en_agarro = bool(zona) and any(
        p is not None and punto_en_zona(*p, zona["agarro"])
        for p in (izq, der)
    )

    entrando_al_agarro = mano_en_agarro and not datos.get("mano_dentro", False)

    if mano_en_agarro:
        datos["mano_en_zona"] += 1
        datos["mano_estante_frame"] = fi
        datos["ultimo_contacto_frame"] = fi
        datos["ultima_zona_contacto"] = zona["id"]
        datos["mano_fuera_racha"] = 0

        # Una posible devolucion requiere una visita NUEVA al estante. Ademas,
        # el producto debe verse al entrar (o pocos frames antes), no solo
        # desaparecer despues de la toma original.
        ultimo_objeto = datos.get("ultimo_frame_posesion")
        objeto_al_entrar = (
            ultimo_objeto is not None
            and fi - ultimo_objeto <= VENTANA_OBJETO_AL_ENTRAR
        )
        if (not datos.get("pickup_armado", True)
                and datos.get("nuevo_contacto_armado", False)
                and entrando_al_agarro
                and objeto_al_entrar):
            datos["contacto_desde_pickup"] = True
            datos["devolucion_candidata"] = True

        if datos["mano_en_zona"] >= MANO_EN_ZONA_PARA_RETIRAR \
                and not datos["mano_dentro"]:
            datos["mano_dentro"] = True
            datos["alcance"] = True
            registrar_evento(datos, ACCION_MANO_EN_ESTANTE, fi, zona["id"])
    else:
        datos["mano_dentro"] = False
        datos["mano_en_zona"] = 0
        if not datos.get("pickup_armado", True):
            datos["mano_fuera_racha"] = datos.get("mano_fuera_racha", 0) + 1
            if datos["mano_fuera_racha"] >= MANO_FUERA_PARA_NUEVO_CONTACTO:
                datos["nuevo_contacto_armado"] = True

    ultimo_contacto = datos.get("ultimo_contacto_frame")
    contacto_reciente = (
        ultimo_contacto is not None
        and fi - ultimo_contacto <= VENTANA_SALIDA_OBJETO
    )
    zona_evento = datos.get("ultima_zona_contacto")

    # TOMA: dos observaciones de producto asociadas a un alcance reciente.
    # Ya no se exige que producto y muneca coincidan dentro del poligono en el
    # mismo frame, que era la causa del conteo 0 en el video de referencia.
    if (POSESION_DISPARA_PICKUP
            and datos.get("pickup_armado", True)
            and len(frames_posesion) >= OBJETO_OBSERVACIONES_CONFIRMAR
            and datos.get("alcance", False)
            and contacto_reciente
            and zona_evento):
        datos["pickup_armado"] = False
        datos["ultimo_pickup_frame"] = fi
        datos["contacto_desde_pickup"] = False
        datos["mano_fuera_racha"] = 0
        datos["nuevo_contacto_armado"] = False
        datos["devolucion_candidata"] = False
        datos["retirado"] = True
        datos["adquirido"] = True
        datos["devolviendo"] = False
        datos["accion"] = ACCION_ADQUIRIDO
        registrar_evento(datos, ACCION_ADQUIRIDO, fi, zona_evento)

    # RESPALDO POR GESTO: algunos productos no son reconocidos por el modelo
    # fine-tuned. Un contacto sostenido durante unas seis observaciones es una
    # senal mas fuerte que una muneca que solo cruza el poligono. Se permite
    # una sola confirmacion por ID; la deduplicacion global absorbe IDs
    # fragmentados de una misma persona.
    elif (datos.get("pickup_armado", True)
            and not datos.get("pickup_gesto_registrado", False)
            and datos["mano_en_zona"] >= MANO_EN_ZONA_CONFIRMA_GESTO
            and datos.get("alcance", False)
            and zona_evento):
        datos["pickup_armado"] = False
        datos["pickup_gesto_registrado"] = True
        datos["ultimo_pickup_frame"] = fi
        datos["contacto_desde_pickup"] = False
        datos["mano_fuera_racha"] = 0
        datos["nuevo_contacto_armado"] = False
        datos["devolucion_candidata"] = False
        datos["retirado"] = True
        datos["adquirido"] = True
        datos["devolviendo"] = False
        datos["accion"] = ACCION_ADQUIRIDO
        registrar_evento(datos, ACCION_ADQUIRIDO, fi, zona_evento)

    # DEVOLUCION: despues de una toma, la persona vuelve a tocar el estante y
    # el producto permanece ausente durante varias observaciones. La espera
    # evita interpretar un parpadeo del detector como devolucion.
    elif (not datos.get("pickup_armado", True)
            and datos.get("contacto_desde_pickup", False)
            and datos.get("devolucion_candidata", False)
            and datos["sin_posesion_racha"] >= OBJETO_OBSERVACIONES_REARMAR
            and not mano_en_agarro
            and zona_evento):
        datos["devolviendo"] = True
        datos["retirado"] = False
        datos["adquirido"] = False
        datos["accion"] = ACCION_DEVOLVIENDO
        registrar_evento(datos, ACCION_DEVOLVIENDO, fi, zona_evento)
        datos["pickup_armado"] = True
        datos["alcance"] = False
        datos["contacto_desde_pickup"] = False
        datos["nuevo_contacto_armado"] = False
        datos["devolucion_candidata"] = False
        frames_posesion.clear()

    # Si el objeto deja de verse lejos del estante, se rearma el detector para
    # una toma posterior, pero NO se inventa una devolucion.
    elif (not datos.get("pickup_armado", True)
            and datos["sin_posesion_racha"] >= OBJETO_OBSERVACIONES_REARMAR
            and not datos.get("contacto_desde_pickup", False)
            and not mano_en_agarro):
        datos["pickup_armado"] = True
        datos["retirado"] = False
        datos["adquirido"] = False
        datos["alcance"] = False
        datos["nuevo_contacto_armado"] = False
        datos["devolucion_candidata"] = False
        frames_posesion.clear()

    if datos.get("devolviendo", False) and not mano_en_agarro:
        datos["devolviendo"] = False
    datos["tiene_objeto_prev"] = bool(tiene_objeto)


def procesar_personas(results, cajas_objetos, personas_estado, analizador, fi,
                      zonas=None, historial=None):
    etiquetas = []
    cajas = results[0].boxes
    if cajas is None or cajas.id is None:
        return etiquetas

    keypoints = (results[0].keypoints.data.cpu().numpy()
                 if results[0].keypoints is not None
                 and len(results[0].keypoints) else None)
    zonas = zonas if zonas is not None else ZONAS

    for i, caja in enumerate(cajas.xyxy.cpu().numpy()):
        tid = int(cajas.id[i])

        if tid not in personas_estado:
            personas_estado[tid] = nueva_persona(centro_de_caja(caja), fi)
        datos = personas_estado[tid]

        centro = suavizar(centro_de_caja(caja), datos["ultimo_centro"],
                          SUAVIZADO_CENTRO)
        zona_visita = zona_de_visita(centro, zonas)

        kps_persona = keypoints[i] if keypoints is not None else None
        # Posesion combinada: solape estricto muñeca-caja o producto dentro del
        # radio de alcance. Es la senal "el cliente lleva un producto en la
        # mano" que alimenta el embudo (pick-up y put-back).
        tiene_objeto = (detectar_posesion_objeto(kps_persona, cajas_objetos)
                        or detectar_posesion_relajada(kps_persona, cajas_objetos))

        # La zona de la persona se decide PRIORIZANDO la muneca (agarro): la
        # mano que toca el estante define la zona del gesto/pick-up. Si no hay
        # muneca fiable se cae al centroide del cuerpo. Asi un pick-up frente a
        # las neveras (derecha) se asigna a Neveras y no a la zona del
        # centroide, que podia caer fuera del poligono.
        zona = None
        if kps_persona is not None:
            for idx in (IDX_MUNECA_IZQ, IDX_MUNECA_DER):
                m = muneca_confiable(kps_persona, idx)
                if m is None:
                    continue
                for z in zonas:
                    if punto_en_zona(m[0], m[1], z["agarro"]):
                        zona = z
                        break
                if zona is not None:
                    break
        if zona is None:
            for z in zonas:
                if punto_en_zona(centro[0], centro[1], z["poligono"]):
                    zona = z
                    break

        if (zona_visita is not None
                and zona_visita["id"] != datos["zona_anterior"]):
            analizador.zonas[zona_visita["id"]]["visitas"] += 1
        datos["zona_anterior"] = (zona_visita["id"]
                                  if zona_visita is not None else None)

        adquirido_antes = datos.get("adquirido", False)
        devolviendo_antes = datos.get("devolviendo", False)
        accion, color = clasificar(datos, centro, zona, fi, tiene_objeto)
        datos["ultimo_centro"] = centro
        datos["visto_en"] = fi

        if fi % COMPONER_TRAYECTORIA_CADA == 0:
            datos["trayectoria"].append((int(fi), centro[0], centro[1]))
            # Cota de memoria: en videos largos la trayectoria podia crecer sin
            # limite; se conservan solo los MAX_TRAYECTORIA_PUNTOS mas recientes.
            if len(datos["trayectoria"]) > MAX_TRAYECTORIA_PUNTOS:
                del datos["trayectoria"][0]

        # Trafico, permanencia y heatmap usan el cuerpo. La maquina de toma
        # conserva `zona`, calculada con la muneca y el area de agarro.
        zona_metricas = zona_visita if zona_visita is not None else zona
        if zona_metricas is not None:
            analizador.actualizar(centro, zona_metricas)
            if accion == ACCION_INSPECCIONANDO:
                if datos["viendo_desde"] is None:
                    datos["viendo_desde"] = fi
                # Se suma el paso real del pipeline: con PROCESAR_CADA_N>1 cada
                # frame procesado equivale a N frames de video y los segundos
                # del detalle (tiempo_viendo_seg) deben reflejar el tiempo real.
                datos["tiempo_viendo"] += PROCESAR_CADA_N
                datos["compro"] = True
            else:
                datos["viendo_desde"] = None
            datos["fin_estante"] = fi
            if zona is not None:
                datos["ultima_zona"] = zona["id"]

        if kps_persona is not None:
            detectar_interaccion_manos(datos, kps_persona, fi, zona,
                                       tiene_objeto, cajas_objetos)
            accion = datos["accion"]
            if datos.get("devolviendo", False):
                color = COLOR_DEVOLVIENDO
            elif datos.get("retirado", False):
                color = COLOR_INSPECCIONANDO
            elif datos.get("mano_dentro", False):
                color = COLOR_MANO_EN_ESTANTE

        zona_contador = zona["id"] if zona is not None \
            else datos.get("ultima_zona")
        if datos.get("adquirido", False) and not adquirido_antes:
            if zona_contador and zona_contador in analizador.zonas:
                zz = analizador.zonas[zona_contador]
                ultimo = zz.get("ultimo_pickup_frame")
                if ultimo is None or fi - ultimo > VENTANA_DEDUPE_PICKUP:
                    zz["pick_ups"] += 1
                    zz["ultimo_pickup_frame"] = fi
        elif (datos.get("devolviendo", False) and not devolviendo_antes
                and zona_contador and zona_contador in analizador.zonas):
            zz = analizador.zonas[zona_contador]
            ultimo = zz.get("ultimo_putback_frame")
            if ultimo is None or fi - ultimo > VENTANA_DEDUPE_PICKUP:
                zz["put_backs"] += 1
                zz["ultimo_putback_frame"] = fi

        x1, y1, _, _ = caja
        etiquetas.append(((int(x1), max(20, int(y1) - 10)),
                          f"ID:{tid} - {accion}", color))

    for tid in [t for t, d in personas_estado.items()
                if fi - d.get("visto_en", fi) > BORRAR_ID_TRAS]:
        # Antes se descartaba el dict y con el se PERDIAN los eventos y la
        # trayectoria de la persona (solo aparecian en el JSON quienes seguian
        # vivos al final del video). Se mueve a un historial que el pipeline
        # exporta al terminar, para conservar el detalle de todos.
        datos_hist = personas_estado.pop(tid)
        if historial is not None:
            historial[tid] = datos_hist

    return etiquetas
