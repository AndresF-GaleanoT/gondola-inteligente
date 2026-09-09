// ============================================================================
// PRESENTATION / App - componente de UI del dashboard (arquitectura limpia).
// La logica pura vive en domain/, los casos de uso en application/.
// ============================================================================

import { lazy, Suspense, useRef, useState, useEffect, useMemo, useCallback } from 'react';
import simpleheat from 'simpleheat';
import '../App.css';
import {
  zoneView,
  calcInteractionRate,
  calcRejectionRate,
  ZONE_NAME_MAP,
} from '../domain/zones';
import { analizarZona, sugerirPlanograma } from '../domain/agente';
import { cargarDatos, subirVideo, obtenerEstado } from '../application/api';
// three.js (~600 KB) se carga bajo demanda, cuando el plano esta a la vista:
// el resto del dashboard ya no paga ese peso en el primer paint.
const HabboFloor = lazy(() => import('./HabboFloor'));
import { LAYOUT_DEFAULT } from '../domain/layout';

// Margen (en pixeles) para que el resplandor del heatmap respire dentro del
// pasillo sin invadir las gondolas.
const AISLE_MARGIN = 8;

// Orden de areas CSS tal como las reporta HabboFloor, derivado del layout.
  const GONDOLA_ORDEN = LAYOUT_DEFAULT.zonaAGondola.map((z) => z.area);

