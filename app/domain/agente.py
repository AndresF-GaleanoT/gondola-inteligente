# DOMAIN / agente - recomendaciones de planograma (space management) derivadas
# de los datos observados por el pipeline YOLO (visitas, pick-ups, rechazo,
# dwell, presencia y clasificacion).

from .constantes import CLASIF_CALIENTE, CLASIF_TEMPLADA, CLASIF_FRIA


def _pct(valor):
    return min(100, max(0, round((valor or 0) * 100)))


def recomendar_zona(zona):
    """Diagnostico + accion por zona, calculados con sus metricas observadas."""
    nombre = zona.get("id", "la zona")
    visitas = zona.get("visitas", 0) or 0
    pick_ups = zona.get("pick_ups", 0) or 0
    devoluciones = zona.get("put_backs", 0) or 0
    tasa_rechazo = zona.get("tasa_rechazo", 0) or 0
    dwell_prom = zona.get("dwell_promedio_seg", 0) or 0
    clasificacion = zona.get("clasificacion", CLASIF_FRIA)

    if clasificacion == CLASIF_CALIENTE:
        if tasa_rechazo > 0.5:
            # Tomar y devolver = el cliente CONSIDERO el producto: interes real.
            return (f"{nombre} es de las zonas mas visitadas y {devoluciones}/{pick_ups} "
                    f"de las tomas se consideran y se dejan de nuevo "
                    f"({_pct(tasa_rechazo)}% de consideracion): el producto atrae "
                    f"pero no termina de convencer. Ajusta precio, "
                    f"senalizacion u oferta y revisa el SKU mas considerado: "
                    f"hay demanda latente por capitalizar.")
        return (f"{nombre} muestra el mejor embudo ({pick_ups} pick-ups, "
                f"{round(dwell_prom, 1)} s de permanencia). Refuerza el stock de "
                f"los productos más tomados y conserva el planograma actual.")

    if clasificacion == CLASIF_TEMPLADA:
        return (f"{nombre} es intermedia ({visitas} visitas, {pick_ups} "
                f"interacciones). Tomar y devolver aqui confirma consideracion "
                f"del surtido: ubica en el tercio medio del estante un SKU "
                f"estrella o promo de prueba y observa como cambia la "
                f"consideracion.")

    sin_interaccion = visitas > 0 and pick_ups == 0
    if sin_interaccion:
        return (f"{nombre} recibe {visitas} visitas pero {pick_ups} interacciones: "
                f"la gente pasa de largo. Reubica la categoría hacia una zona "
                f"caliente o trae tráfico con un display frontal de test.")

    if visitas == 0:
        return (f"{nombre} no registró visitas en el periodo. Acerca una "
                f"categoría de alta rotación desde las zonas calientes o reduce "
                f"la cara de góndola asignada a esta zona.")

    return (f"{nombre} registra {visitas} visitas y {pick_ups} interacciones: es "
            f"una zona fría con tráfico bajo frente a las calientes. Acerca una "
            f"categoría de alta rotación o un display frontal de prueba para "
            f"elevar la consideración.")


def _puntaje_interes(zona):
    """Puntaje observado: la interaccion (pick-up) pesa mas que la presencia."""
    return (zona.get("visitas") or 0) * 0.5 + (zona.get("pick_ups") or 0) * 3.0


def recomendar_planograma(zonas):
    """Propuesta de planograma cuantificada desde lo observado.

    Cruza la zona caliente con la más fría y propone un reparto de espacio
    (facing) proporcional al interes observado (visitas + interacciones).
    """
    zona_caliente = next(
        (z for z in zonas if z.get("clasificacion") == CLASIF_CALIENTE), None
    )
    candidatas_frias = sorted(
        (z for z in zonas if z.get("clasificacion") == CLASIF_FRIA),
        key=lambda z: (z.get("visitas") or 0),
    )
    zona_fria = candidatas_frias[0] if candidatas_frias else None

    sin_desbalance = not zona_caliente or not zona_fria or zona_caliente["id"] == zona_fria["id"]
    if sin_desbalance:
        return {
            "accion": "mantener",
            "texto": ("No hay un desbalance caliente/fria claro hoy: se "
                      "recomienda mantener el layout y revalidar con un "
                      "periodo de observacion mas largo."),
        }

    puntaje_total = sum(_puntaje_interes(z) for z in zonas) or 1.0
    reparto = {
        z["id"]: max(0, round(100 * _puntaje_interes(z) / puntaje_total))
        for z in zonas
    }

    texto = (
        f"Reubicar la categoria de {zona_fria['id']} ({zona_fria.get('visitas') or 0} "
        f"visitas, {zona_fria.get('pick_ups') or 0} interacciones) hacia "
        f"{zona_caliente['id']} ({zona_caliente.get('pick_ups') or 0} tomas) para "
        f"aprovechar su trafico. Reparto de espacio sugerido por zona "
        f"(% de facing segun interes observado): "
        + ", ".join(f"{k}={v}%" for k, v in reparto.items()) + "."
    )
    return {
        "accion": "reubicar",
        "origen": zona_fria["id"],
        "destino": zona_caliente["id"],
        "facing_pct": reparto,
        "texto": texto,
    }
