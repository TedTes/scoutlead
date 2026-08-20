import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiClient } from "../api/client";
import { getApiBaseUrl } from "../config/env";
import type {
  AgentRunDetail,
  Campaign,
  CampaignCreateInput,
  CampaignSnapshot,
  CampaignTrace,
  ConnectionStatus,
  Conversation,
  ICPPreset,
  Lead,
  Message,
  Metrics,
  ManualClassificationInput,
  Product,
  ProductDescriptionInput,
  ProductIcpSuggestionResponse,
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
  icpPresets: ICPPreset[];
  setSelectedProductId: (productId: string) => void;
  setSelectedCampaignId: (campaignId: string) => void;
  refreshAll: () => Promise<void>;
  refreshSnapshot: (campaignId?: string) => Promise<void>;
  createProduct: (input: unknown) => Promise<Product | null>;
  createProductFromDescription: (input: ProductDescriptionInput) => Promise<Product | null>;
  suggestProductIcps: (input: ProductDescriptionInput) => Promise<ProductIcpSuggestionResponse | null>;
  deleteProduct: (productId?: string) => Promise<void>;
  updateProduct: (productId: string, update: Partial<Product>) => Promise<void>;
  updateSelectedProduct: (update: Partial<Product>) => Promise<void>;
  createCampaign: (input: CampaignCreateInput) => Promise<Campaign | null>;
  deleteCampaigns: (campaignIds: string[]) => Promise<void>;
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
  generateCampaignInsight: (campaignId?: string) => Promise<void>;
};

const AppDataContext = createContext<AppDataContextValue | null>(null);

const emptySnapshot: CampaignSnapshot = {
  campaignSources: [],
  leads: [],
  discoveryCandidates: [],
  messages: [],
  conversations: [],
  agentRuns: [],
};

async function getTraceWithFallback(api: ApiClient, campaignId: string): Promise<CampaignTrace | undefined> {
  try {
    return await api.getCampaignTrace(campaignId);
  } catch {
    const runs = await api.getCampaignAgentRuns(campaignId).catch(() => []);
    if (!runs.length) return undefined;

    const details = await Promise.all(
      runs.map(async (run): Promise<AgentRunDetail> => {
        try {
          return await api.getAgentRun(run.id);
        } catch {
          return { ...run, steps: [], tool_calls: [] };
        }
      }),
    );

    return {
      campaign_id: campaignId,
      run_count: details.length,
      latest_run: details[0] ?? null,
      runs: details,
    };
  }
}

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
  const [icpPresets, setIcpPresets] = useState<ICPPreset[]>([]);

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
      const [
        campaign,
        campaignSources,
        leads,
        discoveryCandidates,
        messages,
        conversations,
        metrics,
        preflight,
        insight,
        trace,
      ] = await Promise.all([
        api.getCampaign(campaignId),
        api.getCampaignSources(campaignId).catch(() => []),
        api.getLeads(campaignId),
        api.getDiscoveryCandidates(campaignId).catch(() => []),
        api.getMessages(campaignId),
        api.getConversations(campaignId),
        api.getMetrics(campaignId),
        api.getCampaignPreflight(campaignId),
        api.getCampaignInsight(campaignId).catch(() => undefined),
        getTraceWithFallback(api, campaignId),
      ]);
      const latestAgentRun = trace?.latest_run ?? undefined;
      const agentRuns = trace?.runs ?? [];
      setSnapshot({
        campaign,
        campaignSources,
        leads,
        discoveryCandidates,
        messages,
        conversations,
        metrics,
        insight,
        preflight,
        trace,
        agentRuns,
        latestAgentRun,
      });
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
      setIcpPresets(await api.getIcpPresets().catch(() => []));

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
      icpPresets,
      setSelectedProductId: persistSelectedProductId,
      setSelectedCampaignId: persistSelectedCampaignId,
      refreshAll,
      refreshSnapshot,
      createProduct: async (input) => {
        let created: Product | null = null;
        await mutate(async () => {
          const product = await api.createProduct(input);
          localStorage.setItem("selectedProductId", product.id);
          created = product;
        });
        return created;
      },
      createProductFromDescription: async (input) => {
        let created: Product | null = null;
        await mutate(async () => {
          const product = await api.createProductFromDescription(input);
          localStorage.setItem("selectedProductId", product.id);
          localStorage.setItem("selectedCampaignId", "");
          created = product;
        });
        return created;
      },
      suggestProductIcps: async (input) => {
        setError("");
        try {
          return await api.suggestProductIcps(input);
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err));
          throw err;
        }
      },
      deleteProduct: (productId = selectedProductIdState) =>
        mutate(async () => {
          if (!productId) return;
          await api.deleteProduct(productId);
          if (productId === selectedProductIdState) {
            localStorage.removeItem("selectedProductId");
            localStorage.setItem("selectedCampaignId", "");
          }
        }),
      updateProduct: (productId, update) =>
        mutate(async () => {
          if (!productId) return;
          await api.updateProduct(productId, update);
        }),
      updateSelectedProduct: (update) =>
        mutate(async () => {
          if (!selectedProductIdState) return;
          await api.updateProduct(selectedProductIdState, update);
        }),
      createCampaign: async (input) => {
        let created: Campaign | null = null;
        await mutate(async () => {
          const campaign = await api.createCampaign(input);
          localStorage.setItem("selectedCampaignId", campaign.id);
          created = campaign;
        });
        return created;
      },
      deleteCampaigns: (campaignIds) =>
        mutate(async () => {
          await Promise.all(campaignIds.map((campaignId) => api.deleteCampaign(campaignId)));
          if (campaignIds.includes(selectedCampaignIdState)) {
            localStorage.setItem("selectedCampaignId", "");
          }
        }),
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
      generateCampaignInsight: (campaignId = selectedCampaignIdState) =>
        mutate(async () => {
          if (campaignId) await api.generateCampaignInsight(campaignId);
        }),
    }),
    [
      api,
      apiHealthy,
      campaigns,
      connections,
      error,
      icpPresets,
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
