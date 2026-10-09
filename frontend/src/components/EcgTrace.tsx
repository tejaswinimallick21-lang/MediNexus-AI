import { useEffect, useRef } from "react";

/** Live ECG (PQRST) sweep with a glowing trailing head, drawn on canvas. */
export function EcgTrace({ width = 520, height = 90, className }: { width?: number; height?: number; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    const beat = (t: number) => {
      // One heartbeat over t ∈ [0,1): P wave, QRS complex, T wave
      const g = (mu: number, sigma: number, amp: number) => amp * Math.exp(-((t - mu) ** 2) / (2 * sigma ** 2));
      return g(0.18, 0.025, 0.12) - g(0.37, 0.008, 0.15) + g(0.4, 0.01, 1) - g(0.43, 0.01, 0.28) + g(0.62, 0.045, 0.25);
    };
    const period = width * 0.42;
    const mid = height * 0.62;
    const amp = height * 0.5;
    const y = (x: number) => mid - beat(((x % period) + period) % period / period) * amp;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let head = 0, raf = 0, last = performance.now();

    const draw = () => {
      ctx.clearRect(0, 0, width, height);
      const trail = width * 0.65;
      for (let x = 0; x < width; x += 2) {
        const behind = (head - x + width) % width;
        if (!reduced && behind > trail) continue;
        const alpha = reduced ? 0.8 : 1 - behind / trail;
        ctx.strokeStyle = `rgba(45,212,191,${alpha})`;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x, y(x));
        ctx.lineTo(x + 2, y(x + 2));
        ctx.stroke();
      }
      if (!reduced) {
        const hy = y(head);
        const g = ctx.createRadialGradient(head, hy, 0, head, hy, 14);
        g.addColorStop(0, "rgba(255,255,255,0.95)");
        g.addColorStop(0.3, "rgba(45,212,191,0.8)");
        g.addColorStop(1, "rgba(45,212,191,0)");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(head, hy, 14, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const loop = (time: number) => {
      head = (head + Math.min(64, time - last) * 0.16) % width;
      last = time;
      draw();
      raf = requestAnimationFrame(loop);
    };
    if (reduced) {
      draw();
      return;
    }
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [width, height]);

  return <canvas ref={ref} className={className} style={{ width, height }} aria-hidden="true" />;
}
