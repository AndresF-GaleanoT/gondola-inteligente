// ============================================================================
// PRESENTATION / ZoneEditor - editor visual de poligonos de zonas.
// Carga /api/zonas (coordenadas del frame de referencia 1280x720), las dibuja
// sobre el frame real del video (escalando a su resolucion natural) y permite
// arrastrar los 8 vertices de cada zona (poligono + agarro). Guarda con PUT
// /api/zonas (tambien restablece las de fabrica).
// ============================================================================

import { useEffect, useRef, useState } from 'react';
import {
  cargarZonas,
  guardarZonas,
  restablecerZonas,
} from '../application/api';

const COLORES = ['#d9ed55', '#8ab4ff', '#ff8f6b'];

const orientacion = (a, b, c) =>
  (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);

const segmentosCruzan = (p1, p2, p3, p4) => {
  const d1 = orientacion(p3, p4, p1);
  const d2 = orientacion(p3, p4, p2);
  const d3 = orientacion(p1, p2, p3);
  const d4 = orientacion(p1, p2, p4);
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) &&
    ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
};

const poligonoValido = (pts) => {
  const n = pts.length;
  for (let i = 0; i < n; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % n];
    for (let j = i + 1; j < n; j++) {
      const c = pts[j];
      const d = pts[(j + 1) % n];
      if ((c[0] === a[0] && c[1] === a[1]) ||
          (c[0] === b[0] && c[1] === b[1]) ||
          (d[0] === a[0] && d[1] === a[1]) ||
          (d[0] === b[0] && d[1] === b[1])) continue;
      if (segmentosCruzan(a, b, c, d)) return false;
    }
  }
  let area = 0;
  for (let i = 0; i < n; i++) {
    area += pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1];
  }
  return Math.abs(area) > 0;
};

