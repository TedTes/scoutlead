import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiClient } from "../api/client";
import { getApiBaseUrl } from "../config/env";
import type {
  Campaign,
  CampaignCreateInput,
  CampaignSnapshot,
  ConnectionStatus,
  Conversation,
  Lead,
  Message,
  Metrics,
  ManualClassificationInput,
  Product,
} from "../types/domain";

type AppDataContextValue = {
  apiHealthy: boolean;
  loading: boolean;
  error: string;
  products: Product[];
  campaigns: Campaign[];
  selectedProductId: string;
  selectedCampaignId: string;
  selectedProduct?: Product;
  selectedCampaign?: Campaign;
  productCampaigns: Campaign[];
  snapshot: CampaignSnapshot;
  connections: ConnectionStatus[];
  setSelectedProductId: (productId: string) => void;
  setSelectedCampaignId: (campaignId: string) => void;
  refreshAll: () => Promise<void>;
  refreshSnapshot: (campaignId?: string) => Promise<void>;
  createProduct: (input: unknown) => Promise<boolean>;
  updateSelectedProduct: (update: Partial<Product>) => Promise<void>;
  createCampaign: (input: CampaignCreateInput) => Promise<boolean>;
  runCampaign: (campaignId?: string) => Promise<void>;
  enqueueCampaign: (campaignId?: string) => Promise<void>;
  pauseCampaign: (campaignId?: string) => Promise<void>;
  resumeCampaign: (campaignId?: string) => Promise<void>;
  addSeedLeads: (seeds: unknown[]) => Promise<void>;
  updateMessage: (messageId: string, update: Partial<Message>) => Promise<void>;
  approveMessage: (messageId: string) => Promise<void>;
  sendMessage: (messageId: string) => Promise<void>;
  cancelMessage: (messageId: string) => Promise<void>;
  recordResponse: (conversationId: string, body: string) => Promise<void>;
  manuallyClassifyResponse: (
    conversationId: string,
    classification: ManualClassificationInput,
  ) => Promise<void>;
};

const AppDataContext = createContext<AppDataContextValue | null>(null);

const emptySnapshot: CampaignSnapshot = {
  leads: [],
  messages: [],
  conversations: [],
};

