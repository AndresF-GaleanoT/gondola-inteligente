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

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const chart = echarts.init(containerRef.current, null, { renderer: 'canvas' });
    chart.setOption(option, { notMerge: true });

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [option]);

  return <div ref={containerRef} className="echart" role="img" aria-label={ariaLabel} />;
}

