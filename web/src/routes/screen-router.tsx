import { AudienceProfileScreen } from "../screens/AudienceProfileScreen";
import { IntegrationsScreen } from "../screens/IntegrationsScreen";
import { ProductScreen } from "../screens/ProductScreen";
import { ResultsScreen } from "../screens/ResultsScreen";
import type { ReactNode } from "react";
import type { LeadWorkflowCounts, LeadWorkflowView, Screen } from "../types/navigation";

export function renderScreen(
  screen: Screen,
  productEditor: {
    isCreatingProduct: boolean;
    onCreatingProductChange: (isCreating: boolean) => void;
    onDeleteProduct?: () => Promise<void> | void;
  } = {
    isCreatingProduct: false,
    onCreatingProductChange: () => undefined,
  },
  resultsNavigation: {
    listRequestId?: number;
    view: LeadWorkflowView;
    onViewChange: (view: LeadWorkflowView) => void;
    onCountsChange?: (runId: string, counts: LeadWorkflowCounts) => void;
    onCreateAudience?: () => void;
    accountControl?: ReactNode;
  } = {
    listRequestId: 0,
    view: "this_week",
    onViewChange: () => undefined,
  },
) {
  switch (screen) {
    case "integrations":
      return <IntegrationsScreen />;
    case "product":
      return <ProductScreen {...productEditor} />;
    case "results":
      return (
        <ResultsScreen
          listRequestId={resultsNavigation.listRequestId}
          workflowView={resultsNavigation.view}
          onWorkflowViewChange={resultsNavigation.onViewChange}
          onWorkflowCountsChange={resultsNavigation.onCountsChange}
          onCreateAudience={resultsNavigation.onCreateAudience}
          accountControl={resultsNavigation.accountControl}
        />
      );
    default:
      return <AudienceProfileScreen />;
  }
}
