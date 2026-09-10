"""QA de privacidad y compliance (Ley 1581) - checks ejecutables.

Uso:  python scripts_qa/qa_privacidad.py [--salida outputs/metricas_retail.json]
Estado de salida: 0 si todo cumple, 1 si hay hallazgos.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config
from app.application import paths  # noqa: E402

PATRONES_PROHIBIDOS = [
    r"\bemotion(s)?\b",
    r"\bexpression(s)?\b",
    r"\bface_recognition\b",
    r"\bfacenet\b",
    r"\bdeepface\b",
    r"\binsightface\b",
    r"\bbiometric(s)?\b",
    r"\bembedding(s)?\b",
    r"\bsentiment\b",
    r"reconocimiento facial",
    r"analisis de emociones",
]

HALLAZGOS = []


def marcar(check, detalle):
    if detalle:
        HALLAZGOS.append((check, detalle))
    print("  [%s] %s%s" % ("FALLA" if detalle else "OK", check,
                           (" -> %s" % detalle) if detalle else ""))


def archivos_py(raiz):
    return [p for p in raiz.rglob("*.py") if "__pycache__" not in p.parts]


def banear_scan(texto):
    devueltos = []
    for pat in PATRONES_PROHIBIDOS:
        for m in re.finditer(pat, texto, re.IGNORECASE):
            devueltos.append((pat, m.group(0)))
    return devueltos


def main(salida_metricas):
    print("=== QA PRIVACIDAD / COMPLIANCE (Ley 1581) ===")

    import importlib
    anoni = importlib.import_module("app.infrastructure.anonimizacion")
    marcar("PRIV-01 anonimizacion importable",
           None if callable(anoni.anonimizar) else "anonimizar no es callable")

    tam = config.TAM_BLUR
    sigma = config.SIGMA_BLUR
    mal_blur = []
    if tam < 41:
        mal_blur.append("TAM_BLUR=%d < 41" % tam)
    if sigma < 20:
        mal_blur.append("SIGMA_BLUR=%d < 20" % sigma)
    marcar("PRIV-01 kernel de blur cubre el rostro (TAM=%d SIGMA=%d)"
           % (tam, sigma), " y ".join(mal_blur) or None)

    if not (0 < config.CONF_CABEZA_KP <= 1):
        marcar("PRIV-01 CONF_CABEZA_KP en rango", "valor=%r" % config.CONF_CABEZA_KP)
    else:
        marcar("PRIV-01 CONF_CABEZA_KP en rango", None)

    modelo_pose = Path(config.MODELO_POSE).name.lower()
    modelo_obj = Path(config.MODELO_OBJETOS).name.lower()
    facial = [n for n in (modelo_pose, modelo_obj) if "face" in n]
    marcar("PRIV-03 modelos cargados son pose+producto (no facial)",
           ("modelos faciales: %s" % facial) if facial else None)

    hallazgos = []
    for py in archivos_py(ROOT / "app"):
        for pat, m in banear_scan(py.read_text(encoding="utf-8", errors="replace")):
            hallazgos.append("%s :: %s (%s)" % (py.relative_to(ROOT), m, pat))
    marcar("PRIV-03/04 sin codigo de reconocimiento facial, emociones ni "
           "embeddings en app/", " ".join(sorted(set(hallazgos))) or None)

    prohibidos_sensibles = ["id_persona"]
    ruta_m = Path(salida_metricas)
    metricas_sensibles = []
    if ruta_m.exists():
        try:
            data = json.loads(ruta_m.read_text(encoding="utf-8"))
            text = json.dumps(data, ensure_ascii=False).lower()
            for clave in ("nombre", "cedula", "email", "telefono", "dni",
                          "embedding", "biometric", "rostro", "face"):
                if clave in text:
                    metricas_sensibles.append(clave)
        except json.JSONDecodeError:
            metricas_sensibles.append("JSON corrupto")
    marcar("PRIV-02 metricas sin datos personales/biometricos",
           ("claves encontradas: %s" % metricas_sensibles) if metricas_sensibles
           else None)

    artefactos = []
    for artefacto in (Path(paths.OUTPUTS)).rglob("*"):
        if artefacto.is_file():
            nombre = artefacto.name.lower()
            if any(t in nombre for t in ("face", "embed", "crop", "rostro",
                                         "biometr")):
                artefactos.append(str(artefacto.relative_to(ROOT)))
    marcar("PRIV-02 sin artefactos de rostros/embeddings en outputs/",
           " ".join(artefactos) or None)

    logs = []
    for log in ("analysis.log", "uvicorn.log", "uvicorn_err.log"):
        ruta_log = Path(paths.OUTPUTS) / log
        if ruta_log.exists():
            logs.append(ruta_log)
    hallazgos_log = []
    for ruta_log in logs:
        texto = ruta_log.read_text(encoding="utf-8", errors="replace")
        for pat, m in banear_scan(texto):
            hallazgos_log.append("%s (%s)" % (ruta_log.name, m))
    marcar("PRIV-02/05 logs sin datos sensibles",
           " ".join(sorted(set(hallazgos_log))) or None)

    print("-" * 56)
    if HALLAZGOS:
        print("RESULTADO: %d hallazgo(s) -> NO CUMPLE" % len(HALLAZGOS))
        return 1
    print("RESULTADO: CUMPLE (0 hallazgos)")
    return 0


if __name__ == "__main__":
    salida = sys.argv[sys.argv.index("--salida") + 1] \
        if "--salida" in sys.argv else paths.JSON_METRICAS
    sys.exit(main(salida))