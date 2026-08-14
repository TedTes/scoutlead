import { ApprovalsScreen } from "../screens/ApprovalsScreen";
import { CampaignsScreen } from "../screens/CampaignsScreen";
import { ConnectionsScreen } from "../screens/ConnectionsScreen";
import { ConversationsScreen } from "../screens/ConversationsScreen";
import { LeadsScreen } from "../screens/LeadsScreen";
import { OverviewScreen } from "../screens/OverviewScreen";
import { ProductScreen } from "../screens/ProductScreen";
import type { Screen } from "../types/navigation";

export function renderScreen(
  screen: Screen,
  setActiveScreen: (screen: Screen) => void,
  productEditor: {
    isCreatingProduct: boolean;
    newProductToken: number;
    onCreatingProductChange: (isCreating: boolean) => void;
  },
) {
  switch (screen) {
    case "product":
      return <ProductScreen {...productEditor} />;
    case "campaigns":
      return <CampaignsScreen onNavigate={setActiveScreen} />;
    case "leads":
      return <LeadsScreen />;
    case "approvals":
      return <ApprovalsScreen />;
    case "conversations":
      return <ConversationsScreen />;
    case "connections":
      return <ConnectionsScreen />;
    default:
      return <OverviewScreen onNewCampaign={() => setActiveScreen("campaigns")} />;
  }
}
