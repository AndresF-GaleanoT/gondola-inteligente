# INTERFACES / validar_embudo - precision/recall/F1 del embudo (pick-up/put-back)
# contra un ground truth ({frame, tipo, zona}) y chequeo de coherencia del JSON.
#   python -m app.interfaces.validar_embudo --gt ground_truth/candidatos.json [--tol N]
#   python -m app.interfaces.validar_embudo --metricas ruta.json [--no-sanity]
#   python -m app.interfaces.validar_embudo --gt ruta.json --barrido-tol

import argparse
import json
import sys
from pathlib import Path

from ..config import ACCION_ADQUIRIDO, ACCION_DEVOLVIENDO, JSON_METRICAS

FRAME_TOL_DEFECTO = 15


def eventos_detectados(metricas):
    """Extrae pick-ups/put-backs detectados desde detalle_por_persona."""
    personas = metricas.get("detalle_por_persona") or []
    if isinstance(personas, dict):
        personas = personas.values()
    evs = []
    for persona in personas:
        tid = persona.get("id_persona")
        for e in persona.get("eventos", []):
            tipo = e.get("tipo", "")
            if tipo == ACCION_ADQUIRIDO:
                tipo_norm = "pick_up"
            elif tipo == ACCION_DEVOLVIENDO:
                tipo_norm = "put_back"
            else:
                continue
            evs.append({
                "frame": int(e.get("frame", 0)),
                "tipo": tipo_norm,
                "zona": e.get("zona") or None,
                "persona": tid,
            })
    return evs


def coinciden(det, gt, tol):
    mismo_tipo = det["tipo"] == gt["tipo"]
    mismo_frame = abs(det["frame"] - gt["frame"]) <= tol
    zona = gt.get("zona")
    mismo_zona = (not zona) or (det.get("zona") == zona)
    return mismo_tipo and mismo_frame and mismo_zona


def validar_gt(detectados, gt_eventos, tol):
    """Emparejamiento greedy 1:1 por vecino mas cercano (listas ordenadas).

    Se ordenan por frame para que cada evento GT se case con la deteccion mas
    proxima dentro de la ventana (y no con la primera por casualidad).
    Devuelve TP (pares gt-det), FP (detecciones sin casar) y FN (eventos GT
    sin casar), con su lista para poder desglosar por zona.
    """
    det_pend = sorted(detectados, key=lambda d: d["frame"])
    pend = list(det_pend)
    tp = []
    faltas = []
    for gt_ev in sorted(gt_eventos, key=lambda g: g["frame"]):
        mejor = None
        mejor_d = None
        for i, d in enumerate(pend):
            if not coinciden(d, gt_ev, tol):
                continue
            dist = abs(d["frame"] - gt_ev["frame"])
            if mejor is None or dist < mejor:
                mejor, mejor_d = dist, i
        if mejor is not None:
            tp.append((gt_ev, pend.pop(mejor_d)))
        else:
            faltas.append(gt_ev)
    fp = pend
    return tp, fp, len(faltas), faltas


def desglose_por_zona(tp, fp, faltas):
    """Resume TP/FP/FN por zona (la zona GT si existe; si no, la de la deteccion)."""
    zon = {}
    for gt, det in tp:
        z = gt.get("zona") or det.get("zona") or "(sin zona)"
        zc = zon.setdefault(z, {"tp": 0, "fp": 0, "fn": 0})
        zc["tp"] += 1
    for d in fp:
        z = d.get("zona") or "(sin zona)"
        zc = zon.setdefault(z, {"tp": 0, "fp": 0, "fn": 0})
        zc["fp"] += 1
    for g in faltas:
        z = g.get("zona") or "(sin zona)"
        zc = zon.setdefault(z, {"tp": 0, "fp": 0, "fn": 0})
        zc["fn"] += 1
    return zon


