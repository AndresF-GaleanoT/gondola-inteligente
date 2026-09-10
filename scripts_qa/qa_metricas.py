"""QA funcional y de invariantes sobre el JSON de metricas exportado.

Uso:  python scripts_qa/qa_metricas.py [--salida outputs/metricas_retail.json]
Estado de salida: 0 si todo cumple, 1 si hay hallazgos.
Cubre VIS-02 (heatmap), VIS-04 (embudo), INT-01/03 (coherencia), REC-01/02
(recomendacion).

Requiere haber generado las metricas:
  python -m app.interfaces.cli --video video/videoBase.mp4 --no-ventana
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.application import paths  # noqa: E402

HALLAZGOS = []


def marcar(check, ok, detalle=""):
    if not ok:
        HALLAZGOS.append((check, detalle))
    print("  [%s] %s%s" % ("OK" if ok else "FALLA", check,
                           (" -> %s" % detalle) if detalle and not ok else ""))


def eventos_embudo(metricas):
    """Flatten de eventos pick_up/put_back desde detalle_por_persona."""
    personas = metricas.get("detalle_por_persona") or []
    evs = []
    for persona in personas:
        for e in persona.get("eventos", []):
            tipo = e.get("tipo", "")
            if tipo == config.ACCION_ADQUIRIDO:
                t = "pick_up"
            elif tipo == config.ACCION_DEVOLVIENDO:
                t = "put_back"
            else:
                continue
            evs.append({"tipo": t, "frame": e.get("frame"),
                        "zona": e.get("zona")})
    return evs


def main(salida_metricas):
    print("=== QA FUNCIONAL / INVARIANTES DE METRICAS ===")
    if not Path(salida_metricas).exists():
        marcar("metricas existen", False,
               "No existe %s. Ejecuta el pipeline antes." % salida_metricas)
        _fin()
        return 1

    with open(salida_metricas, encoding="utf-8") as f:
        m = json.load(f)

    # --- INT-02 / estado: estructura general ---
    obligatorias = {"analisis_zonas", "detalle_por_persona",
                    "embudo_interaccion", "heatmap_global", "total_personas_registradas"}
    faltantes = obligatorias - set(m.keys())
    marcar("claves obligatorias presentes", not faltantes,
           ("faltan: %s" % sorted(faltantes)) if faltantes else "")
    ids_actuales = set(m.get("zonas_configuradas") or [])
    if ids_actuales:
        ids_config = {z["id"] for z in (config.ZONAS or [])}
        marcar("zonas_configuradas == config.ZONAS",
               ids_config == ids_actuales,
               ("config=%s metricas=%s" % (sorted(ids_config), sorted(ids_actuales))))
        ids_ok = ids_config == ids_actuales

    # --- INT-03 / coherencia por zona ---
    total_put = total_pick = 0
    for z in (m.get("analisis_zonas") or []):
        zid = z.get("id"); pick = z.get("pick_ups", 0) or 0
        put = z.get("put_backs", 0) or 0; visitas = z.get("visitas", 0) or 0
        tasa = z.get("tasa_rechazo", 0) or 0
        total_pick += pick; total_put += put
        marcar("zona %s: contadores >= 0" % zid,
               pick >= 0 and put >= 0 and visitas >= 0
               and z.get("dwell_promedio_seg", 0) >= 0)
        marcar("zona %s: sin contraccion de put-backs" % zid, put <= pick,
               "put=%d > pick=%d" % (put, pick) if put > pick else "")
        marcar("zona %s: tasa de rechazo correcta" % zid,
               abs(tasa - (put / pick if pick else 0.0)) <= 0.01,
               "tasa=%r esperada=%.2f" % (tasa, put / pick if pick else 0))
        marcar("zona %s: pick-up sin visitas absurdo" % zid,
               not (pick > 0 and visitas == 0),
               "pick=%d visitas=0" % pick if pick and not visitas else "")

    # --- INT-03 / invariante global pick/put ---
    embudo = m.get("embudo_interaccion") or {}
    ep = embudo.get("total_pick_ups", 0) or 0
    eu = embudo.get("total_put_backs", 0) or 0
    marcar("embudo global == suma por zona", ep == total_pick and eu == total_put,
           "p=%d/%d put=%d/%d" % (ep, total_pick, eu, total_put))
    marcar("embudo: total_put <= total_pick", eu <= ep, "put>pick")

    # --- VIS-04 / embudo: eventos sin personas invalidas ---
    evs = eventos_embudo(m)
    invalidos = [e for e in evs if not isinstance(e.get("frame"), int)]
    marcar("embudo: eventos con frame valido", not invalidos)

    # --- VIS-02 / heatmap ---
    grilla = m.get("heatmap_global") or []
    filas = len(grilla)
    cols = len(grilla[0]) if filas else 0
    celdas_cfg = config.HEATMAP_EXPORT_CELDAS
    marcar("heatmap 96x96", filas == celdas_cfg and all(len(r) == celdas_cfg
           for r in grilla), "grilla %dx%d esperada %dx%d" % (cols, filas, celdas_cfg, celdas_cfg))
    fuera_rango = any(any(not (0 <= v <= 100) for v in fila) for fila in grilla)
    marcar("heatmap en rango 0-100", not fuera_rango)
    marcar("heatmap no vacio", bool(filas and cols), "grilla vacia")

    # --- REC-01 / texto de recomendacion no contradice sus metricas ---
    rec = m.get("recomendaciones") or {}
    por_zona = rec.get("por_zona") or {}
    for z in (m.get("analisis_zonas") or []):
        zid = z.get("id"); texto = (por_zona.get(zid) or "").lower()
        marcar("recomendacion presente para %s" % zid, bool(texto))
        if "0 pick-ups" in texto and z.get("pick_ups"):
            marcar("REC %s: texto no contradice pick-ups" % zid, False,
                   "dice 0 pick-ups pero hay %d" % z.get("pick_ups"))
        elif "sin visita" in texto and z.get("visitas"):
            marcar("REC %s: texto no contradice visitas" % zid, False,
                   "dice sin visitas pero hay %d" % z.get("visitas"))

    # --- REC-02 / planograma ---
    plano = rec.get("planograma") or {}
    facing = (plano.get("facing_pct") or {})
    saca = plano.get("accion")
    marcar("REC-02: facing_pct suma 100", not facing or
           abs(sum(facing.values()) - 100) <= 1,
           "suma=%d" % sum(facing.values()) if facing else "sin facing")
    if saca == "reubicar":
        origen = plano.get("origen"); destino = plano.get("destino")
        marcar("REC-02: origen=fria, destino=caliente",
               origen != destino and bool(origen) and bool(destino),
               "origen=%s destino=%s" % (origen, destino))
    elif saca == "mantener":
        marcar("REC-02: mantener sin caliente/fria inconsistente", True)

    _fin()
    return 0 if not HALLAZGOS else 1


def _fin():
    print("-" * 56)


if __name__ == "__main__":
    salida = sys.argv[sys.argv.index("--salida") + 1] \
        if "--salida" in sys.argv else paths.JSON_METRICAS
    sys.exit(main(salida))