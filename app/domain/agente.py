# DOMAIN / agente - recomendaciones de planograma (space management) derivadas
# de los datos observados por el pipeline YOLO (visitas, pick-ups, rechazo,
# dwell, presencia y clasificacion).

from ..config import CLASIF_CALIENTE, CLASIF_FRIA


def _pct(v):
    return min(100, max(0, round((v or 0) * 100)))


def recomendar_zona(z):
    """Diagnostico + accion por zona, calculados con sus metricas observadas."""
    nombre = z.get("id", "la zona")
    visitas = z.get("visitas", 0) or 0
    pick = z.get("pick_ups", 0) or 0
    devol = z.get("put_backs", 0) or 0
    rechazo = z.get("tasa_rechazo", 0) or 0
    dwell = z.get("dwell_promedio_seg", 0) or 0
    clasif = z.get("clasificacion", CLASIF_FRIA)

    if clasif == CLASIF_CALIENTE:
        if rechazo > 0.5:
            # Tomar y devolver = el cliente CONSIDERO el producto: interes real.
            return (f"{nombre} es de las zonas mas visitadas y {devol}/{pick} "
                    f"de las tomas se consideran y se dejan de nuevo "
                    f"({_pct(rechazo)}% de consideracion): el producto atrae "
                    f"pero no termina de convencer. Ajusta precio, "
                    f"senalizacion u oferta y revisa el SKU mas considerado: "
                    f"hay demanda latente por capitalizar.")
        return (f"{nombre} muestra el mejor embudo ({pick} pick-ups, "
                f"{round(dwell, 1)} s de permanencia). Refuerza el stock de "
                f"los productos más tomados y conserva el planograma actual.")

    if clasif == "templada":
        return (f"{nombre} es intermedia ({visitas} visitas, {pick} "
                f"interacciones). Tomar y devolver aqui confirma consideracion "
                f"del surtido: ubica en el tercio medio del estante un SKU "
                f"estrella o promo de prueba y observa como cambia la "
                f"consideracion.")

    if visitas > 0 and pick == 0:
        return (f"{nombre} recibe {visitas} visitas pero {pick} interacciones: "
                f"la gente pasa de largo. Reubica la categoría hacia una zona "
                f"caliente o trae tráfico con un display frontal de test.")

    if visitas == 0:
        return (f"{nombre} no registró visitas en el periodo. Acerca una "
                f"categoría de alta rotación desde las zonas calientes o reduce "
                f"la cara de góndola asignada a esta zona.")

    return (f"{nombre} registra {visitas} visitas y {pick} interacciones: es "
            f"una zona fría con tráfico bajo frente a las calientes. Acerca una "
            f"categoría de alta rotación o un display frontal de prueba para "
            f"elevar la consideración.")


def recomendar_planograma(zonas):
    """Propuesta de planograma cuantificada desde lo observado.

    Cruza la zona caliente con la más fría y propone un reparto de espacio
    (facing) proporcional al interes observado (visitas + interacciones).
    """
    caliente = next((z for z in zonas
                     if z.get("clasificacion") == CLASIF_CALIENTE), None)
    frias = sorted([z for z in zonas
                    if z.get("clasificacion") == CLASIF_FRIA],
                   key=lambda z: (z.get("visitas") or 0))
    fria = frias[0] if frias else None

    if not caliente or not fria or caliente["id"] == fria["id"]:
        return {
            "accion": "mantener",
            "texto": ("No hay un desbalance caliente/fria claro hoy: se "
                      "recomienda mantener el layout y revalidar con un "
                      "periodo de observacion mas largo."),
        }

    # Puntaje observado: la interaccion (pick-up) pesa mas que la presencia.
    def _puntaje(z):
        return (z.get("visitas") or 0) * 0.5 + (z.get("pick_ups") or 0) * 3.0

    total = sum(_puntaje(z) for z in zonas) or 1.0
    reparto = {z["id"]: max(0, round(100 * _puntaje(z) / total))
               for z in zonas}

    texto = (
        f"Reubicar la categoria de {fria['id']} ({fria.get('visitas') or 0} "
        f"visitas, {fria.get('pick_ups') or 0} interacciones) hacia "
        f"{caliente['id']} ({caliente.get('pick_ups') or 0} tomas) para "
        f"aprovechar su trafico. Reparto de espacio sugerido por zona "
        f"(% de facing segun interes observado): "
        + ", ".join(f"{k}={v}%" for k, v in reparto.items()) + "."
    )
    return {
        "accion": "reubicar",
        "origen": fria["id"],
        "destino": caliente["id"],
        "facing_pct": reparto,
        "texto": texto,
    }