def metricas(tp, fp, fn):
    def _n(x):
        return len(x) if isinstance(x, (list, tuple)) else int(x)
    tp_n, fp_n, fn_n = _n(tp), _n(fp), _n(fn)
    precision = tp_n / (tp_n + fp_n) if (tp_n or fp_n) else 0.0
    recall = tp_n / (tp_n + fn_n) if (tp_n or fn_n) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def reportar(tp, fp, fn, tol, faltas=None):
    p, r, f1 = metricas(tp, fp, fn)
    print("=" * 62)
    print("VALIDACION EMBUDO vs GROUND TRUTH"
          f" (tolerancia +/-{tol} frames)")
    print("=" * 62)
    print(f"  Verdaderos positivos (acertados) : {len(tp)}")
    print(f"  Falsos positivos (detectados de mas): {len(fp)}")
    print(f"  Falsos negativos (no detectados)  : {fn}")
    print(f"  Precision  : {p:.2%}")
    print(f"  Recall     : {r:.2%}")
    print(f"  F1         : {f1:.2f}")

    por_zona = desglose_por_zona(tp, fp, faltas or [])
    if por_zona:
        print("-" * 62)
        print("  Desglose por zona:")
        print(f"  {'zona':<20}{'TP':>4}{'FP':>4}{'FN':>4}{'P':>8}{'R':>8}{'F1':>7}")
        for z in sorted(por_zona):
            c = por_zona[z]
            zp, zr, zf1 = metricas(c["tp"], c["fp"], c["fn"])
            print(f"  {z:<20}{c['tp']:>4}{c['fp']:>4}{c['fn']:>4}"
                  f"{zp:>7.0%}{zr:>8.0%}{zf1:>7.2f}")

    print("-" * 62)
    for gt, det in tp:
        d = abs(det["frame"] - gt["frame"])
        print(f"   OK  {gt['tipo']:<9} gt={gt['frame']:>4} det="
              f"{det['frame']:>4} (dist {d}) zona={gt.get('zona') or det.get('zona')}")
    for d in fp:
        print(f"   FP  {d['tipo']:<9} det={d['frame']:>4} zona={d.get('zona')} "
              f"persona={d.get('persona')}  << sin match en GT")
    return p, r, f1


def barrido_tol(detectados, gt_eventos, tols):
    """F1 alcanzable para varias tolerancias de frames (diagnostico del match)."""
    print("=" * 62)
    print("BARRIDO DE TOLERANCIA DE FRAMES")
    print("=" * 62)
    print(f"  {'tol':<6}{'TP':>5}{'FP':>5}{'FN':>5}{'P':>8}{'R':>8}{'F1':>7}")
    mejor = None
    for tol in tols:
        tp, fp, fn_n, _ = validar_gt(detectados, gt_eventos, tol)
        p, r, f1 = metricas(tp, fp, fn_n)
        print(f"  {tol:<6}{len(tp):>5}{len(fp):>5}{fn_n:>5}"
              f"{p:>7.0%}{r:>8.0%}{f1:>7.2f}")
        if (tp or fp or fn_n) and (mejor is None or f1 > mejor[1]):
            mejor = (tol, f1)
    if mejor:
        print(f"  -> Mejor F1 {mejor[1]:.2f} con tolerancia +/-{mejor[0]} frames.")
    return mejor


def chequeo_coherencia(metricas):
    """Aserciones de calidad sobre el JSON de metricas (sin ground truth)."""
    print("=" * 62)
    print("CHEQUEO DE COHERENCIA")
    print("=" * 62)
    ok = True

    analisis = metricas.get("analisis_zonas") or []

    for z in analisis:
        zid = z.get("id", "?")
        tasa = z.get("tasa_rechazo", 0) or 0
        pick = z.get("pick_ups", 0) or 0
        put = z.get("put_backs", 0) or 0
        visitas = z.get("visitas", 0) or 0

        if tasa > 1.01:
            print(f"  [FALLA] {zid}: tasa de rechazo {tasa:.2f} > 100%"
                  f" ({put} devoluciones / {pick} tomas).")
            ok = False
        elif put > pick:
            print(f"  [AVISO] {zid}: {put} put-backs > {pick} pick-ups "
                  f"(devolver sin tomar antes).")
        if pick > 0 and visitas == 0:
            print(f"  [FALLA] {zid}: {pick} pick-ups pero 0 visitas (imposible).")
            ok = False

    embudo = metricas.get("embudo_interaccion") or {}
    tot_pick = embudo.get("total_pick_ups", 0) or 0
    tot_put = embudo.get("total_put_backs", 0) or 0
    if tot_put > tot_pick:
        print(f"  [AVISO] embudo global: {tot_put} devoluciones > {tot_pick} tomas.")

    heat = metricas.get("heatmap_global") or []
    if heat and not any(any(float(v) > 0 for v in fila) for fila in heat):
        print("  [AVISO] heatmap_global completamente en cero.")

    if not analisis:
        print("  [FALLA] analisis_zonas vacio.")
        ok = False

    print("  Estado: " + ("OK (sin incoherencias detectadas)" if ok
                          else "SE DETECTARON INCOHERENCIAS"))
    return ok


