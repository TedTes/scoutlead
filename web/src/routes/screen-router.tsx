import { ApprovalsScreen } from "../screens/ApprovalsScreen";
import { ConnectionsScreen } from "../screens/ConnectionsScreen";
import { OverviewScreen } from "../screens/OverviewScreen";
import { ProductScreen } from "../screens/ProductScreen";
import { ResultsScreen } from "../screens/ResultsScreen";
import type { Screen } from "../types/navigation";

export function renderScreen(
  screen: Screen,
  setActiveScreen: (screen: Screen) => void,
  productEditor: {
    isCreatingProduct: boolean;
    onCreatingProductChange: (isCreating: boolean) => void;
  },
) {
  switch (screen) {
    case "product":
      return <ProductScreen {...productEditor} onNavigate={setActiveScreen} />;
    case "results":
      return <ResultsScreen />;
    case "approvals":
      return <ApprovalsScreen />;
    case "connections":
      return <ConnectionsScreen />;
    default:
      return <OverviewScreen />;
  }
}
