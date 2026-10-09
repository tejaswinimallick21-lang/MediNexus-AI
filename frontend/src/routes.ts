import type { IconName } from "./components/Icons";

/** Console routes in sidebar order. */
export interface ConsoleRoute {
  path: string;
  label: string;
  short: string;
  icon: IconName;
}

export const CONSOLE_ROUTES: ConsoleRoute[] = [
  { path: "/data", label: "Data Engineering", short: "Data Platform", icon: "Database" },
  { path: "/doctor", label: "Clinical Workstation", short: "Clinical", icon: "Stethoscope" },
  { path: "/executive", label: "Executive Operations", short: "Executive", icon: "Building" },
  { path: "/pharmacy", label: "Pharmacy & Supply Chain", short: "Pharmacy", icon: "Pill" },
  { path: "/laboratory", label: "Laboratory Operations", short: "Laboratory", icon: "Flask" },
  { path: "/reception", label: "Reception & Patient Flow", short: "Reception", icon: "Clipboard" },
  { path: "/it", label: "Security & Infrastructure", short: "Security", icon: "Shield" },
];
