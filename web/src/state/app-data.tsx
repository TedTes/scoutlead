import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ApiClient } from "../api/client";
import { getApiBaseUrl } from "../config/env";
import type {
  AgentRunDetail,
  DiscoveryRun,
  DiscoveryRunCreateInput,
  DiscoveryResult,
  DiscoverySnapshot,
  DiscoveryTrace,
  Message,
  Metrics,
  Product,
  ProductDescriptionInput,
  SourceRequestInput,
  SourceRequestRun,
  SourceProvider,
  SourceRequestSource,
} from "../types/domain";
import { normalizeActiveSourceIds } from "../utils/source-providers";

type AppDataContextValue = {
  apiHealthy: boolean;
  loading: boolean;
  error: string;
  products: Product[];
  discoveryRuns: DiscoveryRun[];
  selectedProductId: string;
  selectedDiscoveryRunId: string;
  selectedProduct?: Product;
  selectedDiscoveryRun?: DiscoveryRun;
  productDiscoveryRuns: DiscoveryRun[];
  productContacts: DiscoveryResult[];
  snapshot: DiscoverySnapshot;
  sourceProviders: SourceProvider[];
  activeSourceIds: SourceRequestSource[];
  setSelectedProductId: (productId: string) => void;
  setSelectedDiscoveryRunId: (runId: string) => void;
  setActiveSourceIds: (sourceIds: SourceRequestSource[]) => void;
  refreshAll: () => Promise<void>;
  refreshSnapshot: (runId?: string) => Promise<void>;
  createProduct: (input: unknown) => Promise<Product | null>;
  createProductFromDescription: (input: ProductDescriptionInput) => Promise<Product | null>;
  deleteProduct: (productId?: string) => Promise<void>;
  discoverProduct: (productId?: string, maxResults?: number) => Promise<void>;
  runSourceRequest: (input: SourceRequestInput) => Promise<SourceRequestRun | null>;
  updateProduct: (productId: string, update: Partial<Product>) => Promise<void>;
  updateSelectedProduct: (update: Partial<Product>) => Promise<void>;
  createDiscoveryRun: (input: DiscoveryRunCreateInput) => Promise<DiscoveryRun | null>;
  renameDiscoveryRun: (runId: string, name: string) => Promise<void>;
  deleteDiscoveryRuns: (runIds: string[]) => Promise<void>;
  runDiscovery: (runId?: string) => Promise<void>;
  enqueueDiscoveryRun: (runId?: string) => Promise<void>;
  pauseDiscoveryRun: (runId?: string) => Promise<void>;
  resumeDiscoveryRun: (runId?: string) => Promise<void>;
  addSeedResults: (seeds: unknown[]) => Promise<void>;
  updateMessage: (messageId: string, update: Partial<Message>) => Promise<void>;
  approveMessage: (messageId: string) => Promise<void>;
  sendMessage: (messageId: string) => Promise<void>;
  cancelMessage: (messageId: string) => Promise<void>;
};

const AppDataContext = createContext<AppDataContextValue | null>(null);

const emptySnapshot: DiscoverySnapshot = {
  sourceConfigs: [],
  results: [],
  discoveryCandidates: [],
  messages: [],
  agentRuns: [],
};

const activeSourcesStorageKey = "scoutlead.activeSourceIds";

function readStoredActiveSourceIds() {
  try {
    const parsed = JSON.parse(localStorage.getItem(activeSourcesStorageKey) || "[]");
    return Array.isArray(parsed) ? parsed.filter((value): value is SourceRequestSource => typeof value === "string") : [];
  } catch {
    return [];
  }
}

