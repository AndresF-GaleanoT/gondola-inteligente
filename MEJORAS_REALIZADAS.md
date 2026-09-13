# Mejoras realizadas — fase de estabilidad

## Backend

- Se agregó `python-multipart` a las dependencias.
- La API ahora diferencia los estados `inactivo`, `iniciando`, `procesando`,
  `completado` y `error`.
- El endpoint `/api/estado` informa porcentaje, frame actual y total de frames.
- Los errores del proceso YOLO se conservan en `outputs/analysis.log` y se
  muestran al frontend sin presentar métricas anteriores como nuevas.
- Las métricas se escriben atómicamente para evitar JSON incompletos.
- Solo se aceptan rutas de video ubicadas dentro de `video/`.
- La carga está limitada a 500 MB de forma predeterminada.
- Los videos originales subidos se eliminan al finalizar el análisis.
- CORS se restringió a los orígenes locales utilizados durante el desarrollo.

## Procesamiento y métricas

- El visor almacena aproximadamente cinco fotogramas por segundo, reduciendo
  el consumo de disco y las transferencias del navegador.
- Se corrigió el flujo de toma y devolución para que ambos eventos puedan
  pertenecer a una misma persona.
- La toma ahora se correlaciona temporalmente: se conserva el último contacto
  de la mano con la góndola y se acepta que el detector reconozca el producto
  hasta 48 frames después. Esto corrige los eventos perdidos por falta de
  coincidencia exacta en un mismo fotograma.
- Se agregó antirrebote: dos observaciones positivas confirman la toma y cinco
  observaciones negativas rearman el seguimiento. Una detección aislada no
  suma y una racha continua sólo cuenta una vez.
- Una misma persona puede realizar varias tomas separadas durante el video.
- La tasa general de rechazo/devolución ahora se calcula con los totales:
  `total de devoluciones / total de tomas`.
- Se corrigieron las zonas de los datos de demostración.

## Frontend

- Se agregó una barra de progreso real durante el análisis.
- Los errores del backend y los tiempos agotados se presentan explícitamente.
- Se eliminan visualmente los resultados anteriores al iniciar un video nuevo.
- La interfaz ahora se adapta a tabletas y celulares.
- Se aclaró el texto de privacidad y la métrica de devolución.
- Se reemplazó el estilo brutalista por un dashboard moderno de analítica:
  navegación sobria, tarjetas suaves, jerarquía tipográfica y modo oscuro.
- Se agregó una tarjeta independiente para las tomas detectadas y textos de
  contexto para interpretar cada indicador.
- Se reorganizaron la carga de video, el visor YOLO, el mapa de calor, las
  recomendaciones y las tarjetas de zonas.
- Se modernizó la paleta del plano 3D y se mantuvo el diseño adaptable a
  escritorio, tableta y celular.

## Pruebas ejecutables

```powershell
python -m unittest discover -s tests -v
cd frontend
npm test
npm run lint
npm run build
```

Las pruebas cubren el cálculo ponderado de métricas, el mapeo de zonas, los
límites porcentuales, el flujo toma-devolución, la respuesta tardía del detector,
el antirrebote, las tomas múltiples y respuestas básicas de la API.
