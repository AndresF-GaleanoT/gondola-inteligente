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
  const containerRef = useRef(null);
  const printImageRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const chart = echarts.init(containerRef.current, null, { renderer: 'canvas' });
    chart.setOption(option, { notMerge: true });

    const updatePrintImage = () => {
      if (!printImageRef.current || chart.isDisposed()) return;
      chart.resize();
      try {
        printImageRef.current.src = chart.getDataURL({
          type: 'png',
          pixelRatio: 2,
          backgroundColor: '#f6f3e9',
        });
      } catch {
        // El gráfico seguirá disponible en pantalla aunque el navegador no
        // permita construir la imagen de impresión en ese instante.
      }
    };

    const observer = new ResizeObserver(() => {
      chart.resize();
      window.requestAnimationFrame(updatePrintImage);
    });
    observer.observe(containerRef.current);
    const firstSnapshot = window.setTimeout(updatePrintImage, 120);
    window.addEventListener('beforeprint', updatePrintImage);
    window.addEventListener('gondola:prepare-print', updatePrintImage);

    return () => {
      window.clearTimeout(firstSnapshot);
      window.removeEventListener('beforeprint', updatePrintImage);
      window.removeEventListener('gondola:prepare-print', updatePrintImage);
      observer.disconnect();
      chart.dispose();
    };
  }, [option]);

  return (
    <div className="echart-shell">
      <div ref={containerRef} className="echart" role="img" aria-label={ariaLabel} />
      <img ref={printImageRef} className="echart-print-image" alt={ariaLabel} />
    </div>
  );
}
