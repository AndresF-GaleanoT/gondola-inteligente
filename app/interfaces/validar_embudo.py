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
    eventos_normalizados = []
    for persona in personas:
        tid = persona.get("id_persona")
        for evento in persona.get("eventos", []):
            tipo = evento.get("tipo", "")
            if tipo == ACCION_ADQUIRIDO:
                tipo_norm = "pick_up"
            elif tipo == ACCION_DEVOLVIENDO:
                tipo_norm = "put_back"
            else:
                continue
            eventos_normalizados.append({
                "frame": int(evento.get("frame", 0)),
                "tipo": tipo_norm,
                "zona": evento.get("zona") or None,
                "persona": tid,
            })
    return eventos_normalizados


def coinciden(detectado, gt, tol):
    mismo_tipo = detectado["tipo"] == gt["tipo"]
    mismo_frame = abs(detectado["frame"] - gt["frame"]) <= tol
    zona_gt = gt.get("zona")
    misma_zona = (not zona_gt) or (detectado.get("zona") == zona_gt)
    return mismo_tipo and mismo_frame and misma_zona


def validar_gt(detectados, gt_eventos, tol):
    """Emparejamiento greedy 1:1 por vecino mas cercano (listas ordenadas).

    Se ordenan por frame para que cada evento GT se case con la deteccion mas
    proxima dentro de la ventana (y no con la primera por casualidad).
    Devuelve TP (pares gt-det), FP (detecciones sin casar) y FN (eventos GT
    sin casar), con su lista para poder desglosar por zona.
    """
    pendientes = sorted(detectados, key=lambda d: d["frame"])
    verdaderos_positivos = []
    sin_match = []
    for evento_gt in sorted(gt_eventos, key=lambda g: g["frame"]):
        mejor_distancia = None
        mejor_indice = None
        for indice, candidato in enumerate(pendientes):
            if not coinciden(candidato, evento_gt, tol):
                continue
            distancia = abs(candidato["frame"] - evento_gt["frame"])
            if mejor_distancia is None or distancia < mejor_distancia:
                mejor_distancia, mejor_indice = distancia, indice
        if mejor_distancia is not None:
            verdaderos_positivos.append((evento_gt, pendientes.pop(mejor_indice)))
        else:
            sin_match.append(evento_gt)
    falsos_positivos = pendientes
    return verdaderos_positivos, falsos_positivos, len(sin_match), sin_match


def desglose_por_zona(tp, fp, faltas):
    """Resume TP/FP/FN por zona (la zona GT si existe; si no, la de la deteccion)."""
    por_zona = {}
    for evento_gt, detectado in tp:
        zona = evento_gt.get("zona") or detectado.get("zona") or "(sin zona)"
        contador = por_zona.setdefault(zona, {"tp": 0, "fp": 0, "fn": 0})
        contador["tp"] += 1
    for detectado in fp:
        zona = detectado.get("zona") or "(sin zona)"
        contador = por_zona.setdefault(zona, {"tp": 0, "fp": 0, "fn": 0})
        contador["fp"] += 1
    for evento_gt in faltas:
        zona = evento_gt.get("zona") or "(sin zona)"
        contador = por_zona.setdefault(zona, {"tp": 0, "fp": 0, "fn": 0})
        contador["fn"] += 1
    return por_zona


