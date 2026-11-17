// ============================================================================
// DOMAIN / layout - layout del plano (gondolas + pasillos + mapeo de zonas).
// Contrato CONFIGURABLE: las gondolas, pasillos y el vinculo zona->gondola no
// estan hardcodeados en la UI; se declaran aqui (o se cargan desde un JSON) y
// el plano 3D + el dashboard los consumen. Asi un mismo codigo sirve para
// distintos layouts de tienda (la distribucion varia en cada escenario).
// ============================================================================

// Gondolas 3D: coordenadas en el mundo del plano (x=ancho, z=profundidad).
export const GONDOLAS_DEFAULT = [
  { id: 'Góndola izquierda', x: -6.0, z: 0.0, color: 0x16c78c, w: 3.2, d: 8.0, h: 1.6 },
  { id: 'Góndola central', x: 0.0, z: 0.0, color: 0xffb000, w: 2.6, d: 8.0, h: 1.6 },
  { id: 'Góndola derecha', x: 6.0, z: 0.0, color: 0xff4545, w: 3.2, d: 8.0, h: 2.2 },
];

// Pasillos (calles entre gondolas): mismas coordenadas del render 3D.
export const PASILLOS_DEFAULT = [
  { x: -3.3, w: 2.0, d: 8.6 },
  { x: 3.3, w: 2.0, d: 8.6 },
];

// Zona del pipeline -> posicion en el plano (id de la gondola que la ocupa).
// Orden define el area CSS (zone-left/center/right) y el indice en `gondolas`.
export const ZONA_A_GONDOLA = [
  { zona: 'Estante_Izquierdo', gondola: 0, area: 'zone-left' },
  { zona: 'Estante_Central', gondola: 1, area: 'zone-center' },
  { zona: 'Estante_Derecho', gondola: 2, area: 'zone-right' },
];

// Contrato completo: puede sustituirse por un objeto equivalente (desde un
// JSON/API) sin cambiar la UI, siempre que respete esta forma.
export const LAYOUT_DEFAULT = {
  gondolas: GONDOLAS_DEFAULT,
  pasillos: PASILLOS_DEFAULT,
  zonaAGondola: ZONA_A_GONDOLA,
};

// Devuelve el area CSS (y el indice de gondola) de una zona segun el layout.
// Si el layout no declara la zona, cae a un area por indice correlativo.
export function areaDeZona(zonaId, layout = LAYOUT_DEFAULT, indice = 0) {
  const mapeo = layout.zonaAGondola.find((z) => z.zona === zonaId);
  if (mapeo) return { area: mapeo.area, gondola: mapeo.gondola };
  const areas = ['zone-left', 'zone-center', 'zone-right'];
  return { area: areas[indice] || 'zone-left', gondola: indice };
}
