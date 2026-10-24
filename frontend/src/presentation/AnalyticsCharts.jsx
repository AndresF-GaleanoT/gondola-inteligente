import { useMemo } from 'react';
import EChart from './EChart.jsx';

// Paleta sincronizada con los tokens de App.css (neumorfismo claro). Los
// textos de ECharts no leen CSS custom properties, así que se repiten aquí
// a mano — si cambia el tema en App.css, estos valores también deben cambiar.
const PALETA_SERIES = ['#1f9d66', '#c76a00', '#d33b3b', '#2f7fd1', '#d9a300'];
const COLOR_TEXTO = '#2c3242';
const COLOR_TENUE = '#5b6478';
const COLOR_LINEA = '#ccd4e2';

const tooltipBase = {
  backgroundColor: '#ffffff',
  borderWidth: 1,
  borderColor: COLOR_LINEA,
  textStyle: { color: COLOR_TEXTO, fontFamily: "'JetBrains Mono', monospace", fontSize: 12 },
  extraCssText: 'box-shadow: 0 8px 20px rgba(163,177,198,.4);',
};

function ChartCard({ eyebrow, title, note, children, wide = false }) {
  return (
    <article className={`chart-card${wide ? ' wide' : ''}`}>
      <header className="chart-card-head">
        <p>{eyebrow}</p>
        <h3>{title}</h3>
      </header>
      {children}
      <p className="chart-note">{note}</p>
    </article>
  );
}

export default function AnalyticsCharts({ analytics, zoneData }) {
  const funnelOption = useMemo(() => ({
    animationDuration: 650,
    color: PALETA_SERIES,
    tooltip: { ...tooltipBase, trigger: 'item', formatter: '{b}: <b>{c}</b> personas' },
    aria: { enabled: true },
    series: [{
      type: 'funnel',
      left: '6%',
      top: 12,
      bottom: 10,
      width: '88%',
      minSize: '20%',
      maxSize: '100%',
      sort: 'descending',
      gap: 3,
      label: { show: true, position: 'inside', color: '#fff8ee', fontWeight: 700, formatter: '{b}\n{c}' },
      labelLine: { show: false },
      itemStyle: { borderColor: '#e7ecf3', borderWidth: 2 },
      emphasis: { label: { fontSize: 13 } },
      data: analytics.funnel,
    }],
  }), [analytics.funnel]);

  const dwellOption = useMemo(() => {
    const ordered = [...zoneData].sort((a, b) => (a.dwell || 0) - (b.dwell || 0));
    const average = ordered.length
      ? ordered.reduce((sum, zone) => sum + (Number(zone.dwell) || 0), 0) / ordered.length
      : 0;
    return {
      animationDuration: 650,
      color: [PALETA_SERIES[0]],
      tooltip: { ...tooltipBase, trigger: 'axis', valueFormatter: (value) => `${Number(value).toFixed(1)} s` },
      aria: { enabled: true },
      grid: { left: 8, right: 22, top: 18, bottom: 8, containLabel: true },
      xAxis: {
        type: 'value',
        name: 'segundos',
        nameTextStyle: { color: COLOR_TENUE },
        axisLabel: { color: COLOR_TENUE },
        splitLine: { lineStyle: { color: COLOR_LINEA, type: 'dashed' } },
      },
      yAxis: {
        type: 'category',
        data: ordered.map((zone) => zone.id),
        axisLabel: { color: COLOR_TEXTO, width: 115, overflow: 'truncate' },
        axisLine: { lineStyle: { color: COLOR_LINEA } },
        axisTick: { show: false },
      },
      series: [{
        type: 'bar',
        barMaxWidth: 30,
        data: ordered.map((zone, index) => ({ value: Number(zone.dwell) || 0, itemStyle: { color: PALETA_SERIES[index % PALETA_SERIES.length] } })),
        label: { show: true, position: 'right', color: COLOR_TEXTO, formatter: ({ value }) => `${Number(value).toFixed(1)} s` },
        markLine: average > 0 ? {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#d33b3b', type: 'dashed', width: 1.5 },
          label: { color: '#c76a00', formatter: `Promedio ${average.toFixed(1)} s` },
          data: [{ xAxis: average }],
        } : undefined,
      }],
    };
  }, [zoneData]);

  const behaviorOption = useMemo(() => ({
    animationDuration: 650,
    color: ['#ccd4e2', '#c76a00', '#1f9d66'],
    tooltip: { ...tooltipBase, trigger: 'item', formatter: '{b}: <b>{c}</b> ({d}%)' },
    aria: { enabled: true },
    legend: { bottom: 0, left: 'center', textStyle: { color: COLOR_TENUE, fontSize: 11 } },
    series: [{
      type: 'pie',
      radius: ['48%', '72%'],
      center: ['50%', '43%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: '#e7ecf3', borderWidth: 3 },
      label: { color: COLOR_TEXTO, fontWeight: 700, formatter: '{d}%' },
      data: analytics.behavior,
    }],
  }), [analytics.behavior]);

  const sankeyOption = useMemo(() => ({
    animationDuration: 650,
    color: PALETA_SERIES,
    tooltip: { ...tooltipBase, trigger: 'item' },
    aria: { enabled: true },
    series: [{
      type: 'sankey',
      left: 16,
      right: 22,
      top: 14,
      bottom: 14,
      nodeWidth: 18,
      nodeGap: 20,
      draggable: false,
      data: analytics.flows.nodes,
      links: analytics.flows.links,
      label: { color: COLOR_TEXTO, fontWeight: 700, fontSize: 11 },
      lineStyle: { color: 'gradient', curveness: 0.5, opacity: 0.42 },
      emphasis: { focus: 'adjacency' },
    }],
  }), [analytics.flows]);

  return (
    <div className="charts-grid">
      <ChartCard
        eyebrow="Conversión física"
        title="Embudo de interacción"
        note="Cada etapa representa personas rastreadas; la última no confirma una venta, solo que no se observó una devolución durante el video."
      >
        <EChart option={funnelOption} ariaLabel="Embudo de interacción con la góndola" />
      </ChartCard>

      <ChartCard
        eyebrow="Atención por zona"
        title="Permanencia promedio"
        note="Comparación del dwell time por góndola. La línea punteada corresponde al promedio observado en este análisis."
      >
        <EChart option={dwellOption} ariaLabel="Permanencia promedio por góndola" />
      </ChartCard>

      <ChartCard
        eyebrow="Respuesta al producto"
        title="Comportamiento observado"
        note="Distribuye a las personas entre ausencia de toma, toma sin devolución y toma con devolución detectada."
      >
        <EChart option={behaviorOption} ariaLabel="Distribución de comportamiento frente al producto" />
      </ChartCard>

      <ChartCard
        eyebrow="Trayectorias"
        title="Flujo entre góndolas"
        note="Las conexiones se construyen con cambios consecutivos de zona de los IDs temporales; no representan identidad biométrica."
      >
        {analytics.flows.links.length > 0 ? (
          <EChart option={sankeyOption} ariaLabel="Flujo de personas entre góndolas" />
        ) : (
          <div className="chart-empty">
            <strong>Sin transiciones entre zonas</strong>
            <span>El Sankey aparecerá cuando un recorrido pase por dos o más góndolas.</span>
          </div>
        )}
      </ChartCard>
    </div>
  );
}
