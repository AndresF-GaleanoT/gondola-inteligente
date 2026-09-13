// ============================================================================
// PRESENTATION / ZoneOverlay - muestra EN VIVO los poligonos de las zonas
// vigentes (GET /api/zonas) superpuestos al video/fotogramas anotados de
// "Escena analizada". Se ajusta a la resolucion nativa del material de video
// (medida con el primer frame anotado) y escala las coordenadas 1280x720.
// ============================================================================

import { useState } from 'react';

const COLORES = ['#d9ed55', '#8ab4ff', '#ff8f6b'];

export default function ZoneOverlay({
  zonas,
  referencia,
  frameUrl,
  src,
  tipo,
}) {
  const [dims, setDims] = useState(null);

  const [refW, refH] = referencia || [1280, 720];
  const fx = dims ? dims.w / refW : 1;
  const fy = dims ? dims.h / refH : 1;

  const pts = (lista) =>
    lista
      .map((p) => [p[0] * fx, p[1] * fy].map((c) => c.toFixed(1)).join(','))
      .join(' ');

  const etiqueta = (p) => [p[0] * fx + 14, p[1] * fy + 20];

  return (
    <div
      className="zone-overlay"
      style={{ aspectRatio: dims ? `${dims.w} / ${dims.h}` : '16 / 9' }}
    >
      <img
        className="zone-dims-io"
        src={frameUrl}
        alt=""
        aria-hidden="true"
        onLoad={(e) => {
          const el = e.currentTarget;
          if (el.naturalWidth > 0) {
            setDims({ w: el.naturalWidth, h: el.naturalHeight });
          }
        }}
      />
      {tipo === 'video' ? (
        <video
          className="zone-media"
          src={src}
          autoPlay
          muted
          loop
          playsInline
          controls
        />
      ) : (
        <img className="zone-media" src={src} alt="Visión de las góndolas" />
      )}
      {zonas && dims && (
        <svg viewBox={`0 0 ${dims.w} ${dims.h}`} preserveAspectRatio="xMidYMid meet">
          {zonas.map((z, i) => (
            <g key={z.id} stroke={COLORES[i]}>
              <polygon
                points={pts(z.poligono)}
                fill="none"
                strokeWidth={Math.max(2, dims.w * 0.0025)}
              />
              <polygon
                points={pts(z.agarro)}
                fill="none"
                strokeWidth={Math.max(1.5, dims.w * 0.0015)}
                strokeDasharray={Math.max(5, dims.w * 0.006)}
              />
              <text x={etiqueta(z.poligono[0])[0]} y={etiqueta(z.poligono[0])[1]}>
                {z.id}
              </text>
            </g>
          ))}
        </svg>
      )}
    </div>
  );
}