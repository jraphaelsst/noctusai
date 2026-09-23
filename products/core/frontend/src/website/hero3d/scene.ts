/**
 * The procedural "constellation" three.js scene (rebrand direction A —
 * bootstrap, contract D7). ONLY ever reached via a dynamic `import()` from
 * `HeroScene.tsx` — never imported eagerly, never imported from the app
 * bundle, never imported from `entry-server.tsx` (SSR never touches WebGL).
 *
 * Reads `--scene-bg` / `--scene-accent` / `--scene-fog` off the given root
 * element so a theme switch recolours the live scene without a reload
 * (06 §Theming). Nodes = the curated products; the caller supplies labels.
 */
import * as THREE from "three";

export interface SceneNode {
  slug: string;
  label: string;
  position: [number, number, number];
}

export interface SceneHandle {
  dispose: () => void;
  pause: () => void;
  resume: () => void;
  setDpr: (dpr: number) => void;
  /** Screen-space [x, y] in 0..1 for each node, updated every frame. */
  onProjectedPositions: (cb: (positions: Record<string, { x: number; y: number; visible: boolean }>) => void) => void;
}

const LINKS: [number, number][] = [[0, 1], [1, 2], [2, 3], [1, 3], [0, 3]];

/**
 * Fixed world position of the cluster's own pivot (2026-09-23 review fix).
 * `n.position` on each `SceneNode` is now a LOCAL offset from this anchor,
 * not an absolute world coordinate — the anchor itself never rotates, only
 * an inner `spin` group nested inside it does. Rotating the OLD flat
 * `group` (which held nodes already offset to world X≈+3.5) around the
 * WORLD origin made the whole "right-biased" cluster sweep in a wide arc
 * across the entire frame every ~4s, periodically landing directly on the
 * H1 — the bug the tech-lead's screenshots caught. With the anchor/spin
 * split, the cluster's SCREEN position stays fixed (wherever this world
 * point projects to); only the nodes orbit locally, in place, around it.
 */
const CLUSTER_ANCHOR: [number, number, number] = [5.6, -0.6, -1];

function readCssVar(el: Element, name: string, fallback: string): string {
  const value = getComputedStyle(el).getPropertyValue(name).trim();
  return value || fallback;
}

export function createConstellationScene(
  container: HTMLElement,
  nodes: SceneNode[],
  themeRootEl: Element,
): SceneHandle {
  const width = container.clientWidth || 1;
  const height = container.clientHeight || 1;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
  camera.position.set(0, 0, 12);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(width, height);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  container.appendChild(renderer.domElement);

  const accentColor = new THREE.Color(readCssVar(themeRootEl, "--scene-accent", "#8b5cf6"));
  const fogColor = new THREE.Color(readCssVar(themeRootEl, "--scene-bg", "#07080f"));
  scene.fog = new THREE.FogExp2(fogColor, 0.03);

  // `anchor` holds a FIXED world position (never rotated) — the cluster's
  // on-screen location. `spin` is nested inside it and is the ONLY thing
  // the tick loop rotates, so nodes orbit in place around the anchor
  // instead of sweeping across the whole scene.
  const anchor = new THREE.Group();
  anchor.position.set(...CLUSTER_ANCHOR);
  scene.add(anchor);
  const group = new THREE.Group();
  anchor.add(group);

  const nodeMeshes: THREE.Mesh[] = [];
  // Smaller nodes (2026-09-23 review): 0.18 world radius read as large,
  // heavy-looking dots (~26px at 1440px) that competed visually with the
  // now right-biased text column's neighbourhood.
  const sphereGeo = new THREE.SphereGeometry(0.12, 16, 16);
  nodes.forEach((n) => {
    const mat = new THREE.MeshBasicMaterial({ color: accentColor });
    const mesh = new THREE.Mesh(sphereGeo, mat);
    mesh.position.set(...n.position);
    group.add(mesh);
    nodeMeshes.push(mesh);
  });

  const linePositions: number[] = [];
  LINKS.forEach(([a, b]) => {
    if (!nodes[a] || !nodes[b]) return;
    linePositions.push(...nodes[a].position, ...nodes[b].position);
  });
  const lineGeo = new THREE.BufferGeometry();
  lineGeo.setAttribute("position", new THREE.Float32BufferAttribute(linePositions, 3));
  const lineMat = new THREE.LineBasicMaterial({ color: accentColor, transparent: true, opacity: 0.35 });
  const lines = new THREE.LineSegments(lineGeo, lineMat);
  group.add(lines);

  let raf: number | null = null;
  let paused = false;
  let pointerX = 0;
  let pointerY = 0;
  let projectedCb: ((p: Record<string, { x: number; y: number; visible: boolean }>) => void) | null = null;

  function onPointerMove(e: PointerEvent) {
    const rect = container.getBoundingClientRect();
    pointerX = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    pointerY = ((e.clientY - rect.top) / rect.height) * 2 - 1;
  }
  container.addEventListener("pointermove", onPointerMove);

  const worldPos = new THREE.Vector3();
  function projectPositions() {
    if (!projectedCb) return;
    const out: Record<string, { x: number; y: number; visible: boolean }> = {};
    nodes.forEach((n, i) => {
      const mesh = nodeMeshes[i];
      // `mesh.position` is LOCAL to `group` (nested in the fixed `anchor`)
      // — must resolve the WORLD position before projecting, or every HUD
      // label lands at the pre-anchor (world-origin-relative) coordinate.
      const vector = mesh.getWorldPosition(worldPos).project(camera);
      out[n.slug] = {
        x: (vector.x * 0.5 + 0.5) * width,
        y: (-vector.y * 0.5 + 0.5) * height,
        visible: vector.z < 1,
      };
    });
    projectedCb(out);
  }

  function tick() {
    if (!paused) {
      group.rotation.y += 0.0015;
      camera.position.x += (pointerX * 1.5 - camera.position.x) * 0.02;
      camera.position.y += (-pointerY * 1.0 - camera.position.y) * 0.02;
      camera.lookAt(0, 0, 0);
      renderer.render(scene, camera);
      projectPositions();
    }
    raf = requestAnimationFrame(tick);
  }
  raf = requestAnimationFrame(tick);

  return {
    dispose() {
      if (raf) cancelAnimationFrame(raf);
      container.removeEventListener("pointermove", onPointerMove);
      renderer.dispose();
      sphereGeo.dispose();
      lineGeo.dispose();
      nodeMeshes.forEach((m) => (m.material as THREE.Material).dispose());
      lineMat.dispose();
      if (renderer.domElement.parentElement === container) {
        container.removeChild(renderer.domElement);
      }
    },
    pause() {
      paused = true;
    },
    resume() {
      paused = false;
    },
    setDpr(dpr: number) {
      renderer.setPixelRatio(Math.min(dpr, 2));
    },
    onProjectedPositions(cb) {
      projectedCb = cb;
    },
  };
}
