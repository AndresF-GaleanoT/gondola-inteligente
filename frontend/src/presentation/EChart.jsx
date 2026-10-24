import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { BarChart, FunnelChart, PieChart, SankeyChart } from 'echarts/charts';
import {
  AriaComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  AriaComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  BarChart,
  FunnelChart,
  PieChart,
  SankeyChart,
  CanvasRenderer,
]);

export default function EChart({ option, ariaLabel }) {
  const lienzoRef = useRef(null);
  const imagenImpresionRef = useRef(null);

  useEffect(() => {
    if (!lienzoRef.current) return undefined;
    const instancia = echarts.init(lienzoRef.current, null, { renderer: 'canvas' });
    instancia.setOption(option, { notMerge: true });

    const actualizarImagenImpresion = () => {
      if (!imagenImpresionRef.current || instancia.isDisposed()) return;
      instancia.resize();
      try {
        imagenImpresionRef.current.src = instancia.getDataURL({
          type: 'png',
          pixelRatio: 2,
          backgroundColor: '#ffffff',
        });
      } catch {
        // El gráfico seguirá disponible en pantalla aunque el navegador no
        // permita construir la imagen de impresión en ese instante.
      }
    };

    const observadorTamano = new ResizeObserver(() => {
      instancia.resize();
      window.requestAnimationFrame(actualizarImagenImpresion);
    });
    observadorTamano.observe(lienzoRef.current);
    const primeraCaptura = window.setTimeout(actualizarImagenImpresion, 120);
    window.addEventListener('beforeprint', actualizarImagenImpresion);
    window.addEventListener('gondola:prepare-print', actualizarImagenImpresion);

    return () => {
      window.clearTimeout(primeraCaptura);
      window.removeEventListener('beforeprint', actualizarImagenImpresion);
      window.removeEventListener('gondola:prepare-print', actualizarImagenImpresion);
      observadorTamano.disconnect();
      instancia.dispose();
    };
  }, [option]);

  return (
    <div className="echart-shell">
      <div ref={lienzoRef} className="echart" role="img" aria-label={ariaLabel} />
      <img ref={imagenImpresionRef} className="echart-print-image" alt={ariaLabel} />
    </div>
  );
}