def metricas(tp, fp, fn):
    def _cantidad(valor):
        return len(valor) if isinstance(valor, (list, tuple)) else int(valor)
    n_tp, n_fp, n_fn = _cantidad(tp), _cantidad(fp), _cantidad(fn)
    precision = n_tp / (n_tp + n_fp) if (n_tp or n_fp) else 0.0
    recall = n_tp / (n_tp + n_fn) if (n_tp or n_fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def reportar(tp, fp, fn, tol, faltas=None):
    precision, recall, f1 = metricas(tp, fp, fn)
    print("=" * 62)
    print("VALIDACION EMBUDO vs GROUND TRUTH"
          f" (tolerancia +/-{tol} frames)")
    print("=" * 62)
    print(f"  Verdaderos positivos (acertados) : {len(tp)}")
    print(f"  Falsos positivos (detectados de mas): {len(fp)}")
    print(f"  Falsos negativos (no detectados)  : {fn}")
    print(f"  Precision  : {precision:.2%}")
    print(f"  Recall     : {recall:.2%}")
    print(f"  F1         : {f1:.2f}")

    por_zona = desglose_por_zona(tp, fp, faltas or [])
    if por_zona:
        print("-" * 62)
        print("  Desglose por zona:")
        print(f"  {'zona':<20}{'TP':>4}{'FP':>4}{'FN':>4}{'P':>8}{'R':>8}{'F1':>7}")
        for zona in sorted(por_zona):
            contador = por_zona[zona]
            zp, zr, zf1 = metricas(contador["tp"], contador["fp"], contador["fn"])
            print(f"  {zona:<20}{contador['tp']:>4}{contador['fp']:>4}{contador['fn']:>4}"
                  f"{zp:>7.0%}{zr:>8.0%}{zf1:>7.2f}")

    print("-" * 62)
    for evento_gt, detectado in tp:
        distancia = abs(detectado["frame"] - evento_gt["frame"])
        print(f"   OK  {evento_gt['tipo']:<9} gt={evento_gt['frame']:>4} det="
              f"{detectado['frame']:>4} (dist {distancia}) zona={evento_gt.get('zona') or detectado.get('zona')}")
    for detectado in fp:
        print(f"   FP  {detectado['tipo']:<9} det={detectado['frame']:>4} zona={detectado.get('zona')} "
              f"persona={detectado.get('persona')}  << sin match en GT")
    return precision, recall, f1


def barrido_tol(detectados, gt_eventos, tols):
    """F1 alcanzable para varias tolerancias de frames (diagnostico del match)."""
    print("=" * 62)
    print("BARRIDO DE TOLERANCIA DE FRAMES")
    print("=" * 62)
    print(f"  {'tol':<6}{'TP':>5}{'FP':>5}{'FN':>5}{'P':>8}{'R':>8}{'F1':>7}")
    mejor = None
    for tol in tols:
        tp, fp, n_fn, _ = validar_gt(detectados, gt_eventos, tol)
        precision, recall, f1 = metricas(tp, fp, n_fn)
        print(f"  {tol:<6}{len(tp):>5}{len(fp):>5}{n_fn:>5}"
              f"{precision:>7.0%}{recall:>8.0%}{f1:>7.2f}")
        if (tp or fp or n_fn) and (mejor is None or f1 > mejor[1]):
            mejor = (tol, f1)
    if mejor:
        print(f"  -> Mejor F1 {mejor[1]:.2f} con tolerancia +/-{mejor[0]} frames.")
    return mejor


def chequeo_coherencia(metricas):
    """Aserciones de calidad sobre el JSON de metricas (sin ground truth)."""
    print("=" * 62)
    print("CHEQUEO DE COHERENCIA")
    print("=" * 62)
    todo_ok = True

    analisis = metricas.get("analisis_zonas") or []

    for zona in analisis:
        zid = zona.get("id", "?")
        tasa = zona.get("tasa_rechazo", 0) or 0
        pick = zona.get("pick_ups", 0) or 0
        put = zona.get("put_backs", 0) or 0
        visitas = zona.get("visitas", 0) or 0

        if tasa > 1.01:
            print(f"  [FALLA] {zid}: tasa de rechazo {tasa:.2f} > 100%"
                  f" ({put} devoluciones / {pick} tomas).")
            todo_ok = False
        elif put > pick:
            print(f"  [AVISO] {zid}: {put} put-backs > {pick} pick-ups "
                  f"(devolver sin tomar antes).")
        if pick > 0 and visitas == 0:
            print(f"  [FALLA] {zid}: {pick} pick-ups pero 0 visitas (imposible).")
            todo_ok = False

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
        todo_ok = False

    print("  Estado: " + ("OK (sin incoherencias detectadas)" if todo_ok
                          else "SE DETECTARON INCOHERENCIAS"))
    return todo_ok


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
        with open(ruta_gt, encoding="utf-8") as archivo:
            gt_data = json.load(archivo)

        # Aviso de zonas obsoletas en el GT (ids que ya no existen en config).
        ids_actuales = {zona.get("id") for zona in (metricas.get("analisis_zonas") or [])}
        for evento_gt in gt_data.get("eventos", []):
            zona = (evento_gt or {}).get("zona")
            if zona and ids_actuales and zona not in ids_actuales:
                print(f"  [AVISO] El GT usa la zona '{zona}', ausente en el "
                      f"JSON de metricas (ids actuales: {sorted(ids_actuales)}).")

        detectados = eventos_detectados(metricas)
        gt_eventos = gt_data.get("eventos", [])
        tp, fp, fn, faltas = validar_gt(detectados, gt_eventos, tol)
        precision, recall, f1 = reportar(tp, fp, fn, tol, faltas=faltas)
        if hacer_barrido:
            barrido_tol(detectados, gt_eventos,
                        list(range(2, 32, 3)))
        resultado.update(tp=len(tp), fp=len(fp), fn=fn,
                         precision=precision, recall=recall, f1=f1,
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

    ruta_metricas = Path(args.metricas)
    if not ruta_metricas.exists():
        sys.exit(f"Metricas no encontradas: {ruta_metricas}")
    with open(ruta_metricas, encoding="utf-8") as archivo:
        metricas_cargadas = json.load(archivo)

    resultado = validar_metricas(metricas_cargadas, ruta_gt=args.gt, tol=args.tol,
                           umbral_f1=args.umbral_f1, sanity=not args.no_sanity,
                           hacer_barrido=args.barrido_tol)

    if args.umbral_f1 is not None and not (resultado["f1_ok"] and resultado["sanity_ok"]):
        sys.exit("VALIDACION NO SUPERADA: F1 por debajo del umbral o "
                 "incoherencias de sanity.")


if __name__ == "__main__":
    main()
