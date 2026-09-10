import test from 'node:test';
import assert from 'node:assert/strict';
import { buildAnalytics } from '../src/domain/analytics.js';

test('construye un embudo monotono y separa toma de devolucion', () => {
  const analytics = buildAnalytics({
    total_personas_registradas: 4,
    embudo_interaccion: { total_pick_ups: 2, total_put_backs: 1 },
    detalle_por_persona: [
      {
        id_persona: 1,
        interes_compra: true,
        alcance_estante: true,
        eventos: [
          { tipo: 'Producto Adquirido', frame: 10, zona: 'Estante_Izquierdo' },
          { tipo: 'Devolver el producto', frame: 20, zona: 'Estante_Izquierdo' },
        ],
      },
      {
        id_persona: 2,
        interes_compra: true,
        alcance_estante: true,
        eventos: [{ tipo: 'Producto Adquirido', frame: 30, zona: 'Estante_Derecho' }],
      },
    ],
  });

  assert.deepEqual(analytics.funnel.map((stage) => stage.value), [4, 2, 2, 2, 1]);
  assert.deepEqual(analytics.behavior.map((stage) => stage.value), [2, 1, 1]);
});

test('crea enlaces Sankey solo cuando cambia la zona', () => {
  const analytics = buildAnalytics({
    total_personas_registradas: 1,
    embudo_interaccion: { total_pick_ups: 1, total_put_backs: 0 },
    detalle_por_persona: [{
      eventos: [
        { tipo: 'Llegando', frame: 1, zona: 'Estante_Izquierdo' },
        { tipo: 'Mano en Estante', frame: 2, zona: 'Estante_Izquierdo' },
        { tipo: 'Llegando', frame: 8, zona: 'Estante_Central' },
      ],
    }],
  });

  assert.deepEqual(analytics.flows.links, [{
    source: 'Góndola izquierda',
    target: 'Góndola central',
    value: 1,
  }]);
});

