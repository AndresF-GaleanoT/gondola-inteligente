// ============================================================================
// APPLICATION / api - caso de uso: obtener las metricas del dashboard.
// Aisla el fetch (adaptador) del resto de la presentacion.
// ============================================================================

import { mergeZones } from '../domain/zones';
import { buildAnalytics } from '../domain/analytics';

const TIMEOUT_MS = 15000;

// Fetch con timeout (AbortController). Devuelve {resp, cuerpo}; un 2xx sin
// cuerpo (p. ej. 202/204) devuelve cuerpo = {} en vez de reventar en json().
async function pedir(url, opciones = {}) {
  const { timeoutMs = TIMEOUT_MS, ...resto } = opciones;
  const controlador = new AbortController();
  const temporizador = setTimeout(() => controlador.abort(), timeoutMs);
  try {
    const resp = await fetch(url, { ...resto, signal: controlador.signal });
    const texto = await resp.text();
    let cuerpo = {};
    if (texto) {
      try {
        cuerpo = JSON.parse(texto);
      } catch {
        cuerpo = { _sin_formato: texto };
      }
    }
    return { resp, cuerpo };
  } finally {
    clearTimeout(temporizador);
  }
}

export async function cargarDatos() {
  let { resp, cuerpo } = await pedir('/api/datos');
  let origen = 'backend';

  if (resp.status === 404) {
    // El backend no tiene metricas todavia (no se ha analizado nada o no esta
    // activo): se muestran los datos de ejemplo y la UI lo anuncia. Cualquier
    // otro error (500, red, timeout) SI se propaga para no enmascararlo.
    ({ resp, cuerpo } = await pedir('/datos.json'));
    if (!resp.ok) throw new Error('Sin datos del backend ni ejemplo disponible.');
    origen = 'demo';
  } else if (!resp.ok) {
    throw new Error(`Error ${resp.status} al cargar los datos`);
  }

  return {
    origen,
    visitors: Number(cuerpo.total_personas_registradas) || 0,
    pickups: Number(cuerpo.embudo_interaccion?.total_pick_ups) || 0,
    zones: mergeZones(cuerpo.analisis_zonas),
    heatMatrix: cuerpo.heatmap_global?.length > 0 ? cuerpo.heatmap_global : [],
    analytics: buildAnalytics(cuerpo),
    recomendaciones: cuerpo.recomendaciones || null,
    generadoEn: cuerpo.generado_en || null,
    videoInfo: cuerpo.video || null,
    evidencias: (cuerpo.detalle_por_persona || []).flatMap((persona) =>
      (persona.eventos || [])
        .filter((evento) => evento.tipo === 'Producto Adquirido' || evento.tipo === 'Devolver el producto')
        .map((evento) => ({ ...evento, idPersona: persona.id_persona }))
    ).sort((a, b) => (Number(a.frame) || 0) - (Number(b.frame) || 0)),
  };
}

export async function obtenerEstado() {
  const { resp, cuerpo } = await pedir('/api/estado');
  if (!resp.ok) return null;
  return cuerpo;
}

export async function subirVideo(archivo) {
  const formData = new FormData();
  formData.append('archivo', archivo);
  const { resp, cuerpo } = await pedir('/api/video', {
    method: 'POST',
    body: formData,
    timeoutMs: 120000,
  });
  if (!resp.ok) {
    const detalle = cuerpo?.detail || cuerpo?.estado || `Error ${resp.status}`;
    throw new Error(detalle);
  }
  return cuerpo;
}

export async function analizarVideo() {
  const { resp, cuerpo } = await pedir('/api/analizar', {
    method: 'POST',
    timeoutMs: 20000,
  });
  if (!resp.ok) {
    const detalle = cuerpo?.detail || cuerpo?.mensaje || `Error ${resp.status}`;
    throw new Error(detalle);
  }
  return cuerpo;
}

export async function cargarZonas() {
  const { resp, cuerpo } = await pedir('/api/zonas');
  if (!resp.ok) throw new Error('No se pudieron cargar las zonas.');
  return cuerpo;
}

export async function guardarZonas(zonas) {
  const { resp, cuerpo } = await pedir('/api/zonas', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ zonas }),
  });
  if (!resp.ok) {
    throw new Error(cuerpo?.detail || `Error ${resp.status} al guardar zonas.`);
  }
  return cuerpo;
}

export async function restablecerZonas() {
  const { resp, cuerpo } = await pedir('/api/zonas/restablecer', {
    method: 'POST',
    timeoutMs: 20000,
  });
  if (!resp.ok) throw new Error('No se pudieron restablecer las zonas.');
  return cuerpo;
}