def validar_metricas(metricas, ruta_gt=None, tol=FRAME_TOL_DEFECTO,
                     umbral_f1=None, sanity=True, hacer_barrido=False):
    """Ejecuta coherencia (+ opcional GT) y devuelve resumen.

    Reutilizable desde el pipeline: devuelve un dict con los resultados para
    poder tomar decisiones (p.ej. fallar el export si el F1 no alcanza un
    umbral) o solo informar.
    """
    resultado = {
        "sanity_ok": True,
        "hay_gt": bool(ruta_gt),
        "precision": None,
        "recall": None,
        "f1": None,
        "tp": 0, "fp": 0, "fn": 0,
        "por_zona": {},
        "umbral_f1": umbral_f1,
        "f1_ok": True,
    }

    if sanity:
        resultado["sanity_ok"] = chequeo_coherencia(metricas)
        print()

    if ruta_gt:
        ruta_gt = Path(ruta_gt)
        if not ruta_gt.exists():
            sys.exit(f"Ground truth no encontrado: {ruta_gt}")
        with open(ruta_gt, encoding="utf-8") as f:
            gt_data = json.load(f)

        # Aviso de zonas obsoletas en el GT (ids que ya no existen en config).
        ids_actuales = {z.get("id") for z in (metricas.get("analisis_zonas") or [])}
        for g in gt_data.get("eventos", []):
            zona = (g or {}).get("zona")
            if zona and ids_actuales and zona not in ids_actuales:
                print(f"  [AVISO] El GT usa la zona '{zona}', ausente en el "
                      f"JSON de metricas (ids actuales: {sorted(ids_actuales)}).")

        detectados = eventos_detectados(metricas)
        gt_eventos = gt_data.get("eventos", [])
        tp, fp, fn, faltas = validar_gt(detectados, gt_eventos, tol)
        p, r, f1 = reportar(tp, fp, fn, tol, faltas=faltas)
        if hacer_barrido:
            barrido_tol(detectados, gt_eventos,
                        list(range(2, 32, 3)))
        resultado.update(tp=len(tp), fp=len(fp), fn=fn,
                         precision=p, recall=r, f1=f1,
                         por_zona=desglose_por_zona(tp, fp, faltas))
        if umbral_f1 is not None:
            resultado["f1_ok"] = f1 >= umbral_f1
            print(f"  Umbral F1 exigido: {umbral_f1:.2f} -> "
                  f"{'CUMPLE' if resultado['f1_ok'] else 'NO CUMPLE'} "
                  f"(F1={f1:.2f})")
    else:
        print("\n(Sin --gt: solo coherencia. Genera el candidato con "
              "app.interfaces.generar_gt y re-ejecuta para F1.)")

    return resultado


def main():
    ap = argparse.ArgumentParser(description="Valida el embudo pick-up/put-back "
                                             "del pipeline YOLO.")
    ap.add_argument("--metricas", default=JSON_METRICAS,
                    help="JSON de metricas exportado por el pipeline.")
    ap.add_argument("--gt", default=None,
                    help="JSON de ground truth anotado (si se omite, solo "
                         "chequeo de coherencia).")
    ap.add_argument("--tol", type=int, default=FRAME_TOL_DEFECTO,
                    help=f"Ventana de frames para match (default {FRAME_TOL_DEFECTO}).")
    ap.add_argument("--no-sanity", action="store_true",
                    help="Omite el chequeo de coherencia.")
    ap.add_argument("--umbral-f1", type=float, default=None,
                    help="Falla (exit code 1) si el F1 queda bajo este umbral "
                         "(solo con --gt).")
    ap.add_argument("--barrido-tol", action="store_true",
                    help="Muestra el F1 para varias tolerancias de frames "
                         "(diagnostico del match).")
    args = ap.parse_args()

    ruta_m = Path(args.metricas)
    if not ruta_m.exists():
        sys.exit(f"Metricas no encontradas: {ruta_m}")
    with open(ruta_m, encoding="utf-8") as f:
        metricas = json.load(f)

    res = validar_metricas(metricas, ruta_gt=args.gt, tol=args.tol,
                           umbral_f1=args.umbral_f1, sanity=not args.no_sanity,
                           hacer_barrido=args.barrido_tol)

    if args.umbral_f1 is not None and not (res["f1_ok"] and res["sanity_ok"]):
        sys.exit("VALIDACION NO SUPERADA: F1 por debajo del umbral o "
                 "incoherencias de sanity.")


if __name__ == "__main__":
    main()