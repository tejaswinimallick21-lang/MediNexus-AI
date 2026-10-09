/** Console routes in sidebar order. `migrated` flips to true as each Streamlit page is replaced. */
export interface ConsoleRoute {
  path: string;
  label: string;
  icon: string;
  streamlitPage: string;
  migrated: boolean;
}

export const CONSOLE_ROUTES: ConsoleRoute[] = [
  { path: "/data", label: "Data Engineering", icon: "⚙️", streamlitPage: "data_engineer", migrated: false },
  { path: "/doctor", label: "Doctor Dashboard", icon: "🩺", streamlitPage: "doctor", migrated: false },
  { path: "/executive", label: "Executive Dashboard", icon: "🏢", streamlitPage: "administrator", migrated: false },
  { path: "/pharmacy", label: "Pharmacy Dashboard", icon: "💊", streamlitPage: "pharmacist", migrated: false },
  { path: "/laboratory", label: "Laboratory Dashboard", icon: "🔬", streamlitPage: "laboratory", migrated: false },
  { path: "/reception", label: "Reception Dashboard", icon: "📋", streamlitPage: "receptionist", migrated: false },
  { path: "/it", label: "IT & Security Admin", icon: "🛡️", streamlitPage: "it_admin", migrated: false },
];
