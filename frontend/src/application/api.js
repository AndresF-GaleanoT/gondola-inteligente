// APPLICATION / api
// Comunicación del frontend con el backend de RetailVision Edge AI.

import { mergeZones } from '../domain/zones';
import { buildAnalytics } from '../domain/analytics';

const TIMEOUT_MS = 15000;

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
  const { resp, cuerpo } = await pedir('/api/datos');

  if (resp.status === 404) {
    return {
      origen: 'vacio',
      visitors: 0,
      pickups: 0,
      zones: mergeZones(undefined),
      heatMatrix: [],
      analytics: buildAnalytics({}),
      recomendaciones: null,
      generadoEn: null,
      videoInfo: null,
      evidencias: [],
    };
  }
  if (!resp.ok) {
    throw new Error(`Error ${resp.status} al cargar los datos.`);
  }

  return {
    origen: 'backend',
    visitors: Number(cuerpo.total_personas_registradas) || 0,
    pickups: Number(cuerpo.embudo_interaccion?.total_pick_ups) || 0,
    zones: mergeZones(cuerpo.analisis_zonas),
    heatMatrix: cuerpo.heatmap_global?.length > 0 ? cuerpo.heatmap_global : [],
    analytics: buildAnalytics(cuerpo),
    recomendaciones: cuerpo.recomendaciones || null,
    generadoEn: cuerpo.generado_en || null,
    videoInfo: cuerpo.video || null,
    evidencias: (cuerpo.detalle_por_persona || [])
      .flatMap((persona) =>
        (persona.eventos || [])
          .filter((evento) => evento.tipo === 'Producto Adquirido' || evento.tipo === 'Devolver el producto')
          .map((evento) => ({ ...evento, idPersona: persona.id_persona }))
      )
      .sort((a, b) => (Number(a.frame) || 0) - (Number(b.frame) || 0)),
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

export async function reiniciarMetricas() {
  const { resp, cuerpo } = await pedir('/api/reiniciar', {
    method: 'POST',
    timeoutMs: 20000,
  });
  if (!resp.ok) {
    const detalle = cuerpo?.detail || cuerpo?.mensaje || `Error ${resp.status} al reiniciar.`;
    throw new Error(detalle);
  }
  return cuerpo;
}
