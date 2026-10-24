import { ZONE_NAME_MAP } from './zones.js';

const PICK_UP = 'Producto Adquirido';
const PUT_BACK = 'Devolver el producto';

function number(valor) {
  const numerico = Number(valor);
  return Number.isFinite(numerico) ? numerico : 0;
}

function visibleZone(rawZone) {
  return ZONE_NAME_MAP[rawZone] || rawZone || null;
}

function orderedEvents(person = {}) {
  return [...(person.eventos || [])].sort(
    (a, b) => number(a.frame) - number(b.frame)
  );
}

function personState(person = {}) {
  const events = orderedEvents(person);
  const hasPickup = events.some((event) => event.tipo === PICK_UP)
    || Boolean(person.producto_adquirido);
  const hasReturn = events.some((event) => event.tipo === PUT_BACK)
    || Boolean(person.devolucion_estante);
  const approached = Boolean(person.alcance_estante)
    || events.some((event) => event.tipo === 'Mano en Estante' || event.tipo === PICK_UP);
  const stopped = Boolean(person.interes_compra)
    || number(person.tiempo_viendo_seg) > 0
    || approached;

  return { events, hasPickup, hasReturn, approached, stopped };
}

function buildFlows(people) {
  const enlaces = new Map();

  people.forEach((person) => {
    const secuenciaZonas = [];
    orderedEvents(person).forEach((event) => {
      const zona = visibleZone(event.zona);
      if (zona && secuenciaZonas[secuenciaZonas.length - 1] !== zona) secuenciaZonas.push(zona);
    });

    for (let indice = 1; indice < secuenciaZonas.length; indice += 1) {
      const origen = secuenciaZonas[indice - 1];
      const destino = secuenciaZonas[indice];
      if (origen === destino) continue;
      const clave = `${origen}::${destino}`;
      enlaces.set(clave, {
        source: origen,
        target: destino,
        value: (enlaces.get(clave)?.value || 0) + 1,
      });
    }
  });

  const listaEnlaces = [...enlaces.values()];
  const nombres = [...new Set(listaEnlaces.flatMap((enlace) => [enlace.source, enlace.target]))];
  return { nodes: nombres.map((nombre) => ({ name: nombre })), links: listaEnlaces };
}

export function buildAnalytics(payload = {}) {
  const people = payload.detalle_por_persona || [];
  const states = people.map(personState);
  const totalVisitors = Math.max(0, number(payload.total_personas_registradas));
  const totalPickups = Math.max(0, number(payload.embudo_interaccion?.total_pick_ups));
  const totalReturns = Math.max(0, number(payload.embudo_interaccion?.total_put_backs));

  const detectedPickupPeople = states.filter((state) => state.hasPickup).length;
  const pickupPeople = Math.min(
    totalVisitors,
    Math.max(detectedPickupPeople, Math.min(totalVisitors, totalPickups))
  );
  const returnedPeople = Math.min(
    pickupPeople,
    Math.max(states.filter((state) => state.hasReturn).length,
      Math.min(pickupPeople, totalReturns))
  );
  const keptPeople = Math.max(0, pickupPeople - returnedPeople);
  const approachedRaw = states.filter((state) => state.approached).length;
  const stoppedRaw = states.filter((state) => state.stopped).length;
  const approached = Math.min(totalVisitors, Math.max(approachedRaw, pickupPeople));
  const stopped = Math.min(totalVisitors, Math.max(stoppedRaw, approached));

  return {
    funnel: [
      { name: 'Tránsito observado', value: totalVisitors },
      { name: 'Parada frente a góndola', value: stopped },
      { name: 'Aproximación al estante', value: approached },
      { name: 'Toma de producto', value: pickupPeople },
      { name: 'Sin devolución observada', value: keptPeople },
    ],
    behavior: [
      { name: 'Sin toma detectada', value: Math.max(0, totalVisitors - pickupPeople) },
      { name: 'Toma sin devolución', value: keptPeople },
      { name: 'Toma y devolución', value: returnedPeople },
    ],
    flows: buildFlows(people),
  };
}