export function AppDataProvider({ children }: { children: React.ReactNode }) {
  const [apiHealthy, setApiHealthy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedProductIdState, setSelectedProductIdState] = useState(
    localStorage.getItem("selectedProductId") || "",
  );
  const [selectedCampaignIdState, setSelectedCampaignIdState] = useState(
    localStorage.getItem("selectedCampaignId") || "",
  );
  const [snapshot, setSnapshot] = useState<CampaignSnapshot>(emptySnapshot);
  const [connections, setConnections] = useState<ConnectionStatus[]>([]);

  const apiBaseUrl = useMemo(() => getApiBaseUrl(), []);
  const api = useMemo(() => new ApiClient({ baseUrl: apiBaseUrl }), [apiBaseUrl]);

  const selectedProduct = products.find((product) => product.id === selectedProductIdState);
  const productCampaigns = campaigns.filter((campaign) => campaign.product_id === selectedProductIdState);
  const selectedCampaign =
    snapshot.campaign ?? campaigns.find((campaign) => campaign.id === selectedCampaignIdState);

  const persistSelectedProductId = useCallback(
    (productId: string, nextCampaigns = campaigns) => {
      localStorage.setItem("selectedProductId", productId);
      setSelectedProductIdState(productId);

      const firstCampaignForProduct = nextCampaigns.find((campaign) => campaign.product_id === productId);
      const nextCampaignId = firstCampaignForProduct?.id || "";
      localStorage.setItem("selectedCampaignId", nextCampaignId);
      setSelectedCampaignIdState(nextCampaignId);
    },
    [campaigns],
  );

  const persistSelectedCampaignId = useCallback((campaignId: string) => {
    localStorage.setItem("selectedCampaignId", campaignId);
    setSelectedCampaignIdState(campaignId);
  }, []);

  const refreshConnections = useCallback(async () => {
    try {
      setConnections(await api.getConnectionsStatus());
    } catch {
      setConnections([]);
    }
  }, [api]);

  const refreshSnapshot = useCallback(
    async (campaignId = selectedCampaignIdState) => {
      if (!campaignId) {
        setSnapshot(emptySnapshot);
        return;
      }
      const [campaign, leads, messages, conversations, metrics] = await Promise.all([
        api.getCampaign(campaignId),
        api.getLeads(campaignId),
        api.getMessages(campaignId),
        api.getConversations(campaignId),
        api.getMetrics(campaignId),
      ]);
      setSnapshot({ campaign, leads, messages, conversations, metrics });
    },
    [api, selectedCampaignIdState],
  );

  const refreshAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [health, nextProducts, nextCampaigns] = await Promise.all([
        api.getHealth().then(
          () => true,
          () => false,
        ),
        api.getProducts(),
        api.getCampaigns(),
      ]);
      setApiHealthy(health);
      setProducts(nextProducts);
      setCampaigns(nextCampaigns);

      const storedProductId = localStorage.getItem("selectedProductId") || "";
      const nextProductId =
        (storedProductId && nextProducts.some((product) => product.id === storedProductId)
          ? storedProductId
          : nextProducts[0]?.id) || "";
      setSelectedProductIdState(nextProductId);
      if (nextProductId) localStorage.setItem("selectedProductId", nextProductId);

      const storedCampaignId = localStorage.getItem("selectedCampaignId") || "";
      const productCampaignList = nextCampaigns.filter((campaign) => campaign.product_id === nextProductId);
      const nextCampaignId =
        (storedCampaignId &&
        productCampaignList.some((campaign) => campaign.id === storedCampaignId)
          ? storedCampaignId
          : productCampaignList[0]?.id) || "";
      setSelectedCampaignIdState(nextCampaignId);
      localStorage.setItem("selectedCampaignId", nextCampaignId);

      await refreshConnections();
      await refreshSnapshot(nextCampaignId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [api, refreshConnections, refreshSnapshot]);

  const mutate = useCallback(
    async (action: () => Promise<unknown>) => {
      setError("");
      setLoading(true);
      try {
        await action();
        await refreshAll();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    },
    [refreshAll],
  );

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  const value = useMemo<AppDataContextValue>(
    () => ({
      apiHealthy,
      loading,
      error,
      products,
      campaigns,
      selectedProductId: selectedProductIdState,
      selectedCampaignId: selectedCampaignIdState,
      selectedProduct,
      selectedCampaign,
      productCampaigns,
      snapshot,
      connections,
      setSelectedProductId: persistSelectedProductId,
      setSelectedCampaignId: persistSelectedCampaignId,
      refreshAll,
      refreshSnapshot,
      createProduct: async (input) => {
        let created = false;
        await mutate(async () => {
          const product = await api.createProduct(input);
          localStorage.setItem("selectedProductId", product.id);
          created = true;
        });
        return created;
      },
      updateSelectedProduct: (update) =>
        mutate(async () => {
          if (!selectedProductIdState) return;
          await api.updateProduct(selectedProductIdState, update);
        }),
      createCampaign: async (input) => {
        let created = false;
        await mutate(async () => {
          const campaign = await api.createCampaign(input);
          localStorage.setItem("selectedCampaignId", campaign.id);
          created = true;
        });
        return created;
      },
      runCampaign: (campaignId = selectedCampaignIdState) =>
        mutate(async () => {
          if (campaignId) await api.runCampaign(campaignId);
        }),
      enqueueCampaign: (campaignId = selectedCampaignIdState) =>
        mutate(async () => {
          if (campaignId) await api.enqueueCampaign(campaignId);
        }),
      pauseCampaign: (campaignId = selectedCampaignIdState) =>
        mutate(async () => {
          if (campaignId) await api.pauseCampaign(campaignId);
        }),
      resumeCampaign: (campaignId = selectedCampaignIdState) =>
        mutate(async () => {
          if (campaignId) await api.resumeCampaign(campaignId);
        }),
      addSeedLeads: (seeds) =>
        mutate(async () => {
          if (selectedCampaignIdState) await api.addSeedLeads(selectedCampaignIdState, seeds);
        }),
      updateMessage: (messageId, update) =>
        mutate(async () => {
          await api.updateMessage(messageId, update);
        }),
      approveMessage: (messageId) =>
        mutate(async () => {
          await api.approveMessage(messageId, "operator");
        }),
      sendMessage: (messageId) =>
        mutate(async () => {
          await api.sendMessage(messageId);
        }),
      cancelMessage: (messageId) =>
        mutate(async () => {
          await api.cancelMessage(messageId);
        }),
      recordResponse: (conversationId, body) =>
        mutate(async () => {
          await api.recordResponse(conversationId, body);
        }),
      manuallyClassifyResponse: (conversationId, classification) =>
        mutate(async () => {
          await api.manuallyClassifyResponse(conversationId, classification);
        }),
    }),
    [
      api,
      apiHealthy,
      campaigns,
      connections,
      error,
      loading,
      mutate,
      persistSelectedCampaignId,
      persistSelectedProductId,
      productCampaigns,
      products,
      refreshAll,
      refreshSnapshot,
      selectedCampaign,
      selectedCampaignIdState,
      selectedProduct,
      selectedProductIdState,
      snapshot,
    ],
  );

  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}

export function useAppData() {
  const value = useContext(AppDataContext);
  if (!value) {
    throw new Error("useAppData must be used inside AppDataProvider");
  }
  return value;
}