export default function App() {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const liveStreamRef = useRef(null);
  const ultimaDibujadaRef = useRef(null);
  const [aisles, setAisles] = useState([]);
  const [gondolas, setGondolas] = useState([]);
  const [activeZone, setActiveZone] = useState(null);
  const [zoneData, setZoneData] = useState([]);
  const [heatMatrix, setHeatMatrix] = useState([]);
  const [activeView, setActiveView] = useState('overview');
  const [evidences, setEvidences] = useState([]);
  const [analysisMeta, setAnalysisMeta] = useState({ generadoEn: null, videoInfo: null });

  // Rect en px de la gondola 3D de una zona (segun el orden de GONDOLAS que
  // reporta HabboFloor). Si el plano aun no lo tiene, se usa el clip-path CSS.
  const zoneRect = (area) => {
    const idx = GONDOLA_ORDEN.indexOf(area);
    const rect = idx >= 0 ? gondolas[idx] : undefined;
    if (!rect) return {};
    return { left: rect.x, top: rect.y, width: rect.w, height: rect.h, clipPath: 'none' };
  };
  const [recomendaciones, setRecomendaciones] = useState(null);
  const [visitors, setVisitors] = useState(0);
  const [pickups, setPickups] = useState(0);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState('');
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [dark, setDark] = useState(() => {
    // Preferencia persistida; si no hay, se respeta el tema del SO.
    try {
      const saved = localStorage.getItem('gondola-theme');
      if (saved === 'dark' || saved === 'light') return saved === 'dark';
    } catch { /* sin localStorage (entornos restrictivos) */ }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
  });
  const [demoMode, setDemoMode] = useState(false);
  // Marca de refresco del video anotado: cambia con cada analisis para que el
  // navegador no use la version cacheada.
  const [videoTick, setVideoTick] = useState(() => Date.now());
  // "Vision de las gondolas": fotogramas anotados por el pipeline YOLO que se
  // reproducen como secuencia animada (los navegadores no decodifican el codec
  // mp4v del OpenCV, asi que no se usa <video> sino una galeria de JPEGs).
  const [vision, setVision] = useState({ frames: [], fps: 24, stride: 2 });
  const [visionIdx, setVisionIdx] = useState(0);
  const [visionPlay, setVisionPlay] = useState(false);

  // Al cambiar videoTick (analisis recien terminado) se recarga el indice.
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

  // Avance de la secuencia a la cadencia real del video: cada fotograma
  // guardado equivale a `stride` fotogramas del video original.
  useEffect(() => {
    if (!visionPlay || !vision.frames.length) return;
    const dt = (vision.stride || 2) * 1000 / (vision.fps || 24);
    const timer = setInterval(() => {
      setVisionIdx((i) => (i + 1) % vision.frames.length);
    }, dt);
    return () => clearInterval(timer);
  }, [visionPlay, vision]);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    try {
      localStorage.setItem('gondola-theme', dark ? 'dark' : 'light');
    } catch { /* sin localStorage */ }
  }, [dark]);

  const interactionRate = useMemo(
    () => calcInteractionRate(visitors, pickups),
    [visitors, pickups]
  );

  const rejectionRate = useMemo(() => calcRejectionRate(zoneData), [zoneData]);

  const evidenceCards = useMemo(() => evidences.map((evidence) => {
    const targetFrame = Number(evidence.frame) || 0;
    let nearest = null;
    let nearestDistance = Number.POSITIVE_INFINITY;
    vision.frames.forEach((name) => {
      const frame = Number(name.match(/(\d+)/)?.[1]);
      const distance = Math.abs(frame - targetFrame);
      if (Number.isFinite(frame) && distance < nearestDistance) {
        nearest = name;
        nearestDistance = distance;
      }
    });
    return { ...evidence, image: nearest, nearestDistance };
  }), [evidences, vision.frames]);

  // Traduce ids crudos del pipeline (Estante_Inferior...) a los nombres que la
  // web muestra (Góndola izquierda...).
  const conNombresVisibles = (texto = '') =>
    Object.entries(ZONE_NAME_MAP).reduce(
      (t, [raw, visible]) => t.split(raw).join(visible),
      texto ?? ''
    );

  const planograma = useMemo(() => {
    // Preferimos la propuesta calculada por el pipeline (motor del backend);
    // si el JSON es viejo o no la trae, cae al agente local.
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

  const aplicarDatos = useCallback((data) => {
    setVisitors(data.visitors);
    setPickups(data.pickups);
    setZoneData(data.zones);
    setRecomendaciones(data.recomendaciones);
    setEvidences(data.evidencias || []);
    setAnalysisMeta({ generadoEn: data.generadoEn, videoInfo: data.videoInfo });
    if (data.heatMatrix.length) setHeatMatrix(data.heatMatrix);
    setDemoMode(data.origen === 'demo');
    setVideoTick(Date.now());
  }, []);

  const loadData = useCallback(async () => {
    try {
      return await cargarDatos();
    } catch (error) {
      console.error('Error cargando los datos reales:', error);
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

  const handleUpload = async (e) => {
    e.preventDefault();
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
      setHeatMatrix([]);
      const canvas = canvasRef.current;
      canvas?.getContext('2d')?.clearRect(0, 0, canvas.width, canvas.height);
      ultimaDibujadaRef.current = null;
      setUploadMsg(`Video subido. ${res.mensaje || 'Análisis en segundo plano.'}`);
      // El pipeline corre en background: se consulta /api/estado cada 2.5 s y,
      // cuando termina, se recargan los datos del dashboard. Hasta 5 min
      // (antes 60 s: un analisis largo nunca llegaba a recargar).
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 2500));
        const estado = await obtenerEstado();
        if (estado?.estado === 'error') {
          throw new Error(estado.error || 'El procesamiento YOLO terminó con error.');
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
            setUploadMsg('Análisis completado: el dashboard muestra los datos del video.');
          } else {
            throw new Error('El análisis terminó, pero no produjo métricas válidas.');
          }
          break;
        }
        if (i === 119) {
          throw new Error('El análisis superó el tiempo máximo de espera de 5 minutos.');
        }
      }
    } catch (err) {
      setUploadMsg(`Error: ${err.message}`);
    } finally {
      setUploading(false);
    }
  };

  const drawHeatmap = useCallback(() => {
    if (!canvasRef.current || !containerRef.current || !heatMatrix.length) return;
    try {
      const cont = containerRef.current;
      const canvas = canvasRef.current;
      const w = cont.clientWidth;
      const h = cont.clientHeight;
      if (!w || !h) return;

      // Validacion defensiva: la grilla del backend llega como array 2D
      // [filas=Y][columnas=X]. Si viene plana o vacia, no se dibuja (antes
      // asumia filas/cols y podia reventar con NaN).
      const rows = heatMatrix.length;
      const first = heatMatrix[0];
      if (!Array.isArray(first)) return;
      const cols = first.length;
      if (!rows || !cols) return;

      // Evita redibujos inecesarios (p. ej. cada resize de la ventana): solo
      // se vuelve a pintar si cambian las dimensiones, la matriz o la
      // geometria de los pasillos 3D. La firma se actualiza DESPUES de
      // dibujar con exito, para no "marcar como pintado" un intento fallido
      // o incompleto (p. ej. sin pasillos o sin puntos validos).
      const firma = JSON.stringify([w, h, aisles.map((a) => [a.x, a.y, a.w, a.h])]);
      const cach_ = ultimaDibujadaRef.current;
      if (cach_ && cach_.firma === firma && cach_.data === heatMatrix) return;

      canvas.width = w;
      canvas.height = h;

      const cellWidth = canvas.width / cols;
      const cellHeight = canvas.height / rows;

      // Un punto es valido solo si cae dentro de alguno de los pasillos 3D.
      const insideAisles = (px, py) =>
        aisles.some((a) => (
          px >= a.x + AISLE_MARGIN &&
          px <= a.x + a.w - AISLE_MARGIN &&
          py >= a.y + AISLE_MARGIN &&
          py <= a.y + a.h - AISLE_MARGIN
        ));

      const points = [];
      let maxVal = 0;

      // Orientacion: row -> eje Y (arriba a abajo), col -> eje X, tal como la
      // exporta el backend (grilla[Y][X]).
      for (let r = 0; r < rows; r++) {
        const fila = heatMatrix[r];
        if (!Array.isArray(fila)) continue;
        for (let c = 0; c < cols; c++) {
          const val = Number(fila[c]) || 0;
          if (val > 0) {
            const px = Math.round((c * cellWidth) + (cellWidth / 2));
            const py = Math.round((r * cellHeight) + (cellHeight / 2));
            if (insideAisles(px, py)) {
              points.push([px, py, val]);
              if (val > maxVal) maxVal = val;
            }
          }
        }
      }

      if (!points.length) return;

      // simpleheat hace getImageData en cada draw; crear el contexto con
      // willReadFrequently evita el warning de "multiple readback operations".
      canvas.getContext('2d', { willReadFrequently: true });

      const heat = simpleheat(canvas);
      heat.clear();
      heat.data(points);
      // Max DINAMICO (antes 100 fijo): el backend normaliza 0-100, pero si
      // llegase 0-255 o 0-1 el color no debe saturarse en un valor incorrecto.
      heat.max(maxVal);
      // Radio de difusion en px: la grilla ahora es mas fina (96x96), asi que
      // un radio menor conserva los focos localizados en vez de mancharlos.
      heat.radius(36, 26);
      heat.draw();
      // Solo se cachea tras dibujar con exito.
      ultimaDibujadaRef.current = { firma, data: heatMatrix };
    } catch (err) {
      console.error('Error rendering heatmap:', err);
    }
  }, [heatMatrix, aisles]);

  useEffect(() => {
    if (activeView !== 'spatial') return undefined;
    const timer = setTimeout(() => drawHeatmap(), 100);
    return () => clearTimeout(timer);
  }, [drawHeatmap, activeView]);

  // Redibuja el heatmap cuando el contenedor cambia de tamaño (p. ej. tras
  // entrar a la pestaña o redimensionar la ventana), usando la última matriz.
  useEffect(() => {
    if (activeView !== 'spatial') return undefined;
    const cont = containerRef.current;
    if (!cont) return undefined;
    const ro = new ResizeObserver(() => drawHeatmap());
    ro.observe(cont);
    return () => ro.disconnect();
  }, [drawHeatmap, activeView]);

  const changeView = (view) => {
    if (view === 'spatial') {
      // La vista crea un canvas nuevo. Se invalida la firma anterior para que
      // el mapa vuelva a pintarse aunque conserve datos y dimensiones.
      ultimaDibujadaRef.current = null;
    }
    setActiveView(view);
    setActiveZone(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const openFullscreen = async (ref) => {
    const element = ref.current;
    if (!element) return;
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await element.requestFullscreen();
    } catch (error) {
      console.error('No se pudo cambiar a pantalla completa:', error);
    }
  };

  const viewContent = {
    overview: ['Panel de analítica retail', 'Inteligencia de góndola', 'Convierte el movimiento de la tienda en decisiones claras de exhibición.'],
    spatial: ['Analítica espacial', 'Distribución espacial', 'Explora el tráfico, la permanencia y la interacción en cada zona.'],
    evidence: ['Auditoría visual', 'Evidencias de interacción', 'Verifica cada evento detectado en el fotograma correspondiente.'],
    report: ['Documento ejecutivo', 'Reporte de analítica retail', 'Consulta la vista previa y exporta los resultados en formato PDF.'],
  }[activeView];

  return (
    <div className="layout-app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <svg className="brand-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </span>
          <span className="brand-copy">
            <span className="brand-text">Alphanode</span>
            <span className="brand-subtitle">Retail Intelligence</span>
          </span>
        </div>

        <nav className="nav-menu" aria-label="Secciones del panel">
          <button
            type="button"
            className={`nav-item${activeView === 'overview' ? ' active' : ''}`}
            onClick={() => changeView('overview')}
            aria-current={activeView === 'overview' ? 'page' : undefined}
            title="Análisis principal"
          >
            <svg className="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 13h6V4H4v9zm0 7h6v-4H4v4zm10 0h6v-9h-6v9zm0-16v4h6V4h-6z" />
            </svg>
            <span className="nav-copy">
              <strong>Análisis principal</strong>
              <small>Indicadores y monitoreo</small>
            </span>
          </button>
          <button
            type="button"
            className={`nav-item${activeView === 'spatial' ? ' active' : ''}`}
            onClick={() => changeView('spatial')}
            aria-current={activeView === 'spatial' ? 'page' : undefined}
            title="Distribución espacial"
          >
            <svg className="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
            </svg>
            <span className="nav-copy">
              <strong>Distribución espacial</strong>
              <small>Mapa de calor y zonas</small>
            </span>
          </button>
          <button
            type="button"
            className={`nav-item${activeView === 'evidence' ? ' active' : ''}`}
            onClick={() => changeView('evidence')}
            aria-current={activeView === 'evidence' ? 'page' : undefined}
            title="Evidencias de interacción"
          >
            <svg className="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.55-2.28A1 1 0 0121 8.62v6.76a1 1 0 01-1.45.9L15 14M5 6h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2z" />
            </svg>
            <span className="nav-copy">
              <strong>Evidencias</strong>
              <small>Tomas y devoluciones</small>
            </span>
          </button>
          <button
            type="button"
            className={`nav-item${activeView === 'report' ? ' active' : ''}`}
            onClick={() => changeView('report')}
            aria-current={activeView === 'report' ? 'page' : undefined}
            title="Reporte descargable"
          >
            <svg className="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 3h7l4 4v14H7V3zm7 0v5h5M10 13h5m-5 4h5" />
            </svg>
            <span className="nav-copy">
              <strong>Reporte</strong>
              <small>Vista previa y PDF</small>
            </span>
          </button>
        </nav>

       

        <div className="theme-toggle-wrap">
          <button
            type="button"
            className="theme-toggle"
            onClick={() => setDark((d) => !d)}
            title={dark ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro'}
          >
            <span className="theme-toggle-icon">
              {dark
                ? (
                  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="16" height="16">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v2m0 14v2m9-9h-2M5 12H3m14.36-6.36l-1.42 1.42M7.06 17.65l-1.42 1.42m12.72 0l-1.42-1.42M7.06 6.36l-1.42-1.42M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                  </svg>
                )
                : (
                  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="16" height="16">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                  </svg>
                )}
            </span>
            <span>{dark ? 'Tema claro' : 'Tema oscuro'}</span>
          </button>
        </div>

        <div className="privacy-box">
          <svg className="privacy-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
          <p className="privacy-title">Privacidad por diseño</p>
          <p className="privacy-text">Los rostros se anonimizan y el video original se elimina al terminar. No se generan datos biométricos.</p>
        </div>
      </aside>

      <main className="main-content">
        <section className="dashboard-header">
          <div>
            <p className="eyebrow">{viewContent[0]}</p>
            <h1>{viewContent[1]}</h1>
            <p className="dashboard-subtitle">{viewContent[2]}</p>
          </div>
        
        </section>

        {activeView === 'overview' && <>
        <header className="topbar">
          <div className="kpi-card">
            <span className="kpi-icon kpi-icon-blue">v</span>
            <div className="kpi-copy">
              <div className="kpi-title">Visitantes totales</div>
              <div className="kpi-value">{visitors}</div>
              <span className="kpi-caption">Personas identificadas</span>
            </div>
          </div>
          <div className="kpi-card">
            <span className="kpi-icon kpi-icon-violet">t</span>
            <div className="kpi-copy">
              <div className="kpi-title">Tomas detectadas</div>
              <div className="kpi-value">{pickups}</div>
              <span className="kpi-caption">Productos retirados</span>
            </div>
          </div>
          <div className="kpi-card">
            <span className="kpi-icon kpi-icon-green">ti</span>
            <div className="kpi-copy">
              <div className="kpi-title">Tasa de interacción</div>
              <div className="kpi-value text-accent">{interactionRate}%</div>
              <span className="kpi-caption">Tomas por visitante</span>
            </div>
          </div>
          <div className="kpi-card">
            <span className="kpi-icon kpi-icon-orange">td</span>
            <div className="kpi-copy">
              <div className="kpi-title">Tasa de devolución</div>
              <div className="kpi-value">{rejectionRate}%</div>
              <span className="kpi-caption">Productos devueltos</span>
            </div>
          </div>
        </header>

        <form className="video-upload" onSubmit={handleUpload}>
          <div className="upload-heading">
            <span className="upload-icon">
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M7 16a4 4 0 01-.9-7.9A5 5 0 0115.8 6H16a5 5 0 011 9.9M12 12V4m0 0L9 7m3-3 3 3" />
              </svg>
            </span>
            <div>
              <strong>Analizar un nuevo video</strong>
              <p>Selecciona una grabación de hasta 500 MB.</p>
            </div>
          </div>
          <div className="video-upload-inner">
            <label className="video-upload-field">
              <input
                type="file"
                accept="video/*,.mp4,.avi,.mov,.mkv,.webm"
                onChange={(e) => {
                  const archivo = e.target.files?.[0] || null;
                  if (archivo && archivo.size > 500 * 1024 * 1024) {
                    setSelectedFile(null);
                    setUploadMsg('El video supera el límite permitido de 500 MB.');
                    e.target.value = '';
                    return;
                  }
                  setSelectedFile(archivo);
                  setAnalysisProgress(0);
                  setUploadMsg('');
                }}
              />
              <span className={`upload-picker${selectedFile ? ' has-file' : ''}`}>
                {selectedFile ? selectedFile.name : 'Seleccionar archivo de video'}
              </span>
            </label>
            <button type="submit" disabled={uploading || !selectedFile}>
              {uploading ? 'Analizando…' : 'Iniciar análisis'}
            </button>
          </div>
          {uploadMsg && <p className="video-upload-msg">{uploadMsg}</p>}
          {uploading && (
            <div className="analysis-progress-wrap">
              <div className="analysis-progress-copy">
                <span>{analysisProgress < 25 ? 'Preparando el video' : analysisProgress < 80 ? 'Detectando personas e interacciones' : 'Generando métricas y evidencias'}</span>
                <strong>{analysisProgress}%</strong>
              </div>
              <div
                className="analysis-progress"
                role="progressbar"
                aria-label="Progreso del análisis"
                aria-valuemin="0"
                aria-valuemax="100"
                aria-valuenow={analysisProgress}
              >
                <span style={{ width: `${analysisProgress}%` }} />
              </div>
            </div>
          )}
          {demoMode && (
            <p className="demo-notice">
              Mostrando datos de ejemplo: el backend no tiene métricas previas.
            </p>
          )}
        </form>

        <div className="view-container">
          <div className="live-stream-card">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Monitoreo visual</p>
                <h2>Visión de las góndolas</h2>
              </div>
              <div className="section-actions">
                <span className="live-badge"><span /> Pipeline YOLO</span>
                <button type="button" className="expand-button" onClick={() => openFullscreen(liveStreamRef)} title="Ampliar monitoreo">⛶ <span>Ampliar</span></button>
              </div>
            </div>
            <div className="live-stream-box" ref={liveStreamRef}>
              {vision.frames.length ? (
                <>
                  <img
                    className="vision-video"
                    src={`/vision-frames/${vision.frames[visionIdx] || ''}?v=${videoTick}`}
                    alt="Visión de las góndolas (pipeline YOLO)"
                  />
                  <div className="vision-controls">
                    <button type="button"
                            onClick={() => setVisionPlay((p) => !p)}>
                      {visionPlay ? '⏸ Pausa' : '▶ Reproducir'}
                    </button>
                    <span>
                      Fotograma {visionIdx + 1} / {vision.frames.length}
                    </span>
                    <button type="button" onClick={() => setVisionIdx(0)}>
                      Reiniciar
                    </button>
                  </div>
                </>
              ) : (
                <p className="vision-fallback">
                  La visión de las góndolas se generará al ejecutar el análisis
                  (sube un video o usa los datos existentes).
                </p>
              )}
              <p className="live-stream-msg">
                Pipeline YOLO: zonas, mano/agarro y personas detectadas
                fotograma a fotograma. Rostros pixelados por privacidad.
              </p>
            </div>
          </div>
        </div>
        </>}

        {activeView === 'spatial' && (
          <div className="spatial-layout">
            <div className="chart-column">
              <div className="section-heading compact">
                <div>
                  <p className="eyebrow">Distribución espacial</p>
                  <h2>Mapa de calor</h2>
                </div>
                <div className="section-actions">
                  <span className="heat-legend"><i /> Mayor actividad</span>
                  <button type="button" className="expand-button" onClick={() => openFullscreen(containerRef)} title="Ampliar mapa">⛶ <span>Ampliar</span></button>
                </div>
              </div>
              <div className="heatmap-box">
                <div className="heatmap-container" ref={containerRef}>
                  <Suspense fallback={<div className="habbo-floor" />}>
                    <HabboFloor onAisles={setAisles} onGondolas={setGondolas} config={LAYOUT_DEFAULT} />
                  </Suspense>
                  <canvas ref={canvasRef} className="heatmap-canvas" />

                  {zoneData.map((zone) => {
                    // Zona sin area conocido (id no mapeado o fuera de layout):
                    // no se pinta overlay 3D, para que un div a pantalla completa
                    // no tape los hovers del plano. Sigue visible en el panel.
                    if (!zone.area) return null;
                    const view = zoneView(zone);
                    const isActive = activeZone?.title === zone.id;

                    return (
                      <div
                        key={zone.id}
                        className={`interactive-zone ${zone.area}${isActive ? ' is-active' : ''}`}
                        style={zoneRect(zone.area)}
                        onMouseEnter={() => setActiveZone(view)}
                        onMouseLeave={() => setActiveZone(null)}
                      />
                    );
                  })}
                </div>
              </div>
            </div>

            <aside className="zones-panel">
              <div className="section-heading compact">
                <div>
                  <p className="eyebrow">Rendimiento</p>
                  <h2>Análisis de zonas</h2>
                </div>
              </div>

              {planograma && (
                <div className="zone-recommendation agente-planograma">
                  <span className="recommendation-label">✦ Recomendación del agente</span>
                  <p>{planograma}</p>
                </div>
              )}

              <div className="zones-list">
                {zoneData.map((zone) => {
                  const view = zoneView(zone);
                  const isActive = activeZone?.title === zone.id;
                  return (
                    <div
                      key={zone.id}
                      className={`zone-row ${isActive ? 'is-active' : ''}`}
                      onMouseEnter={() => setActiveZone(view)}
                      onMouseLeave={() => setActiveZone(null)}
                    >
                      <div className="zone-row-head">
                        <span className="zone-row-title">{zone.id}</span>
                        <span className={`status-indicator indicator-${view.tono}`}>
                          {view.etiqueta}
                        </span>
                      </div>
                      <div className="zone-row-stats">
                        <div className="zone-stat"><span>Entradas a la zona</span><strong>{zone.visits}</strong></div>
                        <div className="zone-stat"><span>Interacción</span><strong>{zone.pick_ups}</strong></div>
                        <div className="zone-stat"><span>Devolución</span><strong>{view.rejection}</strong></div>
                        <div className="zone-stat"><span>Permanencia</span><strong>{Number.isFinite(zone.dwell) ? `${zone.dwell.toFixed(1)} s` : '0.0 s'}</strong></div>
                        <div className="zone-stat"><span>Presencia</span><strong>{zone.presencia}</strong></div>
                      </div>

                      {isActive && (
                        <div className="zone-recommendation">
                          <strong>Agente</strong>
                          {sugerenciaZona(zone)}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </aside>
          </div>
        )}

        {activeView === 'evidence' && (
          <section className="evidence-view">
            <div className="evidence-summary">
              <div>
                <span>Eventos documentados</span>
                <strong>{evidenceCards.length}</strong>
              </div>
              <div>
                <span>Tomas</span>
                <strong>{evidenceCards.filter((item) => item.tipo === 'Producto Adquirido').length}</strong>
              </div>
              <div>
                <span>Devoluciones</span>
                <strong>{evidenceCards.filter((item) => item.tipo === 'Devolver el producto').length}</strong>
              </div>
            </div>

            {evidenceCards.length ? (
              <div className="evidence-grid">
                {evidenceCards.map((evidence, index) => {
                  const isReturn = evidence.tipo === 'Devolver el producto';
                  return (
                    <article className="evidence-card" key={`${evidence.idPersona}-${evidence.frame}-${evidence.tipo}-${index}`}>
                      <div className="evidence-image-wrap">
                        {evidence.image ? (
                          <img
                            src={`/vision-frames/${evidence.image}?v=${videoTick}`}
                            alt={`${evidence.tipo} detectado en el segundo ${evidence.segundo}`}
                          />
                        ) : (
                          <div className="evidence-image-empty">Fotograma no disponible</div>
                        )}
                        <span className={`evidence-type${isReturn ? ' is-return' : ''}`}>
                          {isReturn ? 'Devolución' : 'Toma de producto'}
                        </span>
                      </div>
                      <div className="evidence-body">
                        <div className="evidence-title-row">
                          <div>
                            <p className="eyebrow">Evidencia #{index + 1}</p>
                            <h2>{conNombresVisibles(evidence.zona || 'Zona sin identificar')}</h2>
                          </div>
                          <span className="evidence-validation"><i /> Detección temporal</span>
                        </div>
                        <dl className="evidence-metadata">
                          <div><dt>Persona</dt><dd>ID {evidence.idPersona}</dd></div>
                          <div><dt>Segundo</dt><dd>{Number(evidence.segundo || 0).toFixed(2)} s</dd></div>
                          <div><dt>Fotograma</dt><dd>{evidence.frame}</dd></div>
                          <div><dt>Evento</dt><dd>{isReturn ? 'Producto devuelto' : 'Producto retirado'}</dd></div>
                        </dl>
                        {evidence.nearestDistance > 0 && Number.isFinite(evidence.nearestDistance) && (
                          <p className="evidence-note">Se muestra el fotograma guardado más cercano al evento.</p>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="evidence-empty">
                <span>◎</span>
                <h2>Aún no hay interacciones documentadas</h2>
                <p>Analiza un video con tomas o devoluciones para generar las evidencias.</p>
                <button type="button" onClick={() => changeView('overview')}>Ir al análisis principal</button>
              </div>
            )}
          </section>
        )}

        {activeView === 'report' && (
          <div className="report-view">
            <div className="report-actions">
              <div>
                <strong>Informe listo para exportar</strong>
                <p>En la ventana de impresión selecciona “Guardar como PDF”.</p>
              </div>
              <button type="button" onClick={() => window.print()}>
                <span>⇩</span> Exportar informe PDF
              </button>
            </div>

            <article className="report-shell">
              <header className="report-header">
                <div className="report-brand">
                  <span>ϟ</span>
                  <div><strong>Alphanode</strong><small>Retail Intelligence</small></div>
                </div>
                <div className="report-date">
                  <em>Reporte confidencial</em>
                  <span>Fecha del análisis</span>
                  <strong>{analysisMeta.generadoEn ? new Date(analysisMeta.generadoEn).toLocaleString('es-CO') : 'Datos de demostración'}</strong>
                </div>
              </header>

              <section className="report-title">
                <p>Informe ejecutivo</p>
                <h2>Análisis de comportamiento en góndolas</h2>
                <span>Resultados obtenidos mediante visión artificial y procesamiento temporal de eventos.</span>
                {analysisMeta.videoInfo && (
                  <div className="report-technical-meta">
                    <span>Resolución {analysisMeta.videoInfo.ancho || '—'} × {analysisMeta.videoInfo.alto || '—'}</span>
                    <span>{Number(analysisMeta.videoInfo.fps || 0).toFixed(1)} FPS</span>
                    <span>Pipeline YOLO</span>
                  </div>
                )}
              </section>

              <section className="report-kpis">
                <div className="report-kpi-purple"><span>Visitantes únicos</span><strong>{visitors}</strong><small>Personas identificadas</small></div>
                <div className="report-kpi-blue"><span>Tomas detectadas</span><strong>{pickups}</strong><small>Productos retirados</small></div>
                <div className="report-kpi-green"><span>Tasa de interacción</span><strong>{interactionRate}%</strong><small>Tomas por visitante</small></div>
                <div className="report-kpi-orange"><span>Tasa de devolución</span><strong>{rejectionRate}%</strong><small>Productos devueltos</small></div>
              </section>

              <section className="report-section">
                <div className="report-section-title"><span>01</span><h3>Resumen ejecutivo</h3></div>
                <div className="executive-findings report-findings">
                  <article>
                    <span className="finding-icon finding-traffic">↗</span>
                    <div><small>Mayor tráfico</small><strong>{executiveSummary.busiest?.id || 'Sin actividad'}</strong><p>{executiveSummary.busiest?.visits || 0} entradas registradas</p></div>
                  </article>
                  <article>
                    <span className="finding-icon finding-pickup">◎</span>
                    <div><small>Mayor interacción</small><strong>{executiveSummary.mostInteractive?.id || 'Sin tomas detectadas'}</strong><p>{executiveSummary.mostInteractive?.pick_ups || 0} productos retirados</p></div>
                  </article>
                  <article>
                    <span className="finding-icon finding-result">✓</span>
                    <div><small>Resultado</small><strong>{pickups} tomas · {executiveSummary.returns} devoluciones</strong><p>{visitors} visitantes analizados</p></div>
                  </article>
                </div>
                <div className="executive-recommendation report-recommendation">
                  <span>Recomendación comercial</span><p>{planograma}</p>
                </div>
              </section>

              <section className="report-section">
                <div className="report-section-title"><span>02</span><h3>Rendimiento por zona</h3></div>
                <div className="report-table-wrap">
                  <table className="report-table">
                    <thead><tr><th>Zona</th><th>Entradas</th><th>Interacciones</th><th>Devoluciones</th><th>Permanencia</th><th>Clasificación</th></tr></thead>
                    <tbody>
                      {zoneData.map((zone) => {
                        const view = zoneView(zone);
                        return <tr key={zone.id}><td>{zone.id}</td><td>{zone.visits}</td><td>{zone.pick_ups}</td><td>{view.rejection}</td><td>{Number.isFinite(zone.dwell) ? `${zone.dwell.toFixed(1)} s` : '0.0 s'}</td><td>{view.etiqueta}</td></tr>;
                      })}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="report-section">
                <div className="report-section-title"><span>03</span><h3>Registro de interacciones</h3></div>
                {evidenceCards.length ? (
                  <div className="report-evidence-grid">
                    {evidenceCards.map((evidence, index) => (
                      <article key={`report-${evidence.idPersona}-${evidence.frame}-${index}`}>
                        <div className="report-evidence-image">
                          {evidence.image
                            ? <img src={`/vision-frames/${evidence.image}?v=${videoTick}`} alt={`Evidencia ${index + 1}`} />
                            : <span>Sin captura</span>}
                          <b>{String(index + 1).padStart(2, '0')}</b>
                        </div>
                        <div className="report-evidence-copy">
                          <span>{evidence.tipo === 'Devolver el producto' ? 'Devolución' : 'Toma de producto'}</span>
                          <strong>{conNombresVisibles(evidence.zona || 'Zona sin identificar')}</strong>
                          <p>Persona ID {evidence.idPersona} · {Number(evidence.segundo || 0).toFixed(2)} s</p>
                          <small>Fotograma {evidence.frame} · Detección temporal</small>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : <p className="report-no-events">No se registraron tomas ni devoluciones en este análisis.</p>}
              </section>

              <footer className="report-footer">
                <p><strong>Privacidad por diseño.</strong> Los rostros se anonimizan y no se generan datos biométricos.</p>
                <span>Alphanode · Reporte de analítica retail</span>
              </footer>
            </article>
          </div>
        )}

        <footer className="app-footer">
          <span>Alphanode Retail Intelligence</span>
          <span>Analítica responsable · Privacidad por diseño</span>
        </footer>
      </main>
    </div>
  );
}
