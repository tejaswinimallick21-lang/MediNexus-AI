import type { IconName } from "./components/Icons";

/** Console routes in sidebar order. */
export interface ConsoleRoute {
  path: string;
  label: string;
  short: string;
  icon: IconName;
  description: string;
}

export const CONSOLE_ROUTES: ConsoleRoute[] = [
  {
    path: "/data", label: "Data Engineering", short: "Data Platform", icon: "Database",
    description: "Medallion pipeline (Bronze → Silver → Gold), data quality checks, lineage and model training runs.",
  },
  {
    path: "/doctor", label: "Clinical Workstation", short: "Clinical", icon: "Stethoscope",
    description: "Morning huddle ranked by readmission risk, care-gap radar and the Patient 360 record.",
  },
  {
    path: "/executive", label: "Executive Operations", short: "Executive", icon: "Building",
    description: "Admissions, readmissions, revenue and capacity across the network, with every model scored against a baseline.",
  },
  {
    path: "/command-center", label: "Analyst Command Center", short: "Command Center", icon: "Radar",
    description: "Test decisions before making them: staffing and demand what-ifs, readmission programme economics and model health.",
  },
  {
    path: "/pharmacy", label: "Pharmacy & Supply Chain", short: "Pharmacy", icon: "Pill",
    description: "Stock-out risk, demand outlook by drug class and one-click purchase orders.",
  },
  {
    path: "/laboratory", label: "Laboratory Operations", short: "Laboratory", icon: "Flask",
    description: "Test volumes, critical-value escalation and capacity planning per discipline.",
  },
  {
    path: "/reception", label: "Patient Access", short: "Patient Access", icon: "Clipboard",
    description: "De-identified appointment flow: no-shows, cancellations and waiting times.",
  },
  {
    path: "/it", label: "Security & Infrastructure", short: "Security", icon: "Shield",
    description: "Access audit trail, agent governance and platform health.",
  },
];
