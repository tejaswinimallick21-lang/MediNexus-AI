import { PageHeader } from "../components/Panel";
import { EmptyState } from "../components/StateViews";
import type { ConsoleRoute } from "../routes";

/** Placeholder while a workspace is being built. */
export function NotMigratedPage({ route }: { route: ConsoleRoute }) {
  return (
    <div>
      <PageHeader eyebrow="Coming next" title={route.label} subtitle="This workspace is being rebuilt on the new platform." />
      <EmptyState title="Workspace in progress" hint="It will be available here shortly." />
    </div>
  );
}
