import { OverviewScreen } from "../screens/OverviewScreen";
import { ProductScreen } from "../screens/ProductScreen";
import { ResultsScreen } from "../screens/ResultsScreen";
import type { Screen } from "../types/navigation";

export function renderScreen(
  screen: Screen,
  setActiveScreen: (screen: Screen) => void = () => undefined,
  productEditor: {
    isCreatingProduct: boolean;
    onCreatingProductChange: (isCreating: boolean) => void;
  } = {
    isCreatingProduct: false,
    onCreatingProductChange: () => undefined,
  },
) {
  switch (screen) {
    case "product":
      return <ProductScreen {...productEditor} onNavigate={setActiveScreen} />;
    case "results":
      return <ResultsScreen />;
    default:
      return <OverviewScreen />;
  }
}
