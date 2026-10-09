import { PageHeader } from "../components/Panel";
import { EmptyState } from "../components/StateViews";
import type { ConsoleRoute } from "../routes";

/** Placeholder for consoles still served by Streamlit during the migration. */
export function NotMigratedPage({ route }: { route: ConsoleRoute }) {
  return (
    <div>
      <PageHeader title={route.label} subtitle="This console has not been migrated to React yet." />
      <EmptyState
        title="Use the Streamlit app for this console for now"
        hint={`Run \`npm run streamlit\` and open the "${route.label}" page. It will appear here once migrated.`}
      />
    </div>
  );
}