async function getTraceWithFallback(api: ApiClient, runId: string): Promise<DiscoveryTrace | undefined> {
  try {
    return await api.getDiscoveryTrace(runId);
  } catch {
    const runs = await api.getDiscoveryRunAgentRuns(runId).catch(() => []);
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
      campaign_id: runId,
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
  const [discoveryRuns, setDiscoveryRuns] = useState<DiscoveryRun[]>([]);
  const [selectedProductIdState, setSelectedProductIdState] = useState(
    localStorage.getItem("selectedProductId") || "",
  );
  const [selectedDiscoveryRunIdState, setSelectedDiscoveryRunIdState] = useState(
    localStorage.getItem("selectedDiscoveryRunId") || "",
  );
  const selectedDiscoveryRunIdRef = useRef(selectedDiscoveryRunIdState);
  const [snapshot, setSnapshot] = useState<DiscoverySnapshot>(emptySnapshot);
  const [productContacts, setProductContacts] = useState<DiscoveryResult[]>([]);
  const [sourceProviders, setSourceProviders] = useState<SourceProvider[]>([]);
  const [activeSourceIds, setActiveSourceIdsState] = useState<SourceRequestSource[]>(readStoredActiveSourceIds);

  const apiBaseUrl = useMemo(() => getApiBaseUrl(), []);
  const api = useMemo(() => new ApiClient({ baseUrl: apiBaseUrl }), [apiBaseUrl]);

  const selectedProduct = products.find((product) => product.id === selectedProductIdState);
  const productDiscoveryRuns = discoveryRuns.filter((run) => run.product_id === selectedProductIdState);
  const selectedDiscoveryRun = selectedDiscoveryRunIdState
    ? snapshot.run?.id === selectedDiscoveryRunIdState
      ? snapshot.run
      : discoveryRuns.find((run) => run.id === selectedDiscoveryRunIdState)
    : undefined;

  const persistSelectedProductId = useCallback(
    (productId: string, nextRuns = discoveryRuns) => {
      localStorage.setItem("selectedProductId", productId);
      setSelectedProductIdState(productId);

      const firstRunForProduct = nextRuns.find((run) => run.product_id === productId);
      const nextRunId = firstRunForProduct?.id || "";
      localStorage.setItem("selectedDiscoveryRunId", nextRunId);
      selectedDiscoveryRunIdRef.current = nextRunId;
      setSelectedDiscoveryRunIdState(nextRunId);
    },
    [discoveryRuns],
  );

  const persistSelectedDiscoveryRunId = useCallback((runId: string) => {
    localStorage.setItem("selectedDiscoveryRunId", runId);
    selectedDiscoveryRunIdRef.current = runId;
    setSelectedDiscoveryRunIdState(runId);
    if (!runId) setSnapshot(emptySnapshot);
  }, []);

  const persistActiveSourceIds = useCallback(
    (sourceIds: SourceRequestSource[]) => {
      const normalized = normalizeActiveSourceIds(sourceIds, sourceProviders);
      localStorage.setItem(activeSourcesStorageKey, JSON.stringify(normalized));
      setActiveSourceIdsState(normalized);
    },
    [sourceProviders],
  );

  const refreshProductContacts = useCallback(
    async (productId: string, runs: DiscoveryRun[]) => {
      if (!productId) {
        setProductContacts([]);
        return;
      }
      const productRuns = runs.filter((run) => run.product_id === productId);
      if (!productRuns.length) {
        setProductContacts([]);
        return;
      }
      const resultGroups = await Promise.all(
        productRuns.map((run) => api.getResults(run.id).catch(() => [])),
      );
      setProductContacts(dedupeContacts(resultGroups.flat()));
    },
    [api],
  );

  const refreshSnapshot = useCallback(
    async (runId?: string) => {
      const targetRunId = runId ?? selectedDiscoveryRunIdRef.current;
      if (!targetRunId) {
        setSnapshot(emptySnapshot);
        return;
      }
      const [
        run,
        sourceConfigs,
        results,
        discoveryCandidates,
        messages,
        metrics,
        preflight,
        trace,
      ] = await Promise.all([
        api.getDiscoveryRun(targetRunId),
        api.getDiscoveryRunSources(targetRunId).catch(() => []),
        api.getResults(targetRunId),
        api.getDiscoveryCandidates(targetRunId).catch(() => []),
        api.getMessages(targetRunId),
        api.getMetrics(targetRunId),
        api.getDiscoveryRunPreflight(targetRunId),
        getTraceWithFallback(api, targetRunId),
      ]);
      const latestAgentRun = trace?.latest_run ?? undefined;
      const agentRuns = trace?.runs ?? [];
      setSnapshot({
        run,
        sourceConfigs,
        results,
        discoveryCandidates,
        messages,
        metrics,
        preflight,
        trace,
        agentRuns,
        latestAgentRun,
      });
    },
    [api],
  );

  const refreshAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [health, nextProducts, nextRuns, nextSourceProviders] = await Promise.all([
        api.getHealth().then(
          () => true,
          () => false,
        ),
        api.getProducts(),
        api.getDiscoveryRuns(),
        api.getSourceProviders().catch(() => []),
      ]);
      setApiHealthy(health);
      setProducts(nextProducts);
      setDiscoveryRuns(nextRuns);
      setSourceProviders(nextSourceProviders);
      const nextActiveSourceIds = normalizeActiveSourceIds(readStoredActiveSourceIds(), nextSourceProviders);
      localStorage.setItem(activeSourcesStorageKey, JSON.stringify(nextActiveSourceIds));
      setActiveSourceIdsState(nextActiveSourceIds);
      const storedProductId = localStorage.getItem("selectedProductId") || "";
      const nextProductId =
        (storedProductId && nextProducts.some((product) => product.id === storedProductId)
          ? storedProductId
          : nextProducts[0]?.id) || "";
      setSelectedProductIdState(nextProductId);
      if (nextProductId) localStorage.setItem("selectedProductId", nextProductId);

      const storedRunId = localStorage.getItem("selectedDiscoveryRunId") || "";
      const productRunList = nextRuns.filter((run) => run.product_id === nextProductId);
      const nextRunId =
        (storedRunId && productRunList.some((run) => run.id === storedRunId) ? storedRunId : productRunList[0]?.id) || "";
      setSelectedDiscoveryRunIdState(nextRunId);
      selectedDiscoveryRunIdRef.current = nextRunId;
      localStorage.setItem("selectedDiscoveryRunId", nextRunId);

      await refreshProductContacts(nextProductId, nextRuns);
      await refreshSnapshot(nextRunId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [api, refreshProductContacts, refreshSnapshot]);

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

  useEffect(() => {
    void refreshProductContacts(selectedProductIdState, discoveryRuns);
  }, [discoveryRuns, refreshProductContacts, selectedProductIdState]);

  const value = useMemo<AppDataContextValue>(
    () => ({
      apiHealthy,
      loading,
      error,
      products,
      discoveryRuns,
      selectedProductId: selectedProductIdState,
      selectedDiscoveryRunId: selectedDiscoveryRunIdState,
      selectedProduct,
      selectedDiscoveryRun,
      productDiscoveryRuns,
      productContacts,
      snapshot,
      activeSourceIds,
      sourceProviders,
      setSelectedProductId: persistSelectedProductId,
      setSelectedDiscoveryRunId: persistSelectedDiscoveryRunId,
      setActiveSourceIds: persistActiveSourceIds,
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
          localStorage.setItem("selectedDiscoveryRunId", "");
          created = product;
        });
        return created;
      },
      deleteProduct: (productId = selectedProductIdState) =>
        mutate(async () => {
          if (!productId) return;
          await api.deleteProduct(productId);
          if (productId === selectedProductIdState) {
            localStorage.removeItem("selectedProductId");
            localStorage.setItem("selectedDiscoveryRunId", "");
          }
        }),
      discoverProduct: (productId = selectedProductIdState, maxResults = 10) =>
        mutate(async () => {
          if (!productId) return;
          const summary = await api.discoverProduct(productId, maxResults);
          localStorage.setItem("selectedDiscoveryRunId", summary.campaign.id);
        }),
      runSourceRequest: async (input) => {
        let created: SourceRequestRun | null = null;
        await mutate(async () => {
          const result = await api.createSourceRequest(input);
          localStorage.setItem("selectedDiscoveryRunId", result.run.id);
          created = result;
        });
        return created;
      },
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
      createDiscoveryRun: async (input) => {
        let created: DiscoveryRun | null = null;
        await mutate(async () => {
          const run = await api.createDiscoveryRun(input);
          localStorage.setItem("selectedDiscoveryRunId", run.id);
          created = run;
        });
        return created;
      },
      renameDiscoveryRun: (runId, name) =>
        mutate(async () => {
          if (!runId || !name.trim()) return;
          await api.updateDiscoveryRun(runId, { name: name.trim() });
        }),
      deleteDiscoveryRuns: (runIds) =>
        mutate(async () => {
          await Promise.all(runIds.map((runId) => api.deleteDiscoveryRun(runId)));
          if (runIds.includes(selectedDiscoveryRunIdState)) {
            localStorage.setItem("selectedDiscoveryRunId", "");
          }
        }),
      runDiscovery: (runId = selectedDiscoveryRunIdState) =>
        mutate(async () => {
          if (runId) await api.runDiscovery(runId);
        }),
      enqueueDiscoveryRun: (runId = selectedDiscoveryRunIdState) =>
        mutate(async () => {
          if (runId) await api.enqueueDiscoveryRun(runId);
        }),
      pauseDiscoveryRun: (runId = selectedDiscoveryRunIdState) =>
        mutate(async () => {
          if (runId) await api.pauseDiscoveryRun(runId);
        }),
      resumeDiscoveryRun: (runId = selectedDiscoveryRunIdState) =>
        mutate(async () => {
          if (runId) await api.resumeDiscoveryRun(runId);
        }),
      addSeedResults: (seeds) =>
        mutate(async () => {
          if (selectedDiscoveryRunIdState) await api.addSeedResults(selectedDiscoveryRunIdState, seeds);
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
    }),
    [
      api,
      apiHealthy,
      discoveryRuns,
      error,
      loading,
      mutate,
      persistSelectedDiscoveryRunId,
      persistSelectedProductId,
      persistActiveSourceIds,
      productDiscoveryRuns,
      productContacts,
      products,
      refreshAll,
      refreshSnapshot,
      selectedDiscoveryRun,
      selectedDiscoveryRunIdState,
      selectedProduct,
      selectedProductIdState,
      sourceProviders,
      activeSourceIds,
      snapshot,
    ],
  );

  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}

function dedupeContacts(contacts: DiscoveryResult[]) {
  const seen = new Set<string>();
  const deduped: DiscoveryResult[] = [];
  for (const contact of contacts) {
    const key = contactKey(contact);
    if (seen.has(key)) continue;
    seen.add(key);
    deduped.push(contact);
  }
  return deduped;
}

function contactKey(contact: DiscoveryResult) {
  const website = (contact.website_url || contact.research?.website_url || "").trim().toLowerCase();
  if (website) return `website:${website.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}`;
  return `name:${contact.company_name.trim().toLowerCase()}|${(contact.geography || contact.research?.geography || "").trim().toLowerCase()}`;
}

export function useAppData() {
  const value = useContext(AppDataContext);
  if (!value) {
    throw new Error("useAppData must be used inside AppDataProvider");
  }
  return value;
}
