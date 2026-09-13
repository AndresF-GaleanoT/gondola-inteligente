# USE CASES / exportar_metricas - vuelca las metricas a JSON para el dashboard.

import json
import time
from pathlib import Path

from ..application import paths
from ..config import (JSON_METRICAS, ZONAS, HEATMAP_EXPORT_CELDAS,
                      CLASIF_CALIENTE, CLASIF_FRIA,
                      ACCION_ADQUIRIDO, ACCION_DEVOLVIENDO,
                      VENTANA_DEDUPE_PICKUP)
from .. import config as cfg
from ..domain.agente import recomendar_zona, recomendar_planograma


def _deduplicar_eventos(eventos, claves_vistos):
    """Filtra pick-ups/put-backs duplicados: si otro evento del MISMO tipo en la
    MISMA zona cae dentro de VENTANA_DEDUPE_PICKUP se conserva solo el primero
    (el tracker puede dividir un evento real en varios IDs en el mismo instante).
    Devuelve los eventos que pasan el filtro y actualiza `claves_vistos`.
    """
    deduplicados = []
    for e in eventos:
        if e["tipo"] not in (ACCION_ADQUIRIDO, ACCION_DEVOLVIENDO):
            deduplicados.append(e)
            continue
        clave = (e["tipo"], e["zona"] or "?")
        ult = claves_vistos.get(clave)
        if ult is not None and e["frame"] - ult <= VENTANA_DEDUPE_PICKUP:
            continue
        claves_vistos[clave] = e["frame"]
        deduplicados.append(e)
    return deduplicados


def exportar_json_metricas(personas_estado, analizador, heatmap, fps):
    path_out = Path(JSON_METRICAS)
    path_out.parent.mkdir(parents=True, exist_ok=True)

    # --- Detalle por persona (con trayectoria de recorrido) ---------------
    data_export = []
    # Deduplicacion GLOBAL de pick-ups/put-backs: si dos personas registran el
    # mismo evento (misma zona en una ventana de frames) es el mismo evento real
    # dividido por el tracker; se conserva solo el primero. Asi el detalle por
    # persona y el conteo de zonas quedan coherentes.
    _vistos = {}
    for tid, datos in personas_estado.items():
        permanencia_seg = max(0, datos["fin_estante"] - datos["inicio_estante"]) / fps
        viendo_seg = datos["tiempo_viendo"] / fps

        eventos_seg = [
            {"tipo": e["tipo"], "frame": e["frame"],
             "segundo": round(e["frame"] / fps, 2),
             "zona": e["zona"]}
            for e in _deduplicar_eventos(datos["eventos"], _vistos)
        ]

        trayectoria = [
            {"segundo": round(fr / fps, 2),
             "x": x, "y": y,
             "x_norm": round(x / cfg.W_VIDEO, 4), "y_norm": round(y / cfg.H_VIDEO, 4)}
            for fr, x, y in datos["trayectoria"]
        ]

        zonas_visitadas = sorted({e["zona"] for e in datos["eventos"]
                                  if e["zona"]})

        data_export.append({
            "id_persona": tid,
            "permanencia_estante_seg": round(permanencia_seg, 2),
            "tiempo_viendo_seg": round(viendo_seg, 2),
            "interes_compra": datos["compro"],
            "alcance_estante": datos["alcance"],
            "producto_adquirido": datos["adquirido"],
            "devolucion_estante": datos["devolviendo"],
            "zonas_visitadas": zonas_visitadas,
            "eventos": eventos_seg,
            "trayectoria": trayectoria,
        })

    # --- Analisis por zona (caliente/fria) ---------------------------------
    analisis_zonas = analizador.resumen(fps)
    zonas_calientes = [z["id"] for z in analisis_zonas
                       if z["clasificacion"] == CLASIF_CALIENTE]
    zonas_frias = [z["id"] for z in analisis_zonas
                   if z["clasificacion"] == CLASIF_FRIA]

    # --- Heatmap global (grilla para dashboard) ----------------------------
    if heatmap is not None:
        try:
            grilla = heatmap.exportar_grilla(HEATMAP_EXPORT_CELDAS)
        except Exception:
            grilla = []
    else:
        grilla = []

    total_pick = sum(z["pick_ups"] for z in analisis_zonas)
    total_put = sum(z["put_backs"] for z in analisis_zonas)

    # Motor de recomendacion: 100% derivado de los datos observados (YOLO).
    recomendaciones = {
        "motor": "agente determinista (reglas sobre datos observados por YOLO)",
        "por_zona": {z["id"]: recomendar_zona(z) for z in analisis_zonas},
        "planograma": recomendar_planograma(analisis_zonas),
    }

    resumen_general = {
        "generado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "video": {"fps": fps, "ancho": cfg.W_VIDEO, "alto": cfg.H_VIDEO},
        "total_personas_registradas": len(personas_estado),
        "embudo_interaccion": {
            "total_pick_ups": total_pick,
            "total_put_backs": total_put,
            "tasa_rechazo_general": round(total_put / total_pick, 2) if total_pick else 0,
        },
        "zonas_configuradas": [z["id"] for z in ZONAS],
        "analisis_zonas": analisis_zonas,
        "zonas_calientes": zonas_calientes,
        "zonas_frias": zonas_frias,
        "heatmap_global": grilla,
        "detalle_por_persona": data_export,
        "recomendaciones": recomendaciones,
    }

    # Escritura atomica: la API nunca alcanza a leer un JSON a medio escribir.
    path_tmp = path_out.with_suffix(path_out.suffix + ".tmp")
    with open(path_tmp, "w", encoding="utf-8") as f:
        json.dump(resumen_general, f, indent=2, ensure_ascii=False)
    path_tmp.replace(path_out)

    print(f"\n[EXITO] Metricas exportadas en: {path_out}")
    print(f"   Zonas calientes: {zonas_calientes}")
    print(f"   Zonas frias:     {zonas_frias}")
    print(f"   Embudo: {total_pick} pick-ups / {total_put} put-backs "
          f"(rechazo {resumen_general['embudo_interaccion']['tasa_rechazo_general']})")
