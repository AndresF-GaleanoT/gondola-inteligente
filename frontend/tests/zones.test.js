import test from 'node:test';
import assert from 'node:assert/strict';

import {
  calcInteractionRate,
  calcRejectionRate,
  mergeZones,
} from '../src/domain/zones.js';

test('la tasa de rechazo se calcula con totales y no promediando zonas', () => {
  const zonas = [
    { pick_ups: 9, put_backs: 1, rejection_rate: 1 / 9 },
    { pick_ups: 1, put_backs: 1, rejection_rate: 1 },
  ];
  assert.equal(calcRejectionRate(zonas), 20);
});

test('la tasa de interaccion queda limitada a un porcentaje valido', () => {
  assert.equal(calcInteractionRate(4, 6), 100);
  assert.equal(calcInteractionRate(0, 1), 0);
});

test('las zonas vigentes se traducen al layout visible', () => {
  const zonas = mergeZones([
    { id: 'Estante_Izquierdo', visitas: 2 },
    { id: 'Estante_Central', visitas: 3 },
    { id: 'Estante_Derecho', visitas: 4 },
  ]);
  assert.deepEqual(zonas.map((z) => z.id), [
    'Góndola izquierda',
    'Góndola central',
    'Góndola derecha',
  ]);
});
