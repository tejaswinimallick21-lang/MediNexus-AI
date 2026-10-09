import type { SVGProps } from "react";

/** Minimal stroke icon set (24×24, currentColor) — replaces emoji for a consistent enterprise look. */
type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 18, children, ...props }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export const Icon = {
  Logo: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12 3l7.5 4.3v8.6L12 20.2 4.5 15.9V7.3z" />
      <path d="M12 8.5v7M8.5 12h7" />
    </Svg>
  ),
  Database: (p: IconProps) => (
    <Svg {...p}>
      <ellipse cx="12" cy="5.5" rx="7" ry="2.5" />
      <path d="M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5" />
    </Svg>
  ),
  Stethoscope: (p: IconProps) => (
    <Svg {...p}>
      <path d="M6 3v6a4 4 0 008 0V3" />
      <path d="M10 13v2a5 5 0 0010 0v-2" />
      <circle cx="20" cy="11" r="2" />
    </Svg>
  ),
  Building: (p: IconProps) => (
    <Svg {...p}>
      <rect x="4" y="3" width="16" height="18" rx="1.5" />
      <path d="M9 21v-4h6v4M8 7h2M14 7h2M8 11h2M14 11h2" />
    </Svg>
  ),
  Pill: (p: IconProps) => (
    <Svg {...p}>
      <rect x="2.8" y="8.5" width="18.4" height="7" rx="3.5" transform="rotate(-45 12 12)" />
      <path d="M9.2 9.2l5.6 5.6" />
    </Svg>
  ),
  Flask: (p: IconProps) => (
    <Svg {...p}>
      <path d="M9 3h6M10 3v6L4.5 18.5A1.7 1.7 0 006 21h12a1.7 1.7 0 001.5-2.5L14 9V3" />
      <path d="M7 15h10" />
    </Svg>
  ),
  Clipboard: (p: IconProps) => (
    <Svg {...p}>
      <rect x="5" y="4" width="14" height="17" rx="2" />
      <path d="M9 4V3h6v1M9 10h6M9 14h6M9 18h3" />
    </Svg>
  ),
  Shield: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12 3l7 3v5.5c0 4.4-3 8.2-7 9.5-4-1.3-7-5.1-7-9.5V6z" />
      <path d="M9 12l2 2 4-4" />
    </Svg>
  ),
  Home: (p: IconProps) => (
    <Svg {...p}>
      <path d="M4 11l8-7 8 7M6 9.5V20h12V9.5" />
    </Svg>
  ),
  Logout: (p: IconProps) => (
    <Svg {...p}>
      <path d="M15 4h3a2 2 0 012 2v12a2 2 0 01-2 2h-3M10 16l-4-4 4-4M6 12h10" />
    </Svg>
  ),
  Key: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="8" cy="15" r="4" />
      <path d="M11 12l9-9M17 6l2 2" />
    </Svg>
  ),
  Pulse: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3 12h4l2-6 4 12 2-6h6" />
    </Svg>
  ),
  Users: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20a6.5 6.5 0 0113 0M16 4.6a3.5 3.5 0 010 6.8M18 14a6.5 6.5 0 013.5 6" />
    </Svg>
  ),
  Clock: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </Svg>
  ),
  Check: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M8.5 12l2.5 2.5 4.5-5" />
    </Svg>
  ),
  Alert: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12 4l9 16H3z" />
      <path d="M12 10v4M12 17h.01" />
    </Svg>
  ),
  Calendar: (p: IconProps) => (
    <Svg {...p}>
      <rect x="3.5" y="5" width="17" height="15" rx="2" />
      <path d="M3.5 10h17M8 3v4M16 3v4" />
    </Svg>
  ),
  Lock: (p: IconProps) => (
    <Svg {...p}>
      <rect x="5" y="10.5" width="14" height="10" rx="2" />
      <path d="M8 10.5V7.5a4 4 0 018 0v3" />
    </Svg>
  ),
  Arrow: (p: IconProps) => (
    <Svg {...p}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </Svg>
  ),
  Sparkle: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z" />
    </Svg>
  ),
};

export type IconName = keyof typeof Icon;
