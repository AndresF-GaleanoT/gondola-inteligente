import { useEffect, useRef, useState } from 'react';

const STORAGE_KEY = 'gondola-accessibility-v1';

const DEFAULTS = {
  fontScale: 100,
  highContrast: false,
  grayscale: false,
  readableFont: false,
  reduceMotion: false,
  largeCursor: false,
  highlightControls: false,
};

function Icon({ name }) {
  const paths = {
    accessibility: <><circle cx="12" cy="4" r="2"/><path d="M5 8h14M12 6v6m0 0-4 8m4-8 4 8"/></>,
    close: <path d="m6 6 12 12M18 6 6 18"/>,
    volume: <><path d="M11 5 6 9H3v6h3l5 4V5Z"/><path d="M15 9a4 4 0 0 1 0 6m3-9a8 8 0 0 1 0 12"/></>,
    reset: <><path d="M4 7v5h5"/><path d="M5.5 17a8 8 0 1 0-.8-8.7L4 12"/></>,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>;
}

function Toggle({ checked, onChange, title, description }) {
  return (
    <label className="a11y-setting">
      <span><b>{title}</b><small>{description}</small></span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <i aria-hidden="true" />
    </label>
  );
}

export default function AccessibilityPanel() {
  const [panelAbierto, setPanelAbierto] = useState(false);
  const [leyendo, setLeyendo] = useState(false);
  const [preferencias, setPreferencias] = useState(() => {
    try {
      return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') };
    } catch {
      return DEFAULTS;
    }
  });
  const botonAperturaRef = useRef(null);
  const panelRef = useRef(null);

  useEffect(() => {
    const raiz = document.documentElement;
    raiz.style.setProperty('--a11y-font-scale', String(preferencias.fontScale / 100));
    Object.entries(preferencias).forEach(([clave, valor]) => {
      if (clave !== 'fontScale') raiz.dataset[clave] = valor ? 'true' : 'false';
    });
    localStorage.setItem(STORAGE_KEY, JSON.stringify(preferencias));
  }, [preferencias]);

  useEffect(() => {
    if (!panelAbierto) return undefined;
    const panel = panelRef.current;
    const elementosEnfocables = panel?.querySelectorAll('button, input, [tabindex]:not([tabindex="-1"])');
    elementosEnfocables?.[0]?.focus();

    const alPresionarTecla = (evento) => {
      if (evento.key === 'Escape') {
        setPanelAbierto(false);
        botonAperturaRef.current?.focus();
        return;
      }
      if (evento.key !== 'Tab' || !elementosEnfocables?.length) return;
      const primero = elementosEnfocables[0];
      const ultimo = elementosEnfocables[elementosEnfocables.length - 1];
      if (evento.shiftKey && document.activeElement === primero) {
        evento.preventDefault();
        ultimo.focus();
      } else if (!evento.shiftKey && document.activeElement === ultimo) {
        evento.preventDefault();
        primero.focus();
      }
    };
    document.addEventListener('keydown', alPresionarTecla);
    return () => document.removeEventListener('keydown', alPresionarTecla);
  }, [panelAbierto]);

  useEffect(() => () => window.speechSynthesis?.cancel(), []);

  useEffect(() => {
    if (!panelAbierto) return undefined;
    const overflowPrevio = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = overflowPrevio; };
  }, [panelAbierto]);

  const actualizarPreferencia = (clave, valor) => setPreferencias((actuales) => ({ ...actuales, [clave]: valor }));

  const cerrarPanel = () => {
    setPanelAbierto(false);
    window.setTimeout(() => botonAperturaRef.current?.focus(), 0);
  };

  const restablecerPreferencias = () => {
    setPreferencias(DEFAULTS);
    window.speechSynthesis?.cancel();
    setLeyendo(false);
  };

  const leerVistaActual = () => {
    if (!('speechSynthesis' in window)) return;
    if (leyendo) {
      window.speechSynthesis.cancel();
      setLeyendo(false);
      return;
    }
    const paginaActiva = document.querySelector('main .page.active');
    const texto = paginaActiva?.innerText?.replace(/\s+/g, ' ').trim();
    if (!texto) return;
    const enunciado = new SpeechSynthesisUtterance(texto);
    enunciado.lang = 'es-CO';
    enunciado.rate = 0.95;
    enunciado.onend = () => setLeyendo(false);
    enunciado.onerror = () => setLeyendo(false);
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(enunciado);
    setLeyendo(true);
  };

  return (
    <>
      <button
        ref={botonAperturaRef}
        type="button"
        className="a11y-trigger"
        aria-label="Abrir herramientas de accesibilidad"
        aria-expanded={panelAbierto}
        aria-controls="accessibility-panel"
        onClick={() => setPanelAbierto(true)}
      >
        <Icon name="accessibility" />
        <span>Accesibilidad</span>
      </button>

      {panelAbierto && (
        <div className="a11y-layer">
          <button className="a11y-backdrop" type="button" aria-label="Cerrar herramientas de accesibilidad" onClick={cerrarPanel} />
          <aside
            ref={panelRef}
            id="accessibility-panel"
            className="a11y-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="a11y-title"
          >
            <header className="a11y-panel-head">
              <div className="a11y-panel-icon"><Icon name="accessibility" /></div>
              <div>
                <p>Preferencias de visualización</p>
                <h2 id="a11y-title">Accesibilidad</h2>
              </div>
              <button type="button" className="a11y-close" aria-label="Cerrar panel" onClick={cerrarPanel}><Icon name="close" /></button>
            </header>

            <div className="a11y-panel-body">
              <section className="a11y-group" aria-labelledby="text-settings">
                <h3 id="text-settings">Lectura y texto</h3>
                <div className="a11y-font-control">
                  <span><b>Tamaño del texto</b><small>Ajusta toda la interfaz</small></span>
                  <div role="group" aria-label="Tamaño del texto">
                    {[100, 112, 125].map((tamano) => (
                      <button key={tamano} type="button" className={preferencias.fontScale === tamano ? 'active' : ''} aria-pressed={preferencias.fontScale === tamano} onClick={() => actualizarPreferencia('fontScale', tamano)}>{tamano}%</button>
                    ))}
                  </div>
                </div>
                <Toggle checked={preferencias.readableFont} onChange={(valor) => actualizarPreferencia('readableFont', valor)} title="Tipografía legible" description="Reduce estilos decorativos" />
                <button type="button" className={`a11y-read${leyendo ? ' active' : ''}`} onClick={leerVistaActual} aria-pressed={leyendo}>
                  <Icon name="volume" />
                  <span><b>{leyendo ? 'Detener lectura' : 'Leer esta sección'}</b><small>Usa la voz disponible en el dispositivo</small></span>
                </button>
              </section>

              <section className="a11y-group" aria-labelledby="visual-settings">
                <h3 id="visual-settings">Visibilidad e interacción</h3>
                <Toggle checked={preferencias.highContrast} onChange={(valor) => actualizarPreferencia('highContrast', valor)} title="Alto contraste" description="Refuerza texto, bordes y fondos" />
                <Toggle checked={preferencias.grayscale} onChange={(valor) => actualizarPreferencia('grayscale', valor)} title="Escala de grises" description="Elimina distracciones de color" />
                <Toggle checked={preferencias.highlightControls} onChange={(valor) => actualizarPreferencia('highlightControls', valor)} title="Resaltar controles" description="Identifica botones y enlaces" />
                <Toggle checked={preferencias.largeCursor} onChange={(valor) => actualizarPreferencia('largeCursor', valor)} title="Cursor grande" description="Facilita apuntar y seleccionar" />
                <Toggle checked={preferencias.reduceMotion} onChange={(valor) => actualizarPreferencia('reduceMotion', valor)} title="Reducir movimiento" description="Desactiva animaciones y transiciones" />
              </section>

              <div className="a11y-help" role="note">
                <b>Compatible con teclado</b>
                <p>Use Tab para recorrer los controles, Enter para activarlos y Esc para cerrar este panel. La aplicación no depende de sonidos: los estados y alertas también aparecen en pantalla.</p>
              </div>
            </div>

            <footer className="a11y-panel-foot">
              <button type="button" onClick={restablecerPreferencias}><Icon name="reset" />Restablecer preferencias</button>
              <span>Los ajustes se guardan en este dispositivo.</span>
            </footer>
          </aside>
        </div>
      )}
    </>
  );
}
