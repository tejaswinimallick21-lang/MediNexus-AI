import { useEffect, useRef } from "react";

/**
 * Rotating 3D "care network" globe drawn on canvas (Fibonacci sphere + perspective projection).
 * No 3D library. Pauses when off-screen, renders a single still frame for reduced-motion users.
 */
export function NeuralGlobe({ size = 420, className }: { size?: number; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const N = 220;
    const golden = Math.PI * (3 - Math.sqrt(5));
    const points = Array.from({ length: N }, (_, i) => {
      const y = 1 - (i / (N - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const t = golden * i;
      return { x: Math.cos(t) * r, y, z: Math.sin(t) * r, pulse: Math.random() * Math.PI * 2 };
    });
    // Precompute near-neighbour links once (sphere-local, so they rotate with the globe)
    const links: [number, number][] = [];
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        const dx = points[i].x - points[j].x, dy = points[i].y - points[j].y, dz = points[i].z - points[j].z;
        if (dx * dx + dy * dy + dz * dz < 0.045) links.push([i, j]);
      }
    }

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const R = size * 0.38, cx = size / 2, cy = size / 2, tilt = 0.35;
    let angle = 0, raf = 0, visible = true, last = performance.now();

    const draw = (time: number) => {
      ctx.clearRect(0, 0, size, size);
      const cosA = Math.cos(angle), sinA = Math.sin(angle), cosT = Math.cos(tilt), sinT = Math.sin(tilt);
      const proj = points.map((p) => {
        const x1 = p.x * cosA - p.z * sinA, z1 = p.x * sinA + p.z * cosA;
        const y2 = p.y * cosT - z1 * sinT, z2 = p.y * sinT + z1 * cosT;
        const persp = 1.6 / (2.6 - z2);
        return { sx: cx + x1 * R * persp, sy: cy + y2 * R * persp, depth: (z2 + 1) / 2, pulse: p.pulse };
      });

      // Halo
      const halo = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 1.25);
      halo.addColorStop(0, "rgba(20,184,166,0.18)");
      halo.addColorStop(1, "rgba(20,184,166,0)");
      ctx.fillStyle = halo;
      ctx.fillRect(0, 0, size, size);

      ctx.lineWidth = 0.7;
      for (const [a, b] of links) {
        const d = (proj[a].depth + proj[b].depth) / 2;
        ctx.strokeStyle = `rgba(56,189,248,${0.05 + d * 0.28})`;
        ctx.beginPath();
        ctx.moveTo(proj[a].sx, proj[a].sy);
        ctx.lineTo(proj[b].sx, proj[b].sy);
        ctx.stroke();
      }
      for (const p of proj) {
        const glow = 0.5 + 0.5 * Math.sin(time / 600 + p.pulse);
        const r = 0.8 + p.depth * 2.1;
        ctx.fillStyle = p.depth > 0.55 ? `rgba(45,212,191,${0.35 + p.depth * 0.6})` : `rgba(129,140,248,${0.2 + p.depth * 0.5})`;
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, r + (p.depth > 0.8 ? glow * 1.2 : 0), 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const loop = (time: number) => {
      const dt = Math.min(64, time - last);
      last = time;
      angle += dt * 0.00018;
      draw(time);
      if (visible) raf = requestAnimationFrame(loop);
    };

    if (reduced) {
      draw(0);
      return;
    }
    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible) {
        last = performance.now();
        raf = requestAnimationFrame(loop);
      } else cancelAnimationFrame(raf);
    });
    io.observe(canvas);
    raf = requestAnimationFrame(loop);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [size]);

  return <canvas ref={ref} className={className} style={{ width: size, height: size }} aria-hidden="true" />;
}
