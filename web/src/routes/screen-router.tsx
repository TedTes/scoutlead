import { OverviewScreen } from "../screens/OverviewScreen";
import { IntegrationsScreen } from "../screens/IntegrationsScreen";
import { ProductScreen } from "../screens/ProductScreen";
import { ResultsScreen } from "../screens/ResultsScreen";
import type { Screen } from "../types/navigation";

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
    onRunCreated?: () => void;
  } = {},
) {
  switch (screen) {
    case "integrations":
      return <IntegrationsScreen />;
    case "product":
      return <ProductScreen {...productEditor} onNavigate={setActiveScreen} />;
    case "results":
      return <ResultsScreen />;
    default:
      return <OverviewScreen {...discoveryDraft} />;
  }
}
