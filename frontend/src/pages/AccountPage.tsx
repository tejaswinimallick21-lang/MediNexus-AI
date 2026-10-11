import { ChangePasswordForm } from "../components/ChangePasswordForm";
import { PageHeader, Panel } from "../components/Panel";
import { useAuth } from "../hooks/useAuth";

/** Your own account: who you are signed in as, and changing your password. */
export function AccountPage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <div>
      <PageHeader eyebrow="Your account" title={user.name} subtitle={`${user.email} · ${user.role_title}${user.department ? ` · ${user.department}` : ""}`} />
      <Panel title="Change password" subtitle="Ends your other sessions; this one stays signed in" icon="Lock">
        <ChangePasswordForm />
      </Panel>
    </div>
  );
}
