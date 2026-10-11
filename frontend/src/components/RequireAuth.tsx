import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { ChangePasswordForm } from "./ChangePasswordForm";
import { PageHeader, Panel } from "./Panel";
import { Skeleton } from "./Skeleton";
import { EmptyState } from "./StateViews";

/** Signed-in users only; `route` additionally requires the server-issued allowed_routes to include it. */
export function RequireAuth({ route, children }: { route?: string; children: ReactNode }) {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === "loading") return <Skeleton height={240} radius={10} />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (user.must_change_password) {
    // First sign-in, or an administrator reset the password: a new one is required before anything else
    return (
      <div>
        <PageHeader
          eyebrow="Welcome"
          title={`Choose your password, ${user.name.split(" ")[0]}`}
          subtitle="You signed in with a temporary password. Replace it to continue."
        />
        <Panel title="Set a new password" icon="Lock">
          <ChangePasswordForm />
        </Panel>
      </div>
    );
  }
  if (route && !user.allowed_routes.includes(route)) {
    return (
      <EmptyState
        title="Access denied"
        hint={`Your role (${user.role_title}) is not authorized for this workspace.`}
      />
    );
  }
  return <>{children}</>;
}