export default function ZoneEditor({ frameUrl, onClose, onGuardado, onCambio }) {
  const [zonas, setZonas] = useState(null);
  const [fuente, setFuente] = useState('default');
  const [referencia, setReferencia] = useState([1280, 720]);
  const [imgDims, setImgDims] = useState({ w: 1280, h: 720 });
  const [arrastre, setArrastre] = useState(null);
  const [error, setError] = useState('');
  const [guardando, setGuardando] = useState(false);
  const contenedorRef = useRef(null);
  const imagenRef = useRef(null);

  const [refW, refH] = referencia;
  const fx = imgDims.w / refW;
  const fy = imgDims.h / refH;

  useEffect(() => {
    let activo = true;
    cargarZonas()
      .then((info) => {
        if (!activo) return;
        setZonas(info.zonas);
        setFuente(info.fuente);
        setReferencia(info.referencia || [1280, 720]);
      })
      .catch((e) => setError(e.message));
    return () => { activo = false; };
  }, []);

  const aImg = (p) => [p[0] * fx, p[1] * fy];

  const aRef = (x, y) => [
    Math.round(Math.min(refW, Math.max(0, x / fx))),
    Math.round(Math.min(refH, Math.max(0, y / fy))),
  ];

  const desdePuntero = (e) => {
    const rect = contenedorRef.current.getBoundingClientRect();
    return {
      x: ((e.clientX - rect.left) / rect.width) * imgDims.w,
      y: ((e.clientY - rect.top) / rect.height) * imgDims.h,
    };
  };

  const cercano = (px, py) => {
    if (!zonas) return null;
    const radio = Math.max(16, imgDims.w * 0.02);
    let mejor = null;
    let dmin = Infinity;
    for (let i = 0; i < zonas.length; i++) {
      for (const clave of ['poligono', 'agarro']) {
        zonas[i][clave].forEach((p, v) => {
          const [x, y] = aImg(p);
          const d = Math.hypot(x - px, y - py);
          if (d < dmin) {
            dmin = d;
            mejor = { zona: i, clave, vertice: v };
          }
        });
      }
    }
    return dmin <= radio ? mejor : null;
  };

  const onPointerDown = (e) => {
    if (!zonas) return;
    const { x, y } = desdePuntero(e);
    const objetivo = cercano(x, y);
    if (objetivo) {
      e.currentTarget.setPointerCapture(e.pointerId);
      e.preventDefault();
      setArrastre(objetivo);
    }
  };

  const onPointerMove = (e) => {
    if (!arrastre) return;
    const { x, y } = desdePuntero(e);
    const refEscala = aRef(x, y);
    setZonas((zs) => {
      const copia = zs.map((z) => ({
        ...z,
        poligono: z.poligono.map((p) => [...p]),
        agarro: z.agarro.map((p) => [...p]),
      }));
      copia[arrastre.zona][arrastre.clave][arrastre.vertice] = refEscala;
      return copia;
    });
  };

  const onPointerUp = () => setArrastre(null);

  const invalidos = zonas
    ? zonas
        .map((z, i) => (poligonoValido(z.poligono) && poligonoValido(z.agarro)
          ? -1 : i))
        .filter((i) => i >= 0)
    : [];

  const hayInvalidos = invalidos.length > 0;

  const guardar = async () => {
    if (hayInvalidos) {
      setError('Un polígono se auto-cruza o quedó sin área: ajustá sus '
        + 'vértices antes de guardar.');
      return;
    }
    try {
      setError('');
      setGuardando(true);
      const r = await guardarZonas(zonas);
      setZonas(r.zonas);
      setFuente(r.fuente);
      onGuardado(
        r.reanalizando
          ? 'Zonas guardadas. Reiniciando el análisis con las nuevas zonas…'
          : 'Zonas guardadas.',
        r
      );
      onCambio?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setGuardando(false);
    }
  };

  const restablecer = async () => {
    try {
      setError('');
      setGuardando(true);
      const r = await restablecerZonas();
      setZonas(r.zonas);
      setFuente(r.fuente);
      onGuardado(
        r.reanalizando
          ? 'Zonas restablecidas. Reiniciando el análisis…'
          : 'Zonas restablecidas a los valores de fábrica.',
        r
      );
      onCambio?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setGuardando(false);
    }
  };

  const pts = (lista) =>
    lista.map((p) => aImg(p).map((c) => c.toFixed(1)).join(',')).join(' ');

  const radio = Math.max(6, imgDims.w * 0.007);

  return (
    <div className="zone-editor">
      <div className="zone-editor-tools">
        <span>
          Editar zonas · marco de referencia {refW}×{refH} px
        </span>
        <span className={`zone-origen ${fuente}`}>
          {fuente === 'runtime' ? 'Configuración personalizada' : 'De fábrica'}
        </span>
        <div className="zone-editor-actions">
          <button type="button" onClick={restablecer} disabled={guardando}>
            Restablecer
          </button>
          <button type="button" onClick={onClose} disabled={guardando}>
            Cancelar
          </button>
          <button
            type="button"
            className="guardar"
            onClick={guardar}
            disabled={guardando || !zonas || hayInvalidos}
            title={hayInvalidos ? 'Ajustá los vértices: hay un polígono inválido' : undefined}
          >
            {guardando ? 'Guardando…' : (hayInvalidos ? 'Polígono inválido' : 'Guardar zonas')}
          </button>
        </div>
      </div>

      <div
        className="zone-canvas"
        ref={contenedorRef}
        style={{ aspectRatio: `${imgDims.w} / ${imgDims.h}` }}
      >
        <img
          ref={imagenRef}
          src={frameUrl}
          alt="Frame de referencia para editar las zonas"
          onLoad={() => {
            const el = imagenRef.current;
            if (el && el.naturalWidth > 0) {
              setImgDims({ w: el.naturalWidth, h: el.naturalHeight });
            }
          }}
        />
        <svg
          viewBox={`0 0 ${imgDims.w} ${imgDims.h}`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          {zonas?.map((z, i) => (
            <g key={z.id} fill={COLORES[i]}>
              <polygon
                className={`zone-fill${invalidos.includes(i) ? ' invalido' : ''}`}
                stroke={COLORES[i]}
                points={pts(z.poligono)}
              />
              <polygon
                className={`zone-agarro${invalidos.includes(i) ? ' invalido' : ''}`}
                stroke={COLORES[i]}
                points={pts(z.agarro)}
              />
              {z.poligono.map((p, v) => {
                const [x, y] = aImg(p);
                return (
                  <circle
                    key={`${z.id}-p-${v}`}
                    cx={x}
                    cy={y}
                    r={radio}
                  />
                );
              })}
              {z.agarro.map((p, v) => {
                const [x, y] = aImg(p);
                return (
                  <circle
                    key={`${z.id}-a-${v}`}
                    cx={x}
                    cy={y}
                    r={radio}
                  />
                );
              })}
              <text x={aImg(z.poligono[0])[0] + 14} y={aImg(z.poligono[0])[1] + 22}>
                {z.id}
              </text>
            </g>
          ))}
        </svg>
        <div className="zone-hint">
          Arrastrá los puntos para ajustar los polígonos. Blanco = cuerpo ·
          punteado = agarro (mano)
        </div>
        {hayInvalidos && (
          <div className="zone-error">
            Un polígono se auto-cruza o quedó sin área: ajustá sus vértices
            antes de guardar.
          </div>
        )}
        {error && !hayInvalidos && <div className="zone-error">{error}</div>}
      </div>
    </div>
  );
}