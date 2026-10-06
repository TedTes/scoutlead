import { AudienceProfileScreen } from "../screens/AudienceProfileScreen";
import { IntegrationsScreen } from "../screens/IntegrationsScreen";
import { ProductScreen } from "../screens/ProductScreen";
import { ResultsScreen } from "../screens/ResultsScreen";
import { SourceReviewScreen } from "../screens/SourceReviewScreen";
import type { DiscoveryRun } from "../types/domain";
import type { LeadWorkflowCounts, LeadWorkflowView, Screen } from "../types/navigation";

export function renderScreen(
  screen: Screen,
  setActiveScreen: (screen: Screen) => void = () => undefined,
  productEditor: {
    isCreatingProduct: boolean;
    onCreatingProductChange: (isCreating: boolean) => void;
    onDeleteProduct?: () => Promise<void> | void;
  } = {
    isCreatingProduct: false,
    onCreatingProductChange: () => undefined,
  },
  discoveryDraft: {
    draftRunName?: string;
    onRunCreated?: (run: DiscoveryRun) => void;
  } = {},
  resultsNavigation: {
    view: LeadWorkflowView;
    onViewChange: (view: LeadWorkflowView) => void;
    onCountsChange?: (runId: string, counts: LeadWorkflowCounts) => void;
    onCreateAudience?: () => void;
  } = {
    view: "this_week",
    onViewChange: () => undefined,
  },
  sourceReview: {
    onCountChange?: (runId: string, count: number) => void;
  } = {},
) {
  switch (screen) {
    case "integrations":
      return <IntegrationsScreen />;
    case "product":
      return <ProductScreen {...productEditor} onNavigate={setActiveScreen} />;
    case "review":
      return <SourceReviewScreen onCountChange={sourceReview.onCountChange} />;
    case "results":
      return (
        <ResultsScreen
          workflowView={resultsNavigation.view}
          onWorkflowViewChange={resultsNavigation.onViewChange}
          onWorkflowCountsChange={resultsNavigation.onCountsChange}
          onCreateAudience={resultsNavigation.onCreateAudience}
        />
      );
    default:
      return <AudienceProfileScreen />;
  }
}
