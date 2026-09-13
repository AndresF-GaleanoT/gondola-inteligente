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
  const [open, setOpen] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [preferences, setPreferences] = useState(() => {
    try {
      return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') };
    } catch {
      return DEFAULTS;
    }
  });
  const triggerRef = useRef(null);
  const panelRef = useRef(null);

  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty('--a11y-font-scale', String(preferences.fontScale / 100));
    Object.entries(preferences).forEach(([key, value]) => {
      if (key !== 'fontScale') root.dataset[key] = value ? 'true' : 'false';
    });
    localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  }, [preferences]);

  useEffect(() => {
    if (!open) return undefined;
    const panel = panelRef.current;
    const focusable = panel?.querySelectorAll('button, input, [tabindex]:not([tabindex="-1"])');
    focusable?.[0]?.focus();

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
        return;
      }
      if (event.key !== 'Tab' || !focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open]);

  useEffect(() => () => window.speechSynthesis?.cancel(), []);

  useEffect(() => {
    if (!open) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previous; };
  }, [open]);

  const update = (key, value) => setPreferences((current) => ({ ...current, [key]: value }));

  const closePanel = () => {
    setOpen(false);
    window.setTimeout(() => triggerRef.current?.focus(), 0);
  };

  const reset = () => {
    setPreferences(DEFAULTS);
    window.speechSynthesis?.cancel();
    setSpeaking(false);
  };

  const readCurrentView = () => {
    if (!('speechSynthesis' in window)) return;
    if (speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
      return;
    }
    const activePage = document.querySelector('main .page.active');
    const text = activePage?.innerText?.replace(/\s+/g, ' ').trim();
    if (!text) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'es-CO';
    utterance.rate = 0.95;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
    setSpeaking(true);
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="a11y-trigger"
        aria-label="Abrir herramientas de accesibilidad"
        aria-expanded={open}
        aria-controls="accessibility-panel"
        onClick={() => setOpen(true)}
      >
        <Icon name="accessibility" />
        <span>Accesibilidad</span>
      </button>

      {open && (
        <div className="a11y-layer">
          <button className="a11y-backdrop" type="button" aria-label="Cerrar herramientas de accesibilidad" onClick={closePanel} />
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
              <button type="button" className="a11y-close" aria-label="Cerrar panel" onClick={closePanel}><Icon name="close" /></button>
            </header>

            <div className="a11y-panel-body">
              <section className="a11y-group" aria-labelledby="text-settings">
                <h3 id="text-settings">Lectura y texto</h3>
                <div className="a11y-font-control">
                  <span><b>Tamaño del texto</b><small>Ajusta toda la interfaz</small></span>
                  <div role="group" aria-label="Tamaño del texto">
                    {[100, 112, 125].map((size) => (
                      <button key={size} type="button" className={preferences.fontScale === size ? 'active' : ''} aria-pressed={preferences.fontScale === size} onClick={() => update('fontScale', size)}>{size}%</button>
                    ))}
                  </div>
                </div>
                <Toggle checked={preferences.readableFont} onChange={(value) => update('readableFont', value)} title="Tipografía legible" description="Reduce estilos decorativos" />
                <button type="button" className={`a11y-read${speaking ? ' active' : ''}`} onClick={readCurrentView} aria-pressed={speaking}>
                  <Icon name="volume" />
                  <span><b>{speaking ? 'Detener lectura' : 'Leer esta sección'}</b><small>Usa la voz disponible en el dispositivo</small></span>
                </button>
              </section>

              <section className="a11y-group" aria-labelledby="visual-settings">
                <h3 id="visual-settings">Visibilidad e interacción</h3>
                <Toggle checked={preferences.highContrast} onChange={(value) => update('highContrast', value)} title="Alto contraste" description="Refuerza texto, bordes y fondos" />
                <Toggle checked={preferences.grayscale} onChange={(value) => update('grayscale', value)} title="Escala de grises" description="Elimina distracciones de color" />
                <Toggle checked={preferences.highlightControls} onChange={(value) => update('highlightControls', value)} title="Resaltar controles" description="Identifica botones y enlaces" />
                <Toggle checked={preferences.largeCursor} onChange={(value) => update('largeCursor', value)} title="Cursor grande" description="Facilita apuntar y seleccionar" />
                <Toggle checked={preferences.reduceMotion} onChange={(value) => update('reduceMotion', value)} title="Reducir movimiento" description="Desactiva animaciones y transiciones" />
              </section>

              <div className="a11y-help" role="note">
                <b>Compatible con teclado</b>
                <p>Use Tab para recorrer los controles, Enter para activarlos y Esc para cerrar este panel. La aplicación no depende de sonidos: los estados y alertas también aparecen en pantalla.</p>
              </div>
            </div>

            <footer className="a11y-panel-foot">
              <button type="button" onClick={reset}><Icon name="reset" />Restablecer preferencias</button>
              <span>Los ajustes se guardan en este dispositivo.</span>
            </footer>
          </aside>
        </div>
      )}
    </>
  );
}
