import { animate, motion, useMotionValue, useReducedMotion, useSpring, useTransform } from "framer-motion";
import { useEffect, useRef, useState, type ReactNode } from "react";

/** Container that staggers its <Reveal> children in on mount. */
export function Stagger({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div
      className={className}
      initial="hidden"
      animate="show"
      variants={{ hidden: {}, show: { transition: { staggerChildren: 0.06 } } }}
    >
      {children}
    </motion.div>
  );
}

export function Reveal({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div
      className={className}
      variants={{
        hidden: { opacity: 0, y: 14, filter: "blur(4px)" },
        show: { opacity: 1, y: 0, filter: "blur(0px)", transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] } },
      }}
    >
      {children}
    </motion.div>
  );
}

/** 3D tilt-on-hover with a moving specular highlight. */
export function TiltCard({ children, className, max = 8 }: { children: ReactNode; className?: string; max?: number }) {
  const reduced = useReducedMotion();
  const mx = useMotionValue(0.5);
  const my = useMotionValue(0.5);
  const rx = useSpring(useTransform(my, [0, 1], [max, -max]), { stiffness: 220, damping: 18 });
  const ry = useSpring(useTransform(mx, [0, 1], [-max, max]), { stiffness: 220, damping: 18 });
  const shine = useTransform([mx, my] as never, ([x, y]: number[]) =>
    `radial-gradient(420px circle at ${x * 100}% ${y * 100}%, rgba(255,255,255,0.22), transparent 45%)`,
  );

  if (reduced) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      style={{ rotateX: rx, rotateY: ry, transformPerspective: 900, position: "relative" }}
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        mx.set((e.clientX - r.left) / r.width);
        my.set((e.clientY - r.top) / r.height);
      }}
      onMouseLeave={() => {
        mx.set(0.5);
        my.set(0.5);
      }}
      whileHover={{ scale: 1.015 }}
      transition={{ type: "spring", stiffness: 260, damping: 20 }}
    >
      {children}
      <motion.span
        aria-hidden="true"
        style={{ position: "absolute", inset: 0, borderRadius: "inherit", background: shine, pointerEvents: "none", mixBlendMode: "overlay" }}
      />
    </motion.div>
  );
}

/** Animates from 0 to `value` once, rendering through `format` (keeps tabular numbers). */
export function CountUp({ value, format }: { value: number; format: (n: number) => string }) {
  const reduced = useReducedMotion();
  const [display, setDisplay] = useState(() => format(reduced ? value : 0));
  const prev = useRef(0);

  useEffect(() => {
    if (reduced) {
      setDisplay(format(value));
      return;
    }
    const controls = animate(prev.current, value, {
      duration: 1.1,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => setDisplay(format(v)),
    });
    prev.current = value;
    return () => controls.stop();
  }, [value, format, reduced]);

  return <>{display}</>;
}
