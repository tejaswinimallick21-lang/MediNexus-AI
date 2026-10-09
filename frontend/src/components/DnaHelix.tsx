import { useEffect, useRef } from "react";

/**
 * Rotating 3D DNA double helix on canvas: two phosphate backbones + base-pair rungs,
 * depth-sorted with perspective, size and opacity falloff. Pauses off-screen; still frame for reduced motion.
 */
export function DnaHelix({ width = 360, height = 560, className }: { width?: number; height?: number; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    const PAIRS = 34;
    const radius = width * 0.26;
    const cx = width / 2;
    const top = height * 0.06;
    const span = height * 0.88;
    const turns = 2.6;
    const tiltX = 0.42; // lean the helix for a 3D read
    const baseColors = [
      ["#2dd4bf", "#38bdf8"],
      ["#818cf8", "#f472b6"],
    ];

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let phase = 0, raf = 0, visible = true, last = performance.now();

    type Node = { x: number; y: number; z: number; strand: 0 | 1; i: number };
    const project = (x: number, y: number, z: number) => {
      const p = 1.9 / (2.9 - z);
      return { sx: cx + x * p + (y - height / 2) * Math.sin(tiltX) * 0.25, sy: y, scale: p };
    };

    const draw = (time: number) => {
      ctx.clearRect(0, 0, width, height);
      const nodes: Node[] = [];
      for (let i = 0; i < PAIRS; i++) {
        const t = i / (PAIRS - 1);
        const a = t * turns * Math.PI * 2 + phase;
        const y = top + t * span;
        nodes.push({ x: Math.cos(a) * radius, y, z: Math.sin(a), strand: 0, i });
        nodes.push({ x: Math.cos(a + Math.PI) * radius, y, z: Math.sin(a + Math.PI), strand: 1, i });
      }

      // Backbones (draw as segmented curves so depth can modulate each segment)
      for (const strand of [0, 1] as const) {
        const pts = nodes.filter((n) => n.strand === strand);
        for (let k = 0; k < pts.length - 1; k++) {
          const a = project(pts[k].x, pts[k].y, pts[k].z), b = project(pts[k + 1].x, pts[k + 1].y, pts[k + 1].z);
          const depth = (pts[k].z + pts[k + 1].z) / 4 + 0.5;
          ctx.strokeStyle = strand === 0 ? `rgba(45,212,191,${0.18 + depth * 0.7})` : `rgba(129,140,248,${0.18 + depth * 0.7})`;
          ctx.lineWidth = 1 + depth * 2.6;
          ctx.beginPath();
          ctx.moveTo(a.sx, a.sy);
          ctx.lineTo(b.sx, b.sy);
          ctx.stroke();
        }
      }

      // Base-pair rungs, back to front
      const rungs = Array.from({ length: PAIRS }, (_, i) => [nodes[i * 2], nodes[i * 2 + 1]] as const).sort(
        (r1, r2) => r1[0].z + r1[1].z - (r2[0].z + r2[1].z),
      );
      for (const [n0, n1] of rungs) {
        const a = project(n0.x, n0.y, n0.z), b = project(n1.x, n1.y, n1.z);
        const mx = (a.sx + b.sx) / 2, my = (a.sy + b.sy) / 2;
        const [c0, c1] = baseColors[n0.i % 2];
        const depth = Math.max(n0.z, n1.z) / 2 + 0.5;
        ctx.globalAlpha = 0.25 + depth * 0.65;
        ctx.lineWidth = 2.2;
        ctx.strokeStyle = c0;
        ctx.beginPath();
        ctx.moveTo(a.sx, a.sy);
        ctx.lineTo(mx, my);
        ctx.stroke();
        ctx.strokeStyle = c1;
        ctx.beginPath();
        ctx.moveTo(mx, my);
        ctx.lineTo(b.sx, b.sy);
        ctx.stroke();

        for (const [n, pt] of [[n0, a], [n1, b]] as const) {
          const d = n.z / 2 + 0.5;
          const r = 2.5 + d * 4.5 * pt.scale;
          const pulse = 0.5 + 0.5 * Math.sin(time / 500 + n.i * 0.6 + n.strand * 2);
          const g = ctx.createRadialGradient(pt.sx, pt.sy, 0, pt.sx, pt.sy, r * 2.6);
          const hue = n.strand === 0 ? "45,212,191" : "129,140,248";
          g.addColorStop(0, `rgba(255,255,255,${0.75 * d})`);
          g.addColorStop(0.35, `rgba(${hue},${0.55 + d * 0.4})`);
          g.addColorStop(1, `rgba(${hue},0)`);
          ctx.globalAlpha = 0.35 + d * 0.65;
          ctx.fillStyle = g;
          ctx.beginPath();
          ctx.arc(pt.sx, pt.sy, r * (2.2 + (d > 0.85 ? pulse * 0.6 : 0)), 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.globalAlpha = 1;
      }
    };

    const loop = (time: number) => {
      phase += Math.min(64, time - last) * 0.0009;
      last = time;
      draw(time);
      if (visible) raf = requestAnimationFrame(loop);
    };

    if (reduced) {
      draw(0);
      return;
    }
    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      cancelAnimationFrame(raf);
      if (visible) {
        last = performance.now();
        raf = requestAnimationFrame(loop);
      }
    });
    io.observe(canvas);
    raf = requestAnimationFrame(loop);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [width, height]);

  return <canvas ref={ref} className={className} style={{ width, height }} aria-hidden="true" />;
}
