// ============================================================================
// DOMAIN / agente - agente determinista de "Analisis de zonas".
// Razonamiento sobre las metricas que entrega el pipeline YOLO (visitas,
// pick-ups, put-backs, rechazo, dwell, presencia y clasificacion).
// Sin LLM: 100% local, offline y con privacidad por diseño (solo numeros).
// ============================================================================

function pct(v) {
  return Math.min(100, Math.max(0, Math.round((v || 0) * 100)));
}

// Diagnostico + accion accionable por zona, derivados de los datos del modelo.
export function analizarZona(zona = {}) {
  const nombre = zona.id || 'la zona';
  const visitas = zona.visits || 0;
  const pick = zona.pick_ups || 0;
  const devol = zona.put_backs || 0;
  const rechazo = zona.rejection_rate || 0;
  const dwell = zona.dwell || 0;
  const clasif = zona.classification || 'fria';

  if (clasif === 'caliente') {
    if (rechazo > 0.5) {
      // Tomar y volver a dejar = el cliente CONSIDERÓ el producto en la zona:
      // es señal de interés real (atrajo la mano) aunque no cerró la compra.
      return `${nombre} es de las zonas más visitadas y ${devol}/${pick} de las tomas se consideran y se dejan de nuevo (${pct(rechazo)}% de consideración): el producto atrae pero no termina de convencer. Ajusta precio, señalización u oferta y revisa el SKU más considerado: hay demanda latente por capitalizar.`;
    }
    return `${nombre} muestra el mejor embudo (${pick} pick-ups, ${dwell.toFixed(1)} s de permanencia). Refuerza el stock de los productos más tomados y conserva el planograma actual.`;
  }

  if (clasif === 'templada') {
    return `${nombre} es intermedia (${visitas} visitas, ${pick} interacciones). Tomar y devolver aquí confirma que hay consideración del surtido: ubica en el tercio medio del estante un SKU estrella o promo de prueba y observa cómo cambia la consideración.`;
  }

  if (visitas > 0 && pick === 0) {
    return `${nombre} recibe ${visitas} visitas pero ${pick} interacciones: la gente pasa de largo. Reubica la categoría hacia una zona caliente o trae tráfico con un display frontal de test.`;
  }

  if (visitas === 0) {
    return `${nombre} no registró visitas en el periodo. Acerca una categoría de alta rotación desde las zonas calientes o reduce la cara de góndola asignada a esta zona.`;
  }

  return `${nombre} registra ${visitas} visitas y ${pick} interacciones: es una zona fría con tráfico bajo frente a las calientes. Acerca una categoría de alta rotación o un display frontal de prueba para elevar la consideración.`;
}

// Recomendacion global de planograma (cruza la zona caliente con la mas fria).
// Reparto de espacio = facing proporcional al interes OBSERVADO (visitas +
// interacciones), como en el motor del backend; no depende del layout estatico.
export function sugerirPlanograma(zonas) {
  const caliente = zonas.find((z) => z.classification === 'caliente');
  const fria = zonas
    .filter((z) => z.classification === 'fria')
    .sort((a, b) => (a.visits || 0) - (b.visits || 0))[0];
  if (!caliente || !fria || caliente.id === fria.id) {
    return 'Sin datos suficientes para recomendar un planograma: se requiere al menos una zona caliente y una fría con tráfico observado.';
  }

  // Puntaje observado: la interaccion (pick-up) pesa mas que la presencia.
  const puntaje = (z) => (z.visits || 0) * 0.5 + (z.pick_ups || 0) * 3.0;
  const total = zonas.reduce((acc, z) => acc + puntaje(z), 0) || 1;
  const reparto = Object.fromEntries(
    zonas.map((z) => [z.id, Math.max(0, Math.round(100 * puntaje(z) / total))])
  );

  return `Planograma recomendado: trasladar la categoría de ${fria.id} (${fria.visits || 0} visitas, ${fria.pick_ups || 0} interacciones) hacia ${caliente.id} (${caliente.pick_ups || 0} tomas) para aprovechar su tráfico y recuperar el espacio frío. Reparto de facing sugerido por interés observado: ${Object.entries(reparto).map(([k, v]) => `${k}=${v}%`).join(', ')}.`;
}