// APPLICATION / api
// Comunicación del frontend con el backend de Góndola Inteligente.

import { mergeZones } from '../domain/zones';
import { buildAnalytics } from '../domain/analytics';

const TIMEOUT_MS = 15000;

// Realiza una petición con tiempo máximo de espera.
async function pedir(url, opciones = {}) {
  const { timeoutMs = TIMEOUT_MS, ...resto } = opciones;
  const controlador = new AbortController();

  const temporizador = setTimeout(
    () => controlador.abort(),
    timeoutMs
  );

  try {
    const resp = await fetch(url, {
      ...resto,
      signal: controlador.signal,
    });

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

// Obtiene y transforma las métricas para el dashboard.
export async function cargarDatos() {
  let { resp, cuerpo } = await pedir('/api/datos');
  let origen = 'backend';

  if (resp.status === 404) {
    ({ resp, cuerpo } = await pedir('/datos.json'));

    if (!resp.ok) {
      throw new Error('Sin datos del backend ni ejemplo disponible.');
    }

    origen = 'demo';
  } else if (!resp.ok) {
    throw new Error(`Error ${resp.status} al cargar los datos.`);
  }

  return {
    origen,
    visitors: Number(cuerpo.total_personas_registradas) || 0,
    pickups: Number(cuerpo.embudo_interaccion?.total_pick_ups) || 0,
    zones: mergeZones(cuerpo.analisis_zonas),

    heatMatrix: cuerpo.heatmap_global?.length > 0
      ? cuerpo.heatmap_global
      : [],

    analytics: buildAnalytics(cuerpo),
    recomendaciones: cuerpo.recomendaciones || null,
    generadoEn: cuerpo.generado_en || null,
    videoInfo: cuerpo.video || null,

    evidencias: (cuerpo.detalle_por_persona || [])
      .flatMap((persona) =>
        (persona.eventos || [])
          .filter(
            (evento) =>
              evento.tipo === 'Producto Adquirido' ||
              evento.tipo === 'Devolver el producto'
          )
          .map((evento) => ({
            ...evento,
            idPersona: persona.id_persona,
          }))
      )
      .sort(
        (a, b) =>
          (Number(a.frame) || 0) - (Number(b.frame) || 0)
      ),
  };
}

// Consulta el progreso del análisis.
export async function obtenerEstado() {
  const { resp, cuerpo } = await pedir('/api/estado');

  if (!resp.ok) {
    throw new Error(
      cuerpo?.detail ||
      `Error ${resp.status} al consultar el estado del análisis.`
    );
  }

  return cuerpo;
}

// Sube el video e inicia el análisis usando las zonas guardadas.
export async function subirVideo(archivo) {
  const formData = new FormData();
  formData.append('archivo', archivo);

  const { resp, cuerpo } = await pedir('/api/video', {
    method: 'POST',
    body: formData,
    timeoutMs: 120000,
  });

  if (!resp.ok) {
    throw new Error(
      cuerpo?.detail ||
      cuerpo?.estado ||
      `Error ${resp.status} al subir el video.`
    );
  }

  // Backend actual: la carga prepara el video.
  // Una segunda petición inicia el procesamiento YOLO.
  if (cuerpo.estado === 'listo_para_analizar') {
    const inicio = await pedir('/api/analizar', {
      method: 'POST',
    });

    if (!inicio.resp.ok) {
      throw new Error(
        inicio.cuerpo?.detail ||
        inicio.cuerpo?.estado ||
        `Error ${inicio.resp.status} al iniciar el análisis.`
      );
    }

    if (inicio.cuerpo.estado !== 'iniciado') {
      throw new Error(
        'El backend no confirmó el inicio del análisis.'
      );
    }

    return inicio.cuerpo;
  }

  // Compatibilidad con el backend anterior:
  // la subida ya iniciaba el procesamiento automáticamente.
  if (cuerpo.estado === 'iniciado') {
    return cuerpo;
  }

  throw new Error(
    'El video se cargó, pero no se confirmó el inicio del análisis.'
  );
}