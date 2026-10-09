import type { ReactNode } from "react";
import { Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { RequireAuth } from "./components/RequireAuth";
import { EmptyState } from "./components/StateViews";
import { LoginPage } from "./pages/LoginPage";
import { ExecutivePage } from "./pages/ExecutivePage";
import { LaboratoryPage } from "./pages/LaboratoryPage";
import { NotMigratedPage } from "./pages/NotMigratedPage";
import { PharmacyPage } from "./pages/PharmacyPage";
import { ReceptionPage } from "./pages/ReceptionPage";
import { WelcomePage } from "./pages/WelcomePage";
import { CONSOLE_ROUTES } from "./routes";

/** Console pages (path → element). */
const CONSOLE_PAGES: Record<string, ReactNode> = {
  "/reception": <ReceptionPage />,
  "/laboratory": <LaboratoryPage />,
  "/pharmacy": <PharmacyPage />,
  "/executive": <ExecutivePage />,
};

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<WelcomePage />} />
        <Route path="/login" element={<LoginPage />} />
        {CONSOLE_ROUTES.map((route) => (
          <Route
            key={route.path}
            path={`${route.path}/*`}
            element={<RequireAuth route={route.path}>{CONSOLE_PAGES[route.path] ?? <NotMigratedPage route={route} />}</RequireAuth>}
          />
        ))}
        <Route path="*" element={<EmptyState title="Page not found" hint="Use the sidebar to open a console." />} />
      </Route>
    </Routes>
  );
}
