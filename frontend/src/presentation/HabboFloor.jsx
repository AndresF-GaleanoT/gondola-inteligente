// ============================================================================
// PRESENTATION / HabboFloor - plano arquitectonico 3D estilo Habbo.
// Renderiza las 3 gondolas (cajas 3D) y los 2 pasillos con Three.js, con
// camara ortografica fija (top-down en angulo, como los planos de Habbo).
// ============================================================================

import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { LAYOUT_DEFAULT } from '../domain/layout';

const GONDOLAS = LAYOUT_DEFAULT.gondolas;
const PASILLOS = LAYOUT_DEFAULT.pasillos;

export default function HabboFloor({ onAisles, onGondolas, config }) {
  const mountRef = useRef(null);
  const aislesRef = useRef(onAisles);
  aislesRef.current = onAisles;
  const gondolasRef = useRef(onGondolas);
  gondolasRef.current = onGondolas;
  // Gondolas/pasillos configurables (prop `config`); si no se pasan o llegan
  // vacios, se usan los del layout por defecto (guard defensiva de arrays).
  const gondolas = Array.isArray(config?.gondolas) && config.gondolas.length
    ? config.gondolas
    : GONDOLAS;
  const pasillos = Array.isArray(config?.pasillos) && config.pasillos.length
    ? config.pasillos
    : PASILLOS;
  // Refs para que el efecto (que corre una sola vez) lea siempre la config
  // mas reciente aunque `config` cambie en renderizados posteriores.
  const gondLayoutRef = useRef(gondolas);
  gondLayoutRef.current = gondolas;
  const pasillosLayoutRef = useRef(pasillos);
  pasillosLayoutRef.current = pasillos;

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return undefined;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x020a06);

    // Camara ortografica top-down en angulo (estilo Habbo).
    const contW = () => mount.clientWidth || 600;
    const contH = () => mount.clientHeight || 400;
    // Frustum amplio (±9): incluye piso completo (x -8..8) y las 3 gondolas
    // (izq y neveras estan en x=±6 con 3.2 de ancho) sin que se corten.
    const frustum = 9;
    const camera = new THREE.OrthographicCamera(
      -frustum, frustum, frustum * (contH() / contW()), -frustum * (contH() / contW()),
      0.1, 100,
    );
    camera.position.set(0, 14, 0);
    camera.up.set(0, 0, 1); // up en +z: vista cenital "de mapa" (evita matriz NaN al mirar hacia abajo)
    camera.lookAt(0, 0, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(contW(), contH());
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    mount.appendChild(renderer.domElement);

    // Luces
    const ambient = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambient);
    const dir = new THREE.DirectionalLight(0xffffff, 1.1);
    dir.position.set(2, 15, 2);
    dir.castShadow = true;
    dir.shadow.mapSize.set(1024, 1024);
    dir.shadow.camera.left = -10;
    dir.shadow.camera.right = 10;
    dir.shadow.camera.top = 10;
    dir.shadow.camera.bottom = -10;
    scene.add(dir);

    // Suelo tipo Habbo (cuadricula de baldosas como pasillos/gondola area).
    const suelo = new THREE.Mesh(
      new THREE.BoxGeometry(16, 0.1, 10),
      new THREE.MeshStandardMaterial({ color: 0x0b1711 }),
    );
    suelo.position.y = -0.05;
    suelo.receiveShadow = true;
    scene.add(suelo);

    // Lineas de cuadricula (baldosas de pasillo).
    const grid = new THREE.GridHelper(16, 16, 0x1f5c3c, 0x163826);
    grid.position.y = 0.02;
    scene.add(grid);

    // Dos calles/pasillos marcados como sendas del suelo.
    const mat_pasillo = new THREE.MeshStandardMaterial({ color: 0x15241a, roughness: 0.9 });
    const pasillo1 = new THREE.Mesh(new THREE.PlaneGeometry(2.0, 8.6), mat_pasillo);
    pasillo1.rotation.x = -Math.PI / 2;
    pasillo1.position.set(-3.3, 0.06, 0);
    pasillo1.receiveShadow = true;
    scene.add(pasillo1);
    const pasillo2 = new THREE.Mesh(new THREE.PlaneGeometry(2.0, 8.6), mat_pasillo);
    pasillo2.rotation.x = -Math.PI / 2;
    pasillo2.position.set(3.3, 0.06, 0);
    pasillo2.receiveShadow = true;
    scene.add(pasillo2);

    // 3 gondolas como cajas 3D.
    const cajas = gondLayoutRef.current.map((g) => {
      const geo = new THREE.BoxGeometry(g.w, g.h, g.d);
      const mat = new THREE.MeshStandardMaterial({
        color: g.color,
        roughness: 0.5,
        metalness: 0.1,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(g.x, g.h / 2, g.z);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      scene.add(mesh);

      // Etiqueta 3D: caja de texto que calza exacto sobre el ancho de la gondola.
      const txtCanvas = document.createElement('canvas');
      const tW = 1024;
      const tH = 256;
      txtCanvas.width = tW;
      txtCanvas.height = tH;
      const tctx = txtCanvas.getContext('2d');

      // Etiqueta sobria y legible, coherente con el dashboard de analitica.
      tctx.fillStyle = '#04070a';
      tctx.fillRect(0, 0, tW, tH);
      tctx.strokeStyle = '#2bff88';
      tctx.lineWidth = 8;
      tctx.strokeRect(5, 5, tW - 10, tH - 10);

      // Fuente auto-ajustada para que el texto nunca se salga de la caja.
      let fontSize = 170;
      for (; fontSize > 24; fontSize -= 2) {
        tctx.font = `bold ${fontSize}px 'JetBrains Mono', monospace`;
        if (tctx.measureText(g.id).width <= tW - 60) break;
      }
      tctx.fillStyle = '#eafff2';
      tctx.font = `bold ${fontSize}px 'JetBrains Mono', monospace`;
      tctx.textAlign = 'center';
      tctx.textBaseline = 'middle';
      tctx.fillText(g.id, tW / 2, tH / 2);

      const spTex = new THREE.CanvasTexture(txtCanvas);
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: spTex, depthTest: false }));
      // El ancho del sprite es EXACTO al ancho de la gondola; el alto mantiene
      // la proporcion del canvas (4:1) para que no se deforme el texto.
      const spW = g.w;
      const spH = spW * (tH / tW);
      sprite.scale.set(spW, spH, 1);
      sprite.position.set(g.x, g.h + 0.7, g.z);
      sprite.renderOrder = 10;
      scene.add(sprite);
      return mesh;
    });

    // Animacion: leve rotacion para dar sensacion de plano interactivo.
    // El loop se PAUSA cuando la pestana no es visible (document.hidden) para
    // no gastar GPU/CPU en una escena que nadie ve (antes giraba siempre).
    let raf = 0;
    let activo = true;
    const animar = () => {
      raf = requestAnimationFrame(animar);
      const t = Date.now() * 0.0004;
      cajas.forEach((c, i) => {
        // Un bamboleo muy suave (bob).
        c.position.y = c.geometry.parameters.height / 2 + Math.sin(t + i * 2) * 0.05;
      });
      renderer.render(scene, camera);
    };
    const detener = () => {
      activo = false;
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
    };
    const reiniciar = () => {
      if (activo) return;
      activo = true;
      animar();
    };
    const onVisibilidad = () => {
      if (document.hidden) detener();
      else reiniciar();
    };
    document.addEventListener('visibilitychange', onVisibilidad);
    animar();

    const onResize = () => {
      const w = contW();
      const h = contH();
      camera.left = -frustum;
      camera.right = frustum;
      camera.top = frustum * (h / w);
      camera.bottom = -frustum * (h / w);
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      reportarTodo();
    };
    window.addEventListener('resize', onResize);

    // Proyecta en pixeles (espacio del contenedor) el footprint 2D (footprint)
    // de un conjunto de objetos 3D (pasillos o gondolas), con la misma camara.
    const proyectarRects = (objetos) => {
      const w = contW();
      const h = contH();
      return objetos.map((o) => {
        let minX = Infinity;
        let maxX = -Infinity;
        let minY = Infinity;
        let maxY = -Infinity;
        for (const oz of [-o.d / 2, o.d / 2]) {
          for (const ox of [o.x - o.w / 2, o.x + o.w / 2]) {
            const v = new THREE.Vector3(ox, 0, oz).project(camera);
            const px = ((v.x + 1) / 2) * w;
            const py = (1 - (v.y + 1) / 2) * h;
            minX = Math.min(minX, px);
            maxX = Math.max(maxX, px);
            minY = Math.min(minY, py);
            maxY = Math.max(maxY, py);
          }
        }
        return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
      });
    };

    // Reporta a los padres (setAisles/setGondolas) SOLO cuando los rectangulos
    // proyectados cambian de verdad: evita re-renderizar todo el dashboard en
    // cada resize/animacion (antes llamaba al setState en cada onResize).
    let ultimaFirma = null;
    const reportarTodo = () => {
      const rectsAisles = proyectarRects(pasillosLayoutRef.current);
      const rectsGondolas = proyectarRects(gondLayoutRef.current);
      const firma = JSON.stringify([rectsAisles, rectsGondolas]);
      if (firma === ultimaFirma) return;
      ultimaFirma = firma;
      if (aislesRef.current) aislesRef.current(rectsAisles);
      if (gondolasRef.current) gondolasRef.current(rectsGondolas);
    };
    reportarTodo();

    return () => {
      detener();
      window.removeEventListener('resize', onResize);
      document.removeEventListener('visibilitychange', onVisibilidad);
      // Libera TODA la escena (geometrias, materiales, texturas de sprites,
      // suelo/cuadricula/luces) y fuerza la perdida del contexto WebGL; antes
      // solo se liberaban las geometrias de las cajas y en remounts (StrictMode)
      // se filtraba memoria de GPU por cada montaje.
      scene.traverse((obj) => {
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) {
          const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
          mats.forEach((mat) => {
            Object.keys(mat).forEach((clave) => {
              const v = mat[clave];
              if (v && v.isTexture) v.dispose();
            });
            mat.dispose();
          });
        }
      });
      renderer.dispose();
      renderer.forceContextLoss();
      if (renderer.domElement.parentNode) {
        renderer.domElement.parentNode.removeChild(renderer.domElement);
      }
    };
  }, []);

  return <div ref={mountRef} className="habbo-floor" />;
}
