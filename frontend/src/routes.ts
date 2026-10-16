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
    path: "/doctor", label: "Oncology Workstation", short: "Oncology", icon: "Stethoscope",
    description: "Tumour-board worklist ranked by 12-month mortality risk, oncology care gaps and the Patient 360 treatment record.",
  },
  {
    path: "/executive", label: "Oncology Outcomes", short: "Outcomes", icon: "Building",
    description: "Survival by cancer type and stage, diagnoses, time to treatment, cost of care and treatment capacity, with every model scored against a baseline.",
  },
  {
    path: "/command-center", label: "Analyst Command Center", short: "Command Center", icon: "Radar",
    description: "Test decisions before making them: outpatient staffing and demand what-ifs and model health.",
  },
  {
    path: "/pharmacy", label: "Pharmacy & Supply Chain", short: "Pharmacy", icon: "Pill",
    description: "Chemotherapy and supportive-care stock-out risk, demand outlook by drug class and one-click purchase orders.",
  },
  {
    path: "/laboratory", label: "Laboratory Operations", short: "Laboratory", icon: "Flask",
    description: "Test volumes including tumour markers, critical-value escalation and capacity planning per discipline.",
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
