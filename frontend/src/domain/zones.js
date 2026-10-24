// ============================================================================
// DOMAIN / zones - logica pura de zonas del dashboard (sin dependencias React)
// El mapeo zona->gondola/area vive en domain/layout.js (fuente unica); aqui se
// consume y se derivan los nombres visibles desde las gondolas del layout.
// ============================================================================

import { areaDeZona, LAYOUT_DEFAULT } from './layout.js';

// Nombre visible por id del pipeline, derivado del layout (gondolas[gondola].id).
export const ZONE_NAME_MAP = Object.fromEntries(
  LAYOUT_DEFAULT.zonaAGondola.map((z) => [
    z.zona,
    LAYOUT_DEFAULT.gondolas[z.gondola]?.id || z.area,
  ])
);

// Coercion numerica defensiva: el backend puede mandar strings; la UI nunca
// debe tocar .toFixed sobre un valor no numerico.
function num(valor) {
  const numerico = Number(valor);
  return Number.isFinite(numerico) ? numerico : 0;
}

export function mergeZones(analisis) {
  const lista = analisis || [];
  if (lista.length > 0) {
    // Datos reales del backend (YOLO). El nombre/layout mostrado se define AQUI
    // en la web (ZONE_NAME_MAP por id del pipeline) y no en el backend.
    return lista.map((raw, indice) => {
      const idRaw = raw.id || '';
      const { area } = areaDeZona(idRaw, LAYOUT_DEFAULT, indice);
      return {
        id: ZONE_NAME_MAP[idRaw] || idRaw || `Zona ${indice + 1}`,
        rawId: idRaw,
        area,
        classification: raw.clasificacion || 'fria',
        visits: num(raw.visitas),
        pick_ups: num(raw.pick_ups),
        put_backs: num(raw.put_backs),
        rejection_rate: num(raw.rejection_rate ?? raw.tasa_rechazo),
        dwell: num(raw.dwell_promedio_seg),
        presencia: num(raw.presencia),
      };
    });
  }
  // Sin datos: layout por defecto (las gondolas del plano, una por zona).
  return LAYOUT_DEFAULT.zonaAGondola.map((z) => ({
    id: LAYOUT_DEFAULT.gondolas[z.gondola]?.id || z.area,
    area: z.area,
    classification: 'fria',
    visits: 0,
    pick_ups: 0,
    put_backs: 0,
    rejection_rate: 0,
    dwell: 0,
    presencia: 0,
  }));
}

// Vista de zona para la UI. Devuelve el estado en TERCER nivel (caliente /
// templada / fria), que antes colapsaba 'templada' a "Fría".
const ETIQUETAS = {
  caliente: { etiqueta: 'Caliente', tono: 'hot' },
  templada: { etiqueta: 'Templada', tono: 'warm' },
  fria: { etiqueta: 'Fría', tono: 'cold' },
};

export function zoneView(zone) {
  const clasif = zone.classification || 'fria';
  const { etiqueta, tono } = ETIQUETAS[clasif] || ETIQUETAS.fria;
  return {
    title: zone.id,
    clasif,
    tono,
    etiqueta,
    isHot: clasif === 'caliente',
    visits: zone.visits,
    pickups: zone.pick_ups,
    rejection: `${capPct(zone.rejection_rate * 100)}%`,
  };
}

// Una "tasa" mostrada como % nunca debe pasar de 100 (una persona puede tomar
// varios productos, pero el embudo habla de la proporcion de ese grupo objetivo).
// El campo se interpreta como CONSIDERACION: tomas devueltas / total tomas
// (tocar y devolver = el producto atrajo la mano aunque no cerrara la compra).
function capPct(valor) {
  return Math.min(100, Math.max(0, Math.round(valor)));
}

export function calcInteractionRate(visitors, pickups) {
  return visitors > 0 ? capPct((pickups / visitors) * 100) : 0;
}

export function calcRejectionRate(zoneData) {
  if (!zoneData.length) return 0;
  const totalPickups = zoneData.reduce((acum, zona) => acum + num(zona.pick_ups), 0);
  const totalPutbacks = zoneData.reduce((acum, zona) => acum + num(zona.put_backs), 0);
  return totalPickups > 0 ? capPct((totalPutbacks / totalPickups) * 100) : 0;
}
