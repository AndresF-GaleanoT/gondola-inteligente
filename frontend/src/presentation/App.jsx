// ============================================================================
// PRESENTATION / App - dashboard estilo editorial (Frontend OpcionB).
// Logica pura en domain/, casos de uso en application/.
// ============================================================================

import { useState, useEffect, useMemo, useCallback } from 'react';
import '../App.css';
import {
  zoneView,
  calcInteractionRate,
  calcRejectionRate,
  ZONE_NAME_MAP,
} from '../domain/zones';
import { analizarZona, sugerirPlanograma } from '../domain/agente';
import { cargarDatos, subirVideo, obtenerEstado } from '../application/api';

const ZONE_TEMP_MAP = {
  caliente: 'hot',
  templada: 'warm',
  fria: '',
};

export default function App() {
  const [, setActiveZone] = useState(null);
  const [zoneData, setZoneData] = useState([]);
  const [activeView, setActiveView] = useState('summary');
  const [evidences, setEvidences] = useState([]);
  const [analysisMeta, setAnalysisMeta] = useState({ generadoEn: null, videoInfo: null });
  const [recomendaciones, setRecomendaciones] = useState(null);
  const [visitors, setVisitors] = useState(0);
  const [pickups, setPickups] = useState(0);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [demoMode, setDemoMode] = useState(false);
  const [videoTick, setVideoTick] = useState(() => Date.now());
  const [toast, setToast] = useState('');
  const [toastVisible, setToastVisible] = useState(false);

  const [vision, setVision] = useState({ frames: [], fps: 24, stride: 2 });
  const [visionIdx, setVisionIdx] = useState(0);
  const [visionPlay, setVisionPlay] = useState(false);

  useEffect(() => {
    let activo = true;
    fetch(`/api/vision-frames?v=${videoTick}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((info) => {
        if (activo && info && info.frames?.length) {
          setVision(info);
          setVisionIdx(0);
          setVisionPlay(true);
        }
      })
      .catch(() => {});
    return () => { activo = false; };
  }, [videoTick]);

  useEffect(() => {
    if (!visionPlay || !vision.frames.length) return;
    const dt = (vision.stride || 2) * 1000 / (vision.fps || 24);
    const timer = setInterval(() => {
      setVisionIdx((i) => (i + 1) % vision.frames.length);
    }, dt);
    return () => clearInterval(timer);
  }, [visionPlay, vision]);

  const showToast = useCallback((msg) => {
    setToast(msg);
    setToastVisible(true);
    setTimeout(() => setToastVisible(false), 2600);
  }, []);

  const interactionRate = useMemo(
    () => calcInteractionRate(visitors, pickups),
    [visitors, pickups]
  );

  const rejectionRate = useMemo(() => calcRejectionRate(zoneData), [zoneData]);

  const conNombresVisibles = (texto = '') =>
    Object.entries(ZONE_NAME_MAP).reduce(
      (t, [raw, visible]) => t.split(raw).join(visible),
      texto ?? ''
    );

  const planograma = useMemo(() => {
    return conNombresVisibles(
      recomendaciones?.planograma?.texto || sugerirPlanograma(zoneData)
    );
  }, [recomendaciones, zoneData]);

  const executiveSummary = useMemo(() => {
    const orderedByVisits = [...zoneData].sort((a, b) => (b.visits || 0) - (a.visits || 0));
    const orderedByPickups = [...zoneData].sort((a, b) => (b.pick_ups || 0) - (a.pick_ups || 0));
    const busiest = orderedByVisits[0];
    const mostInteractive = orderedByPickups.find((zone) => (zone.pick_ups || 0) > 0);
    const returns = zoneData.reduce((total, zone) => total + (Number(zone.put_backs) || 0), 0);
    return { busiest, mostInteractive, returns };
  }, [zoneData]);

  const sugerenciaZona = (zone) =>
    conNombresVisibles(
      recomendaciones?.por_zona?.[zone.rawId] || analizarZona(zone)
    );

  const recentEvents = useMemo(() => {
    return evidences.slice(-5).reverse().map((e) => {
      const seg = Number(e.segundo || 0);
      const min = Math.floor(seg / 60);
      const sec = (seg % 60).toFixed(0).padStart(2, '0');
      return {
        time: `${min}:${sec}`,
        label: e.tipo === 'Devolver el producto' ? 'Producto adquirido' : 'Mano en estante',
        zona: conNombresVisibles(e.zona || 'Zona sin identificar'),
        id: e.idPersona,
      };
    });
  }, [evidences]);

  const evidenceRows = useMemo(() => {
    return evidences.map((e) => {
      const seg = Number(e.segundo || 0);
      const min = Math.floor(seg / 60);
      const sec = (seg % 60).toFixed(0).padStart(2, '0');
      const isReturn = e.tipo === 'Devolver el producto';
      return {
        id: `ID ${String(e.idPersona).padStart(2, '0')}`,
        time: `${min}:${sec}`,
        label: isReturn ? 'Producto devuelto' : 'Mano en estante',
        zona: conNombresVisibles(e.zona || 'Zona sin identificar'),
        badge: isReturn ? 'Devolución' : 'Contacto',
        isTransit: false,
      };
    });
  }, [evidences]);

  const aplicarDatos = useCallback((data) => {
    setVisitors(data.visitors);
    setPickups(data.pickups);
    setZoneData(data.zones);
    setRecomendaciones(data.recomendaciones);
    setEvidences(data.evidencias || []);
    setAnalysisMeta({ generadoEn: data.generadoEn, videoInfo: data.videoInfo });
    setDemoMode(data.origen === 'demo');
    setVideoTick(Date.now());
  }, []);

  const loadData = useCallback(async () => {
    try {
      return await cargarDatos();
    } catch (error) {
      console.error('Error cargando datos:', error);
      return null;
    }
  }, []);

  useEffect(() => {
    let activo = true;
    loadData().then((data) => {
      if (activo && data) aplicarDatos(data);
    });
    return () => { activo = false; };
  }, [loadData, aplicarDatos]);

  const handleFileChange = (e) => {
    const file = e.target.files?.[0] || null;
    if (file && file.size > 500 * 1024 * 1024) {
      setSelectedFile(null);
      setUploadMsg('El video supera el límite de 500 MB.');
      e.target.value = '';
      return;
    }
    setSelectedFile(file);
    setAnalysisProgress(0);
    setUploadMsg('');
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setUploadMsg('Selecciona un archivo de video.');
      return;
    }
    setUploading(true);
    setAnalysisProgress(0);
    setUploadMsg('Subiendo y disparando el análisis…');
    try {
      const res = await subirVideo(selectedFile);
      setVision({ frames: [], fps: 24, stride: 2 });
      setVisionPlay(false);
      setVisitors(0);
      setPickups(0);
      setZoneData([]);
      setUploadMsg(`Video subido. ${res.mensaje || 'Análisis en segundo plano.'}`);
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 2500));
        const estado = await obtenerEstado();
        if (estado?.estado === 'error') {
          throw new Error(estado.error || 'Error en el procesamiento YOLO.');
        }
        if (Number.isFinite(Number(estado?.progreso_pct))) {
          const progreso = Math.round(Number(estado.progreso_pct));
          setAnalysisProgress(progreso);
          setUploadMsg(`Analizando video… ${progreso}%`);
        }
        if (estado?.estado === 'completado') {
          const data = await loadData();
          if (data) {
            aplicarDatos(data);
            setAnalysisProgress(100);
            setUploadMsg('Análisis completado.');
            showToast('Análisis actualizado. Las métricas están listas.');
          } else {
            throw new Error('El análisis terminó, pero no produjo métricas válidas.');
          }
          break;
        }
        if (i === 119) {
          throw new Error('Tiempo máximo de espera superado (5 min).');
        }
      }
    } catch (err) {
      setUploadMsg(`Error: ${err.message}`);
    } finally {
      setUploading(false);
    }
  };

  const changeView = (view) => {
    setActiveView(view);
    setActiveZone(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const fileName = selectedFile?.name || 'Seleccionar archivo de video';

  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand">
          <div className="brand-mark">A</div>
          <div className="brand-copy">
            <strong>AlphaNode</strong>
            <span>RETAIL LAB</span>
          </div>
        </div>
        <nav className="nav">
          {[
            ['summary', '01', 'Lectura general'],
            ['spatial', '02', 'Plano de tienda'],
            ['evidence', '03', 'Evidencias'],
            ['report', '04', 'Informe'],
          ].map(([id, num, label]) => (
            <button
              key={id}
              className={`nav-button${activeView === id ? ' active' : ''}`}
              onClick={() => changeView(id)}
            >
              <b>{num}</b>
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="rail-foot">
          <p className="privacy">Privacidad por diseño</p>
          <p>Sin reconocimiento facial, emociones ni datos biométricos.</p>
          <p>AlphaNode · HackTech 5.0</p>
        </div>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <p className="eyebrow">Registro de comportamiento en tienda</p>
            <h1>Góndola<br />Inteligente</h1>
          </div>
          <div className="edition">
            ANÁLISIS <strong>#GI-001</strong><br />
            {analysisMeta.generadoEn
              ? new Date(analysisMeta.generadoEn).toLocaleDateString('es-CO')
              : new Date().toLocaleDateString('es-CO')}<br />
            VIDEO PREGRABADO
          </div>
        </header>

        {/* =================== SUMMARY =================== */}
        <section className={`page${activeView === 'summary' ? ' active' : ''}`} id="summary">
          <div className="command">
            <div className="command-copy">
              <strong>Nueva lectura</strong>
              <span>Seleccione una grabación de hasta 500 MB.</span>
            </div>
            <label className="file-box" htmlFor="videoInputB">
              <span>{fileName}</span>
            </label>
            <input id="videoInputB" type="file" accept="video/*" hidden onChange={handleFileChange} />
            <button className="run" onClick={handleUpload} disabled={uploading || !selectedFile}>
              {uploading ? 'Procesando…' : 'Analizar video'}
            </button>
          </div>

          {uploadMsg && <p className="upload-msg">{uploadMsg}</p>}
          {uploading && (
            <div className="upload-progress">
              <div className="upload-progress-bar">
                <span style={{ width: `${analysisProgress}%` }} />
              </div>
              <p className="upload-progress-text">{analysisProgress}%</p>
            </div>
          )}
          {demoMode && (
            <p className="upload-msg">Mostrando datos de ejemplo: el backend no tiene métricas previas.</p>
          )}

          <div className="metric-strip">
            <article className="metric">
              <span className="metric-label">Visitantes únicos</span>
              <strong className="metric-value">{visitors}</strong>
              <span className="metric-note">Personas anónimas</span>
            </article>
            <article className="metric">
              <span className="metric-label">Tomas detectadas</span>
              <strong className="metric-value">{pickups}</strong>
              <span className="metric-note">Productos retirados</span>
            </article>
            <article className="metric">
              <span className="metric-label">Tasa de interacción</span>
              <strong className="metric-value">{interactionRate}%</strong>
              <span className="metric-note">Tomas por visitante</span>
            </article>
            <article className="metric">
              <span className="metric-label">Tasa de devolución</span>
              <strong className="metric-value">{rejectionRate}%</strong>
              <span className="metric-note">Put-back / pick-up</span>
            </article>
          </div>

          <div className="stage">
            <div className="stage-main">
              <div className="section-head">
                <h2>Escena analizada</h2>
                <span className="live">Pipeline activo</span>
              </div>
              {vision.frames.length > 0 ? (
                <div className="observation vision-panel" aria-label="Visión de las góndolas">
                  <img
                    className="vision-video"
                    src={`/vision-frames/${vision.frames[visionIdx] || ''}?v=${videoTick}`}
                    alt="Visión de las góndolas"
                  />
                  <div className="vision-controls">
                    <button type="button" onClick={() => setVisionPlay((p) => !p)}>
                      {visionPlay ? '⏸ Pausa' : '▶ Reproducir'}
                    </button>
                    <span>Fotograma {visionIdx + 1} / {vision.frames.length}</span>
                    <button type="button" onClick={() => setVisionIdx(0)}>
                      Reiniciar
                    </button>
                  </div>
                  <span className="frame-counter" style={{ bottom: 58 }}>
                    FOTOGRAMA {visionIdx + 1} / {vision.frames.length}
                  </span>
                </div>
              ) : (
                <div className="observation" style={{ display: 'grid', placeItems: 'center' }}>
                  <p style={{ color: 'var(--muted)', fontSize: '.82rem', textAlign: 'center' }}>
                    La visión de las góndolas se generará al ejecutar el análisis.<br />
                    Sube un video o usa los datos existentes.
                  </p>
                </div>
              )}
            </div>
            <aside className="stage-side">
              <div className="event-head">
                <p>Secuencia verificada</p>
                <h3>Eventos recientes</h3>
              </div>
              <ol className="event-list">
                {recentEvents.length > 0 ? recentEvents.map((evt, i) => (
                  <li key={i}>
                    <time>{evt.time}</time>
                    <div>
                      <strong>{evt.label}</strong>
                      <span>ID {String(evt.id).padStart(2, '0')} · {evt.zona}</span>
                    </div>
                  </li>
                )) : (
                  <li>
                    <time>--:--</time>
                    <div>
                      <strong>Sin eventos</strong>
                      <span>Analiza un video para ver eventos</span>
                    </div>
                  </li>
                )}
              </ol>
              {planograma && (
                <div className="callout">
                  <b>Lectura comercial</b>
                  {planograma}
                </div>
              )}
            </aside>
          </div>
        </section>

        {/* =================== SPATIAL =================== */}
        <section className={`page${activeView === 'spatial' ? ' active' : ''}`} id="spatial">
          <div className="page-title">
            <h2>Distribución espacial</h2>
            <p>El mapa superpone la intensidad de circulación y permanencia sobre el plano configurado.</p>
          </div>
          <div className="spatial-grid">
            <article className="floor-card">
              <div className="section-head">
                <h2>Mapa de actividad</h2>
                <span className="legend"><i></i>Mayor intensidad</span>
              </div>
              <div className="floor">
                <div className="shelf left">Góndola izquierda</div>
                <div className="shelf center">Góndola central</div>
                <div className="shelf right">Góndola derecha</div>
                <i className="heat h1"></i>
                <i className="heat h2"></i>
                <i className="heat h3"></i>
              </div>
            </article>
            <aside className="zone-ledger">
              {zoneData.map((zone) => {
                const view = zoneView(zone);
                const tempClass = ZONE_TEMP_MAP[zone.classification] || '';
                const insight = sugerenciaZona(zone);
                return (
                  <article
                    key={zone.id}
                    className="zone-row"
                    onMouseEnter={() => setActiveZone(zone)}
                    onMouseLeave={() => setActiveZone(null)}
                    style={{ cursor: 'pointer' }}
                  >
                    <div className="zone-top">
                      <h3>{zone.id}</h3>
                      <span className={`temp${tempClass ? ' ' + tempClass : ''}`}>
                        {view.etiqueta.toUpperCase()}
                      </span>
                    </div>
                    <div className="zone-stats">
                      <div><span>Entradas</span><b>{zone.visits}</b></div>
                      <div><span>Tomas</span><b>{zone.pick_ups}</b></div>
                      <div><span>Tiempo</span><b>{Number.isFinite(zone.dwell) ? `${zone.dwell.toFixed(1)}s` : '0.0s'}</b></div>
                    </div>
                    <p className="zone-insight">{insight}</p>
                  </article>
                );
              })}
            </aside>
          </div>
        </section>

        {/* =================== EVIDENCE =================== */}
        <section className={`page${activeView === 'evidence' ? ' active' : ''}`} id="evidence">
          <div className="page-title">
            <h2>Evidencias</h2>
            <p>Cada evento conserva el momento, la zona y una identidad temporal anónima para facilitar la validación.</p>
          </div>
          {evidenceRows.length > 0 ? (
            <div className="evidence-sheet">
              {evidenceRows.map((row, i) => (
                <div className="evidence-row" key={i}>
                  <span className="id">{row.id}</span>
                  <time>{row.time}</time>
                  <div>
                    <strong>{row.label}</strong>
                    <small>{row.zona} · fotograma</small>
                  </div>
                  <span className={`badge${row.isTransit ? ' transit' : ''}`}>
                    {row.badge}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="evidence-empty">
              <h2>Aún no hay interacciones documentadas</h2>
              <p>Analiza un video con tomas o devoluciones para generar las evidencias.</p>
            </div>
          )}
        </section>

        {/* =================== REPORT =================== */}
        <section className={`page${activeView === 'report' ? ' active' : ''}`} id="report">
          <div className="page-title">
            <h2>Informe ejecutivo</h2>
            <p>Resumen listo para compartir con el equipo de space management.</p>
          </div>
          <div className="report-sheet">
            <article className="report-lead">
              <p className="eyebrow">Recomendación comercial</p>
              <h3>Redistribuir el facing según interés observado.</h3>
              <p>{planograma || 'Analiza un video para obtener recomendaciones personalizadas.'}</p>
              <button className="download" onClick={() => window.print()}>
                Imprimir / guardar PDF
              </button>
            </article>
            <div className="report-list">
              <div className="report-item">
                <b>Hallazgo principal</b>
                <p>
                  {executiveSummary.busiest
                    ? `La ${executiveSummary.busiest.id} concentra la mayor actividad con ${executiveSummary.busiest.visits} entradas.`
                    : 'Sin datos suficientes aún.'}
                </p>
              </div>
              <div className="report-item">
                <b>Oportunidad</b>
                <p>
                  {executiveSummary.mostInteractive
                    ? `${executiveSummary.mostInteractive.id} registra ${executiveSummary.mostInteractive.pick_ups} tomas de producto.`
                    : 'No se detectaron tomas en el análisis actual.'}
                </p>
              </div>
              <div className="report-item">
                <b>Resultado</b>
                <p>
                  {pickups} tomas · {executiveSummary.returns} devoluciones
                  {visitors > 0 ? ` — ${visitors} visitantes analizados` : ''}.
                </p>
              </div>
              <div className="report-item">
                <b>Privacidad</b>
                <p>Los IDs son temporales; no se identifican rostros, emociones ni información biométrica.</p>
              </div>
            </div>
          </div>
        </section>

        <div className={`toast${toastVisible ? ' show' : ''}`} role="status" aria-live="polite">
          {toast}
        </div>
      </main>
    </div>
  );
}
