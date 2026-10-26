import { AudienceProfileScreen } from "../screens/AudienceProfileScreen";
import { AudiencesOverviewScreen } from "../screens/AudiencesOverviewScreen";
import { IntegrationsScreen } from "../screens/IntegrationsScreen";
import { ProductScreen } from "../screens/ProductScreen";
import { ResultsScreen } from "../screens/ResultsScreen";
import type { ReactNode } from "react";
import type { LeadWorkflowView, Screen } from "../types/navigation";

export function renderScreen(
  screen: Screen,
  resultsNavigation: {
    listRequestId?: number;
    view: LeadWorkflowView;
    onViewChange: (view: LeadWorkflowView) => void;
    onCreateAudience?: () => void;
    accountControl?: ReactNode;
  } = {
    listRequestId: 0,
    view: "this_week",
    onViewChange: () => undefined,
  },
  audienceNavigation: { defaultFolderId?: string; onOpenAudience: (id: string) => void } = {
    onOpenAudience: () => undefined,
  },
) {
  switch (screen) {
    case "audiences":
      return <AudiencesOverviewScreen onOpenAudience={audienceNavigation.onOpenAudience} />;
    case "integrations":
      return <IntegrationsScreen />;
    case "product":
      return <ProductScreen />;
    case "results":
      return (
        <ResultsScreen
          listRequestId={resultsNavigation.listRequestId}
          workflowView={resultsNavigation.view}
          onWorkflowViewChange={resultsNavigation.onViewChange}
          onCreateAudience={resultsNavigation.onCreateAudience}
          accountControl={resultsNavigation.accountControl}
        />
      );
    default:
      return <AudienceProfileScreen defaultFolderId={audienceNavigation.defaultFolderId} />;
  }
}
