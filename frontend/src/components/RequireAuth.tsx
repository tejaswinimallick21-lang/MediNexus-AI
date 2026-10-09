import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { Skeleton } from "./Skeleton";
import { EmptyState } from "./StateViews";

/** Signed-in users only; `route` additionally requires the server-issued allowed_routes to include it. */
export function RequireAuth({ route, children }: { route?: string; children: ReactNode }) {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === "loading") return <Skeleton height={240} radius={10} />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (route && !user.allowed_routes.includes(route)) {
    return (
      <EmptyState
        title="Access denied"
        hint={`Your role (${user.persona}) is not authorized for this console. The attempt is recorded server-side when data is requested.`}
      />
    );
  }
  return <>{children}</>;
}
