// ============================================================================
// PRESENTATION / ZoneOverlay - muestra EN VIVO los poligonos de las zonas
// vigentes (GET /api/zonas) superpuestos al video/fotogramas anotados de
// "Escena analizada". Se ajusta a la resolucion nativa del material de video
// (medida con el primer frame anotado) y escala las coordenadas 1280x720.
// ============================================================================

import { useState } from 'react';

const COLORES_ZONA = ['#2bff88', '#ffb000', '#ff4545'];

export default function ZoneOverlay({
  zonas,
  referencia,
  frameUrl,
  src,
  tipo,
}) {
  const [dimensiones, setDimensiones] = useState(null);

  const [anchoRef, altoRef] = referencia || [1280, 720];
  const escalaX = dimensiones ? dimensiones.w / anchoRef : 1;
  const escalaY = dimensiones ? dimensiones.h / altoRef : 1;

  const puntosSvg = (lista) =>
    lista
      .map((p) => [p[0] * escalaX, p[1] * escalaY].map((c) => c.toFixed(1)).join(','))
      .join(' ');

  const posicionEtiqueta = (p) => [p[0] * escalaX + 14, p[1] * escalaY + 20];

  return (
    <div
      className="zone-overlay"
      style={{ aspectRatio: dimensiones ? `${dimensiones.w} / ${dimensiones.h}` : '16 / 9' }}
    >
      <img
        className="zone-dims-io"
        src={frameUrl}
        alt=""
        aria-hidden="true"
        onLoad={(evento) => {
          const imagen = evento.currentTarget;
          if (imagen.naturalWidth > 0) {
            setDimensiones({ w: imagen.naturalWidth, h: imagen.naturalHeight });
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
      {zonas && dimensiones && (
        <svg viewBox={`0 0 ${dimensiones.w} ${dimensiones.h}`} preserveAspectRatio="xMidYMid meet">
          {zonas.map((zona, indice) => (
            <g key={zona.id} stroke={COLORES_ZONA[indice]}>
              <polygon
                points={puntosSvg(zona.poligono)}
                fill="none"
                strokeWidth={Math.max(2, dimensiones.w * 0.0025)}
              />
              <polygon
                points={puntosSvg(zona.agarro)}
                fill="none"
                strokeWidth={Math.max(1.5, dimensiones.w * 0.0015)}
                strokeDasharray={Math.max(5, dimensiones.w * 0.006)}
              />
              <text x={posicionEtiqueta(zona.poligono[0])[0]} y={posicionEtiqueta(zona.poligono[0])[1]}>
                {zona.id}
              </text>
            </g>
          ))}
        </svg>
      )}
    </div>
  );
}