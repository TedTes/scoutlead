import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  Check,
  Copy,
  Download,
  ExternalLink,
  Globe,
  Mail,
  MapPin,
  MoreVertical,
  Pause,
  Phone,
  Play,
  PlugZap,
  Plus,
  RotateCw,
  Search,
  Send,
  Sparkles,
  Star,
  Trash2,
  User,
  Users,
  Workflow,
  X,
} from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { createPortal } from "react-dom";
import { AudienceProfileScreen } from "./AudienceProfileScreen";
import { searchIntentFromRun } from "../components/SearchIntentChips";
import { ExportContactsDialog, Modal, useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type {
  AgentFitStatus,
  CampaignMessageBatchResult,
  CampaignOutreachDraftInput,
  ContactPolicyStatus,
  ContactVerificationStatus,
  DiscoveryResult,
  LeadContactPolicyInput,
  LeadReviewStatus,
  LeadUpdateInput,
  LeadOutcomeValue,
  Message,
  Product,
  SenderProfile,
  SearchIntent,
  Territory,
  TerritoryDelivery,
  TerritoryMetrics,
  TerritoryResolution,
} from "../types/domain";
import {
  baseExportFileName,
  defaultExportFileName,
  exportContactEmail,
  normalizeExportFileName,
} from "../utils/export-file";
import { formatDate } from "../utils/format";
import type { LeadWorkflowCounts, LeadWorkflowView } from "../types/navigation";

type DrawerTab = "overview" | "evidence";
type ContactActivityTone = "done" | "pending" | "warning" | "blocked";
type ContactActivityItem = {
  label: string;
  detail: string;
  complete: boolean;
  tone: ContactActivityTone;
};
type PendingContactsExport = {
  contacts: DiscoveryResult[];
  suggestedName: string;
};
const bulkOutreachDefaultSubject = "Quick question for {{business_name}}";
const bulkOutreachDefaultBody = `Hello {{recipient_name}},

I'm reaching out from {{product_name}}. We're building a tool for {{problem}}.

Would something like this be useful for {{business_name}}?

Best,
Tedros`;
const bulkOutreachTokens = [
  "{{business_name}}",
  "{{recipient_name}}",
  "{{geography}}",
  "{{fit_reason}}",
  "{{product_name}}",
  "{{problem}}",
];
const leadOutcomeOptions: Array<{ value: LeadOutcomeValue; label: string }> = [
  { value: "contacted", label: "Contacted" },
  { value: "replied_positive", label: "Positive reply" },
  { value: "replied_negative", label: "Negative reply" },
  { value: "meeting_booked", label: "Meeting booked" },
  { value: "won", label: "Won" },
  { value: "no_response", label: "No response" },
  { value: "not_a_fit", label: "Not a fit" },
  { value: "wrong_contact", label: "Wrong contact" },
  { value: "bounced", label: "Bounced" },
  { value: "business_closed", label: "Business closed" },
  { value: "unsubscribed", label: "Unsubscribed" },
];
type BulkEmailOverride = {
  subject: string;
  body: string;
};

export function ResultsScreen({
  onWorkflowViewChange,
  onWorkflowCountsChange,
  onCreateAudience,
  workflowView,
}: {
  onWorkflowViewChange: (view: LeadWorkflowView) => void;
  onWorkflowCountsChange?: (runId: string, counts: LeadWorkflowCounts) => void;
  onCreateAudience?: () => void;
  workflowView: LeadWorkflowView;
}) {
  const {
    runSourceRequest,
    selectedDiscoveryRun,
    selectedDiscoveryRunId,
    selectedProduct,
    selectedProductId,
    selectedProfileId,
    profileBatch,
    setSelectedDiscoveryRunId,
    deleteDiscoveryRuns,
    renameDiscoveryRun,
    qualifyLead,
    updateLead,
    updateLeadContactPolicy,
    draftShortlist,
    createOutreachDraft,
    updateMessage,
    approveMessage,
    sendMessage,
    gmailConnectionStatus,
    markMessageReplied,
    sendApprovedShortlistWebhook,
    createCampaignOutreachDrafts,
    approveCampaignOutreachDrafts,
    sendCampaignOutreachDrafts,
    snapshot,
    territories,
    territoryApi,
    refillProfile,
    refreshAll,
    refreshSnapshot,
  } = useAppData();
  const { showToast } = useToast();
  const [selectedContactId, setSelectedContactId] = useState("");
  const [detailPanelOpen, setDetailPanelOpen] = useState(true);
  const [leadSearch, setLeadSearch] = useState("");
  const [desktopSplitView, setDesktopSplitView] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia("(min-width: 1160px)").matches : false,
  );
  const [draftPrompt, setDraftPrompt] = useState("");
  const [editedSearchIntent, setEditedSearchIntent] = useState<SearchIntent | null>(null);
  const [running, setRunning] = useState(false);
  const [draftingShortlist, setDraftingShortlist] = useState(false);
  const [sendingWebhook, setSendingWebhook] = useState(false);
  const [runMenuOpen, setRunMenuOpen] = useState(false);
  const [bulkOutreachOpen, setBulkOutreachOpen] = useState(false);
  const [rerunPromptOpen, setRerunPromptOpen] = useState(false);
  const [scheduleDialogOpen, setScheduleDialogOpen] = useState(false);
  const [profileDetailsOpen, setProfileDetailsOpen] = useState(false);
  const [scheduleResolution, setScheduleResolution] = useState<TerritoryResolution | null>(null);
  const [scheduleBusy, setScheduleBusy] = useState(false);
  const [deliveries, setDeliveries] = useState<TerritoryDelivery[]>([]);
  const [deliveryContacts, setDeliveryContacts] = useState<DiscoveryResult[] | null>(null);
  const [territoryMetrics, setTerritoryMetrics] = useState<TerritoryMetrics | null>(null);
  const [exportingDelivery, setExportingDelivery] = useState(false);
  const [pendingExport, setPendingExport] = useState<PendingContactsExport | null>(null);
  const [exportFileName, setExportFileName] = useState("");
  const [bulkPopoverStyle, setBulkPopoverStyle] = useState<CSSProperties>({});
  const runMenuRef = useRef<HTMLDivElement | null>(null);
  const bulkOutreachRef = useRef<HTMLDivElement | null>(null);
  const bulkOutreachButtonRef = useRef<HTMLButtonElement | null>(null);
  const bulkOutreachPopoverRef = useRef<HTMLDivElement | null>(null);

  const selectedTerritory = selectedDiscoveryRun?.territory_id
    ? territories.find((territory) => territory.id === selectedDiscoveryRun.territory_id)
    : undefined;
  const activeProfile = territories.find((profile) => profile.id === selectedProfileId)
    || selectedTerritory;
  const selectedDelivery = selectedTerritory
    ? deliveries.find((delivery) => delivery.campaign_id === selectedDiscoveryRunId)
    : undefined;
  const visibleProfileBatch =
    profileBatch?.profile.id === selectedProfileId
    && (!selectedDelivery || profileBatch.delivery?.id === selectedDelivery.id)
      ? profileBatch
      : null;
  const isProfileAggregate = Boolean(visibleProfileBatch);
  const isAudienceView = Boolean(
    activeProfile && (isProfileAggregate || (!selectedDiscoveryRun && selectedProfileId)),
  );
  const sourceContacts = visibleProfileBatch
    ? visibleProfileBatch.leads
    : selectedDiscoveryRunId
      ? selectedDelivery && deliveryContacts ? deliveryContacts : snapshot.results
      : [];
  const contacts = useMemo(() => deduplicateContacts(sourceContacts), [sourceContacts]);
  const isDeliveryScoped = Boolean(!isProfileAggregate && selectedDelivery && deliveryContacts);
  const thisWeekCutoffMs = Date.now() - 7 * 24 * 60 * 60 * 1000;
  const runPrompt = getRunPrompt(selectedDiscoveryRun);
  const query = runPrompt;
  const activeMessages = snapshot.messages.filter((message) => message.status !== "cancelled");
  const messageByLeadId = new Map(activeMessages.map((message) => [message.lead_id, message]));
  const approvedLeadIds = new Set(
    activeMessages
      .filter((message) => message.status === "approved" || message.status === "sent")
      .map((message) => message.lead_id),
  );
  const shortlistedContactRows = contacts.filter((contact) => contact.shortlisted_at);
  const shortlistedContacts = shortlistedContactRows.length;
  const draftedLeadIds = new Set(activeMessages.map((message) => message.lead_id));
  const approvedShortlistContacts = contacts.filter(
    (contact) => contact.shortlisted_at && approvedLeadIds.has(contact.id),
  );
  const webhookReady = Boolean(
    selectedProduct?.webhook_enabled && selectedProduct.webhook_url && approvedShortlistContacts.length,
  );
  const gmailConnected = Boolean(gmailConnectionStatus?.connected);
  const draftableShortlistContacts = contacts.filter(
    (contact) => contact.shortlisted_at && isVerifiedContact(contact) && canShortlistContact(contact) && !draftedLeadIds.has(contact.id),
  );
  const outreachReadyContacts = shortlistedContactRows.filter(isBulkOutreachReadyContact);
  const outreachSkippedContacts = shortlistedContactRows.filter((contact) => !isBulkOutreachReadyContact(contact));
  const workflowContext = {
    includeAllLeads: isProfileAggregate || isDeliveryScoped,
    thisWeekCutoffMs,
  };
  const workflowCounts = useMemo<LeadWorkflowCounts>(() => ({
    inbox: contacts.filter((contact) => matchesWorkflowView(contact, "inbox", workflowContext)).length,
    this_week: contacts.filter((contact) => matchesWorkflowView(contact, "this_week", workflowContext)).length,
    shortlisted: contacts.filter((contact) => matchesWorkflowView(contact, "shortlisted", workflowContext)).length,
    contacted: contacts.filter((contact) => matchesWorkflowView(contact, "contacted", workflowContext)).length,
    dismissed: contacts.filter((contact) => matchesWorkflowView(contact, "dismissed", workflowContext)).length,
    all: contacts.length,
  }), [contacts, isDeliveryScoped, isProfileAggregate, thisWeekCutoffMs]);
  const workflowContacts = contacts.filter((contact) =>
    matchesWorkflowView(contact, workflowView, workflowContext),
  );
  const visibleContacts = workflowContacts
    .filter((contact) => {
      const needle = leadSearch.trim().toLowerCase();
      if (!needle) return true;
      return [
        contact.company_name,
        contactListCategoryLabel(contact),
        contact.geography,
        contact.research?.geography,
        contactOpportunityReasons(contact).join(" "),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(needle);
    })
    .sort((a, b) =>
      contactOpportunityAssessment(b).score - contactOpportunityAssessment(a).score
      || contactScore(b) - contactScore(a),
    );
  const exportName = selectedDiscoveryRun?.name || selectedProduct?.product_name || "contacts";
  const selectedContact = detailPanelOpen
    ? contacts.find((contact) => contact.id === selectedContactId)
    : undefined;
  const selectedMessage = selectedContact
    ? messageByLeadId.get(selectedContact.outreach_lead_id || selectedContact.id)
    : undefined;
  useEffect(() => {
    const scopeId = selectedDiscoveryRunId
      || visibleProfileBatch?.audience_run_id
      || selectedProfileId;
    if (!scopeId || !onWorkflowCountsChange) return;
    onWorkflowCountsChange(scopeId, workflowCounts);
  }, [
    onWorkflowCountsChange,
    selectedDiscoveryRunId,
    selectedProfileId,
    visibleProfileBatch?.audience_run_id,
    workflowCounts,
  ]);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1160px)");
    const update = () => setDesktopSplitView(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!desktopSplitView || !detailPanelOpen) return;
    if (!visibleContacts.length) {
      setSelectedContactId("");
      return;
    }
    if (!visibleContacts.some((contact) => contact.id === selectedContactId)) {
      setSelectedContactId(visibleContacts[0].id);
    }
  }, [desktopSplitView, detailPanelOpen, selectedContactId, visibleContacts.map((contact) => contact.id).join("|")]);

  useEffect(() => {
    document.body.classList.toggle("has-contact-detail", Boolean(selectedContact));
    return () => document.body.classList.remove("has-contact-detail");
  }, [selectedContact]);

  useEffect(() => {
    setDraftPrompt(runPrompt);
    const savedIntent = searchIntentFromRun(selectedDiscoveryRun);
    setEditedSearchIntent(savedIntent);
    setSelectedContactId("");
    setDetailPanelOpen(true);
    setLeadSearch("");
    onWorkflowViewChange("this_week");
    setRerunPromptOpen(false);
    setBulkOutreachOpen(false);
  }, [onWorkflowViewChange, selectedDiscoveryRunId, runPrompt]);

  useEffect(() => {
    if (!selectedTerritory) {
      setDeliveries([]);
      setDeliveryContacts(null);
      setTerritoryMetrics(null);
      return;
    }
    void Promise.all([
      territoryApi.getTerritoryDeliveries(selectedTerritory.id),
      territoryApi.getTerritoryMetrics(selectedTerritory.id),
    ]).then(([nextDeliveries, nextMetrics]) => {
      setDeliveries(nextDeliveries);
      setTerritoryMetrics(nextMetrics);
    }).catch(() => {
      setDeliveries([]);
      setTerritoryMetrics(null);
    });
  }, [selectedTerritory?.id, territoryApi]);

  useEffect(() => {
    setDeliveryContacts(null);
    if (!selectedTerritory || !selectedDelivery) return;
    void territoryApi
      .getTerritoryDeliveryContacts(selectedTerritory.id, selectedDelivery.id)
      .then((nextContacts) => {
        setDeliveryContacts(nextContacts);
        if (!selectedDelivery.viewed_at) void refreshAll({ showLoading: false });
      })
      .catch(() => setDeliveryContacts(null));
  }, [refreshAll, selectedDelivery?.id, selectedTerritory?.id, territoryApi]);

  useEffect(() => {
    setRunMenuOpen(false);
  }, [selectedDiscoveryRunId]);

  useEffect(() => {
    if (workflowView !== "shortlisted") setBulkOutreachOpen(false);
  }, [workflowView]);

  useEffect(() => {
    if (!runMenuOpen && !bulkOutreachOpen) return undefined;
    const closeMenus = (event: MouseEvent) => {
      if (!runMenuRef.current?.contains(event.target as Node)) {
        setRunMenuOpen(false);
      }
      if (
        !bulkOutreachRef.current?.contains(event.target as Node)
        && !bulkOutreachPopoverRef.current?.contains(event.target as Node)
      ) {
        setBulkOutreachOpen(false);
      }
    };
    document.addEventListener("mousedown", closeMenus);
    return () => document.removeEventListener("mousedown", closeMenus);
  }, [bulkOutreachOpen, runMenuOpen]);

  useEffect(() => {
    // Freezes the underlying results list while the popup is open so it
    // behaves like a centered modal layer instead of moving with the page.
    if (!bulkOutreachOpen) return undefined;
    const contentEl = document.querySelector(".content");
    contentEl?.classList.add("scroll-locked");
    return () => contentEl?.classList.remove("scroll-locked");
  }, [bulkOutreachOpen]);

  useLayoutEffect(() => {
    if (!bulkOutreachOpen) return undefined;
    const BULK_POPOVER_MAX_WIDTH = 1080;
    const positionPopover = () => {
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;
      const gutter = viewportWidth <= 680 ? 10 : 18;
      const verticalInset = 2;
      const maxWidth = Math.max(0, viewportWidth - gutter * 2);
      const width = Math.min(BULK_POPOVER_MAX_WIDTH, maxWidth);
      const maxHeight = Math.min(820, Math.max(240, viewportHeight - verticalInset * 2));
      setBulkPopoverStyle({
        left: Math.round((viewportWidth - width) / 2),
        maxHeight: Math.round(maxHeight),
        top: Math.max(verticalInset, Math.round((viewportHeight - maxHeight) / 2)),
        width: Math.round(width),
      });
    };
    positionPopover();
    window.addEventListener("resize", positionPopover);
    return () => window.removeEventListener("resize", positionPopover);
  }, [bulkOutreachOpen]);

  const updateSearch = async () => {
    const request = draftPrompt.trim() || runPrompt;
    if (running) return;
    if (!selectedProductId) {
      showToast({ title: "Select a product", message: "Create or choose a product before re-running discovery.", tone: "amber" });
      return;
    }
    if (request.length < 4) {
      showToast({ title: "Enter a search prompt", message: "Describe the businesses to find before re-running discovery.", tone: "amber" });
      return;
    }
    setRunning(true);
    showToast({
      title: "Search started",
      message: "Checking the current business index. Unmet demand will guide the next scheduled refresh.",
      tone: "blue",
    });
    try {
      const result = await runSourceRequest({
        product_id: selectedProductId,
        source: "auto",
        name: selectedDiscoveryRun?.name || undefined,
        prompt: request,
        max_results: requestedResultCount(selectedDiscoveryRun),
        run_immediately: true,
        intent_override: editedSearchIntent || undefined,
      });
      if (result) {
        setRerunPromptOpen(false);
        const foundCount = result.current_result_count;
        const criteriaMessage = result.unsupported_criteria.length
          ? `Not evaluated: ${result.unsupported_criteria.join(", ")}.`
          : result.unresolved_criteria.length
            ? `Current evidence is missing for: ${result.unresolved_criteria.join(", ")}.`
            : "";
        showToast({
          title: "Search ready",
          message: criteriaMessage || `${foundCount} indexed match${foundCount === 1 ? "" : "es"} ready.`,
          tone: criteriaMessage ? "amber" : foundCount ? "green" : "blue",
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      showToast({ title: "Search failed", message, tone: "red" });
    } finally {
      setRunning(false);
    }
  };

  const renameCurrentRun = async () => {
    if (!selectedDiscoveryRun) return;
    const nextName = window.prompt(
      "Rename search",
      selectedTerritory?.label || selectedDiscoveryRun.name || runTitle("", query),
    );
    if (!nextName?.trim()) return;
    if (selectedTerritory) {
      await territoryApi.updateTerritory(selectedTerritory.id, { label: nextName.trim() });
      await refreshAll({ showLoading: false });
    } else {
      await renameDiscoveryRun(selectedDiscoveryRun.id, nextName.trim());
    }
    setRunMenuOpen(false);
    showToast({ title: "Search renamed", tone: "green" });
  };

  const deleteCurrentRun = async () => {
    if (!selectedDiscoveryRun) return;
    const confirmed = window.confirm(`Delete ${runTitle(selectedDiscoveryRun.name || "", query)}? This removes the saved results for this run.`);
    if (!confirmed) return;
    await deleteDiscoveryRuns([selectedDiscoveryRun.id]);
    setSelectedDiscoveryRunId("");
    setRunMenuOpen(false);
    showToast({ title: "Run deleted", message: "The saved contact list was removed.", tone: "green" });
  };

  const openRerunPrompt = () => {
    if (!selectedDiscoveryRun || running) return;
    setRunMenuOpen(false);
    setDraftPrompt(runPrompt);
    setRerunPromptOpen(true);
  };

  const openScheduleDialog = async () => {
    if (!selectedDiscoveryRun || !selectedProductId || scheduleBusy) return;
    setRunMenuOpen(false);
    if (selectedTerritory) {
      setScheduleResolution(null);
      setScheduleDialogOpen(true);
      return;
    }
    if (!runPrompt.trim()) {
      showToast({ title: "Search query unavailable", message: "Re-run this search with a business type and location first.", tone: "amber" });
      return;
    }
    setScheduleBusy(true);
    try {
      const resolution = await territoryApi.resolveTerritory(selectedProductId, runPrompt);
      setScheduleResolution(resolution);
      setScheduleDialogOpen(true);
    } catch (err) {
      showToast({
        title: "Could not schedule search",
        message: err instanceof Error ? err.message : String(err),
        tone: "red",
      });
    } finally {
      setScheduleBusy(false);
    }
  };

  const saveSchedule = async (settings: {
    batch_size: number;
    min_fit: Territory["min_fit"];
    refill_policy: Territory["refill_policy"];
  }) => {
    if (!selectedDiscoveryRun || scheduleBusy) return;
    setScheduleBusy(true);
    try {
      if (selectedTerritory) {
        await territoryApi.updateTerritory(selectedTerritory.id, settings);
      } else if (scheduleResolution) {
        const contractHash = storedSearchContractHash(selectedDiscoveryRun);
        const existing = territories.find((territory) => (
          territory.product_id === selectedDiscoveryRun.product_id
          && territory.niche_id === scheduleResolution.niche_id
          && territory.market_key === scheduleResolution.market_key
          && territory.search_prompt === scheduleResolution.request
          && (!contractHash || territory.criteria_hash === contractHash)
        ));
        const scheduled = existing || await territoryApi.createTerritory(scheduleResolution, {
          batch_size: settings.batch_size,
          min_fit: settings.min_fit,
          refill_policy: settings.refill_policy,
          search_contract: storedSearchContract(selectedDiscoveryRun),
          evidence_max_age_days: storedEvidenceMaxAge(selectedDiscoveryRun),
        });
        if (existing) await territoryApi.updateTerritory(existing.id, settings);
        await territoryApi.updateDiscoveryRun(selectedDiscoveryRun.id, { territory_id: scheduled.id });
      } else {
        return;
      }
      await refreshAll({ showLoading: false });
      setScheduleDialogOpen(false);
      showToast({ title: selectedTerritory ? "Audience updated" : "Audience schedule created", tone: "green" });
    } catch (err) {
      showToast({
        title: "Schedule update failed",
        message: err instanceof Error ? err.message : String(err),
        tone: "red",
      });
    } finally {
      setScheduleBusy(false);
    }
  };

  const toggleSchedule = async () => {
    if (!selectedTerritory || scheduleBusy) return;
    setScheduleBusy(true);
    try {
      const status = selectedTerritory.status === "active" ? "paused" : "active";
      await territoryApi.updateTerritory(selectedTerritory.id, { status });
      await refreshAll({ showLoading: false });
      setRunMenuOpen(false);
      showToast({ title: status === "active" ? "Audience resumed" : "Audience paused", tone: "green" });
    } catch (err) {
      showToast({ title: "Schedule update failed", message: err instanceof Error ? err.message : String(err), tone: "red" });
    } finally {
      setScheduleBusy(false);
    }
  };

  const runScheduledSearchNow = async () => {
    if (!selectedTerritory || selectedTerritory.status !== "active" || scheduleBusy) return;
    setScheduleBusy(true);
    try {
      await territoryApi.refreshTerritory(selectedTerritory.id);
      setRunMenuOpen(false);
      showToast({
        title: "Batch queued",
        message: "Scoring runs in the background. New leads will appear when the batch is ready.",
        tone: "blue",
      });
    } catch (err) {
      showToast({ title: "Batch request failed", message: err instanceof Error ? err.message : String(err), tone: "red" });
    } finally {
      setScheduleBusy(false);
    }
  };

  const recordContactOutcome = async (leadId: string, outcome: LeadOutcomeValue) => {
    await territoryApi.recordLeadOutcome(leadId, outcome, outcome === "contacted" ? "email" : "other");
    await refreshAll({ showLoading: false });
    if (selectedTerritory) {
      await territoryApi.getTerritoryMetrics(selectedTerritory.id).then(setTerritoryMetrics);
    }
  };

  const generateContactApproach = async (leadId: string) => {
    const updated = await territoryApi.generateLeadApproach(leadId);
    setDeliveryContacts((current) => (
      current?.map((contact) => contact.id === updated.id ? updated : contact) || current
    ));
    await refreshAll({ showLoading: false });
  };

  const draftCurrentShortlist = async () => {
    if (!selectedDiscoveryRun || draftingShortlist) return;
    setDraftingShortlist(true);
    try {
      const created = await draftShortlist(selectedDiscoveryRun.id);
      setRunMenuOpen(false);
      showToast({
        title: created.length ? "Drafts created" : "No new drafts",
        message: created.length
          ? `${created.length} shortlisted contact${created.length === 1 ? "" : "s"} now have drafts.`
          : "No verified shortlisted contacts needed a new draft.",
        tone: created.length ? "green" : "amber",
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      showToast({ title: "Drafting failed", message, tone: "red" });
    } finally {
      setDraftingShortlist(false);
    }
  };

  const sendCurrentApprovedShortlistWebhook = async () => {
    if (!selectedDiscoveryRun || sendingWebhook) return;
    setSendingWebhook(true);
    try {
      await sendApprovedShortlistWebhook(selectedDiscoveryRun.id);
      setRunMenuOpen(false);
      showToast({
        title: "Webhook sent",
        message: `${approvedShortlistContacts.length} approved contact${
          approvedShortlistContacts.length === 1 ? "" : "s"
        } delivered.`,
        tone: "green",
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      showToast({ title: "Webhook failed", message, tone: "red" });
    } finally {
      setSendingWebhook(false);
    }
  };

  const runActiveAudienceAgain = async () => {
    if (!activeProfile || scheduleBusy) return;
    setScheduleBusy(true);
    try {
      await refillProfile(activeProfile.id);
      setRunMenuOpen(false);
      showToast({
        title: "Audience queued",
        message: "ScoutLead is checking the published business index for the next batch.",
        tone: "blue",
      });
    } catch (err) {
      showToast({
        title: "Audience could not run",
        message: err instanceof Error ? err.message : String(err),
        tone: "red",
      });
    } finally {
      setScheduleBusy(false);
    }
  };

  const beginContactsExport = (contactsToExport: DiscoveryResult[], name: string, suffix = "contacts") => {
    if (!contactsToExport.length) {
      showToast({ title: "No contacts to export", message: "Change the view or run a search first.", tone: "amber" });
      return;
    }
    const suggestedName = defaultExportFileName(name, suffix);
    setRunMenuOpen(false);
    setExportFileName(suggestedName);
    setPendingExport({ contacts: contactsToExport, suggestedName });
  };

  const exportCurrentContacts = async () => {
    if (!selectedTerritory || !selectedDelivery) {
      beginContactsExport(contacts, exportName);
      return;
    }
    if (exportingDelivery) return;
    setExportingDelivery(true);
    setRunMenuOpen(false);
    try {
      const blob = await territoryApi.downloadTerritoryDeliveryCsv(selectedTerritory.id, selectedDelivery.id);
      downloadBlob(blob, defaultExportFileName(selectedTerritory.label, "call-sheet"));
      showToast({ title: "Call sheet exported", message: `${contacts.length} contacts downloaded.`, tone: "green" });
    } catch (err) {
      showToast({ title: "Export failed", message: err instanceof Error ? err.message : String(err), tone: "red" });
    } finally {
      setExportingDelivery(false);
    }
  };

  const confirmContactsExport = () => {
    if (!pendingExport) return;
    if (!baseExportFileName(exportFileName)) {
      showToast({ title: "Name the export file", message: "Enter a filename before exporting.", tone: "amber" });
      return;
    }
    const downloadName = normalizeExportFileName(exportFileName);
    exportContactsCsv(pendingExport.contacts, downloadName);
    setPendingExport(null);
    showToast({
      title: "Contacts exported",
      message: `${pendingExport.contacts.length} contacts downloaded as ${downloadName}.`,
      tone: "green",
    });
  };

  if (!selectedDiscoveryRun && !activeProfile) {
    return <AudienceProfileScreen />;
  }

  return (
    <section className={selectedContact ? "results-workspace has-detail" : "results-workspace"}>
      <div className="results-controlbar">
        {activeProfile ? (
          <nav aria-label="Audience context" className="results-breadcrumb">
            <span>Audiences</span>
            <span aria-hidden="true">/</span>
            <button type="button" onClick={() => setProfileDetailsOpen(true)}>
              {activeProfile.label}
            </button>
          </nav>
        ) : null}
        <div className="results-control-actions">
          {onCreateAudience ? (
            <button
              aria-label="New audience"
              className="secondary results-new-audience-button"
              title="New audience"
              type="button"
              onClick={onCreateAudience}
            >
              <Plus size={14} />
              <span>New audience</span>
            </button>
          ) : null}
          <div className="results-menu-control" ref={runMenuRef}>
            <button
              aria-expanded={runMenuOpen}
              aria-label="Run actions"
              className="menu-button"
              type="button"
              onClick={() => {
                setBulkOutreachOpen(false);
                setRunMenuOpen((open) => !open);
              }}
            >
              <MoreVertical size={18} />
            </button>
            {runMenuOpen ? (
              <div className="action-menu">
                {isAudienceView && activeProfile ? (
                  <div className="run-menu-summary">
                    <strong>{refillPolicyLabel(activeProfile.refill_policy)} · {activeProfile.status}</strong>
                    <span>{visibleProfileBatch?.result_count || 0} leads in the current batch</span>
                  </div>
                ) : selectedTerritory ? (
                  <div className="run-menu-summary">
                    <strong>{refillPolicyLabel(selectedTerritory.refill_policy)} · {selectedTerritory.status}</strong>
                    <span>
                      Next {formatCompactDate(selectedTerritory.next_run_at)}
                      {territoryMetrics ? ` · ${territoryMetrics.totals.delivered} delivered · ${territoryMetrics.totals.meetings} meetings` : ""}
                    </span>
                  </div>
                ) : null}
                {isAudienceView && activeProfile ? (
                  <>
                    <button
                      type="button"
                      disabled={scheduleBusy || activeProfile.status !== "active"}
                      onClick={() => void runActiveAudienceAgain()}
                    >
                      <RotateCw size={14} />
                      {scheduleBusy ? "Queueing..." : "Run again"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setRunMenuOpen(false);
                        setProfileDetailsOpen(true);
                      }}
                    >
                      <CalendarClock size={14} />
                      Audience details
                    </button>
                    <div className="action-menu-divider" />
                  </>
                ) : selectedTerritory ? (
                  <>
                    <button
                      type="button"
                      disabled={scheduleBusy || selectedTerritory.status !== "active"}
                      onClick={() => void runScheduledSearchNow()}
                    >
                      <Play size={14} />
                      {scheduleBusy ? "Queueing..." : "Refill now"}
                    </button>
                    <button type="button" disabled={scheduleBusy} onClick={() => void toggleSchedule()}>
                      {selectedTerritory.status === "active" ? <Pause size={14} /> : <Play size={14} />}
                      {selectedTerritory.status === "active" ? "Pause audience" : "Resume audience"}
                    </button>
                    <button type="button" disabled={scheduleBusy} onClick={() => void openScheduleDialog()}>
                      <CalendarClock size={14} />
                      Audience settings
                    </button>
                    <div className="action-menu-divider" />
                  </>
                ) : (
                  <>
                    <button type="button" disabled={scheduleBusy || !runPrompt.trim()} onClick={() => void openScheduleDialog()}>
                      <CalendarClock size={14} />
                      {scheduleBusy ? "Checking search..." : "Create audience schedule"}
                    </button>
                    <div className="action-menu-divider" />
                  </>
                )}
                <button
                  type="button"
                  disabled={!contacts.length || exportingDelivery}
                  onClick={() => void exportCurrentContacts()}
                >
                  <Download size={14} />
                  {selectedDelivery ? "Export call sheet" : "Export all contacts"}
                </button>
                <button
                  type="button"
                  disabled={!shortlistedContacts}
                  onClick={() =>
                    beginContactsExport(
                      contacts.filter((contact) => contact.shortlisted_at),
                      exportName,
                      "shortlist",
                    )
                  }
                >
                  <Download size={14} />
                  Export shortlist
                </button>
                <button
                  type="button"
                  disabled={!approvedShortlistContacts.length}
                  onClick={() => beginContactsExport(approvedShortlistContacts, exportName, "approved-shortlist")}
                >
                  <Download size={14} />
                  Export approved shortlist
                </button>
                <button
                  type="button"
                  disabled={!webhookReady || sendingWebhook}
                  onClick={() => void sendCurrentApprovedShortlistWebhook()}
                >
                  <PlugZap size={14} />
                  {sendingWebhook ? "Sending webhook..." : "Send approved to webhook"}
                </button>
                <button
                  type="button"
                  disabled={!selectedDiscoveryRun || !draftableShortlistContacts.length || draftingShortlist}
                  onClick={() => void draftCurrentShortlist()}
                >
                  <Mail size={14} />
                  Generate drafts for shortlist
                </button>
                {selectedDiscoveryRun ? (
                  <>
                    <button type="button" onClick={() => void renameCurrentRun()}>
                      Rename search
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setRunMenuOpen(false);
                        window.location.assign(`/trace?run=${encodeURIComponent(selectedDiscoveryRunId)}`);
                      }}
                    >
                      <Workflow size={14} />
                      Inspect run
                    </button>
                  </>
                ) : null}
                {!selectedTerritory && !isAudienceView ? (
                  <button type="button" disabled={running} onClick={openRerunPrompt}>
                    <RotateCw size={14} />
                    Re-run search
                  </button>
                ) : null}
                {!selectedTerritory && !isAudienceView ? (
                  <button className="danger-item" type="button" onClick={() => void deleteCurrentRun()}>
                    <Trash2 size={14} />
                    Delete this search
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className={selectedContact ? "results-body has-detail" : "results-body"}>
        <section className="lead-feed-pane" aria-label="Lead list">
          <header className="lead-feed-header">
            <div className="lead-feed-title-row">
              <div>
                <strong>
                  {isProfileAggregate && workflowView === "this_week"
                    ? "Leads"
                    : workflowViewLabel(workflowView)}
                </strong>
                <span>
                  {visibleContacts.length === workflowContacts.length
                    ? workflowContacts.length
                    : `${visibleContacts.length} of ${workflowContacts.length}`}
                </span>
              </div>
              <div className="lead-feed-header-actions">
                {workflowView === "shortlisted" && outreachReadyContacts.length ? (
                  <div className="bulk-outreach-control" ref={bulkOutreachRef}>
                    <button
                      aria-expanded={bulkOutreachOpen}
                      aria-haspopup="dialog"
                      className={bulkOutreachOpen ? "secondary outreach-toolbar-button active" : "secondary outreach-toolbar-button"}
                      ref={bulkOutreachButtonRef}
                      type="button"
                      onClick={() => {
                        setRunMenuOpen(false);
                        setBulkOutreachOpen((open) => !open);
                      }}
                    >
                      <Users size={14} />
                      <span className="outreach-label">Prepare outreach</span>
                      <span className="outreach-count">{outreachReadyContacts.length}</span>
                    </button>
                    {bulkOutreachOpen
                      ? createPortal(
                          <>
                            <div
                              className="bulk-outreach-backdrop"
                              role="presentation"
                              onMouseDown={() => setBulkOutreachOpen(false)}
                            />
                            <div className="bulk-outreach-popover" ref={bulkOutreachPopoverRef} style={bulkPopoverStyle}>
                              <BulkOutreachPanel
                                gmailConnected={gmailConnected}
                                product={selectedProduct}
                                readyContacts={outreachReadyContacts}
                                skippedContacts={outreachSkippedContacts}
                                onApproveDrafts={approveCampaignOutreachDrafts}
                                onClose={() => setBulkOutreachOpen(false)}
                                onCreateDrafts={createCampaignOutreachDrafts}
                                onSendDrafts={sendCampaignOutreachDrafts}
                                onUpdateMessage={updateMessage}
                              />
                            </div>
                          </>,
                          document.body,
                        )
                      : null}
                  </div>
                ) : null}
              </div>
            </div>
            <label className="lead-feed-search">
              <Search size={15} aria-hidden="true" />
              <input
                aria-label="Search leads"
                placeholder="Search leads"
                value={leadSearch}
                onChange={(event) => setLeadSearch(event.target.value)}
              />
            </label>
          </header>
          {visibleContacts.length ? (
            <ul className="contact-card-list">
              {visibleContacts.map((contact) => (
                <ContactCard
                  contact={contact}
                  key={contact.id}
                  selected={contact.id === selectedContactId}
                  onOpen={() => {
                    setSelectedContactId(contact.id);
                    setDetailPanelOpen(true);
                  }}
                  onToggleShortlist={() => void updateLead(contact.id, { shortlisted: !contact.shortlisted_at })}
                />
              ))}
            </ul>
          ) : (
            <section className="result-empty-card">
              <strong>{emptyBatchCopy(contacts.length, visibleProfileBatch?.state, visibleProfileBatch?.failure_class).title}</strong>
              <p>{emptyBatchCopy(contacts.length, visibleProfileBatch?.state, visibleProfileBatch?.failure_class).detail}</p>
            </section>
          )}
        </section>

        {selectedContact ? (
          <ContactDrawer
            contact={selectedContact}
            persistent={desktopSplitView}
            message={selectedMessage}
            gmailConnected={gmailConnected}
            onClose={() => setDetailPanelOpen(false)}
            onApproveMessage={approveMessage}
            onCreateDraft={createOutreachDraft}
            onQualifyLead={qualifyLead}
            onMarkMessageReplied={markMessageReplied}
            onGenerateApproach={activeProfile ? generateContactApproach : undefined}
            onRecordOutcome={recordContactOutcome}
            onSendMessage={sendMessage}
            onUpdateContactPolicy={updateLeadContactPolicy}
            onUpdateLead={updateLead}
            onUpdateMessage={updateMessage}
          />
        ) : null}
      </div>

      {pendingExport ? (
        <ExportContactsDialog
          contactCount={pendingExport.contacts.length}
          fileName={exportFileName}
          placeholder={pendingExport.suggestedName}
          previewFileName={
            baseExportFileName(exportFileName) ? normalizeExportFileName(exportFileName) : "filename.csv"
          }
          onChange={setExportFileName}
          onClose={() => setPendingExport(null)}
          onExport={confirmContactsExport}
        />
      ) : null}
      {rerunPromptOpen ? (
        <RerunSearchDialog
          prompt={draftPrompt}
          running={running}
          ready={Boolean(selectedProductId && draftPrompt.trim().length >= 4)}
          onChange={(value) => {
            setDraftPrompt(value);
            setEditedSearchIntent(null);
          }}
          onClose={() => setRerunPromptOpen(false)}
          onSubmit={updateSearch}
        />
      ) : null}
      {scheduleDialogOpen ? (
        <ScheduleSearchDialog
          busy={scheduleBusy}
          resolution={scheduleResolution}
          territory={selectedTerritory}
          onClose={() => setScheduleDialogOpen(false)}
          onSave={saveSchedule}
        />
      ) : null}
      {profileDetailsOpen && activeProfile ? (
        <AudienceDetailsDialog
          profile={activeProfile}
          onClose={() => setProfileDetailsOpen(false)}
        />
      ) : null}
    </section>
  );
}

function AudienceDetailsDialog({ profile, onClose }: { profile: Territory; onClose: () => void }) {
  const tradeLabels = profile.trade_keys.map((key) => profileTradeLabel(key));
  const signalLabels = profile.signal_keys.map((key) => profileSignalLabel(key));
  const exclusionLabels = profile.exclusion_keys.map((key) => profileExclusionLabel(key));
  return (
    <Modal title="Audience profile" onClose={onClose}>
      <div className="audience-profile-details">
        <header>
          <strong>{profile.label}</strong>
          <span className={`audience-profile-status is-${profile.status}`}>{profile.status}</span>
        </header>
        <dl>
          <div><dt>Business type</dt><dd>{tradeLabels.join(", ") || "Any supported type"}</dd></div>
          <div><dt>Customer kind</dt><dd>{profileValueLabel(profile.customer_kind)}</dd></div>
          <div><dt>Market</dt><dd>{profile.city} · {profile.radius_km} km</dd></div>
          <div><dt>Batch size</dt><dd>{profile.batch_size} leads</dd></div>
          <div><dt>Refill</dt><dd>{refillPolicyLabel(profile.refill_policy)}</dd></div>
        </dl>
        <section>
          <span>Opportunity signals</span>
          <p>{signalLabels.join(", ") || "No opportunity signal required"}</p>
        </section>
        <section>
          <span>Excluded businesses</span>
          <p>{exclusionLabels.join(", ") || "None"}</p>
        </section>
      </div>
    </Modal>
  );
}

function RerunSearchDialog({
  onChange,
  onClose,
  onSubmit,
  prompt,
  ready,
  running,
}: {
  onChange: (value: string) => void;
  onClose: () => void;
  onSubmit: () => void;
  prompt: string;
  ready: boolean;
  running: boolean;
}) {
  return (
    <Modal title="Re-run search" onClose={onClose}>
      <form
        className="rerun-search-form"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <label className="field rerun-search-field">
          <span>Prompt</span>
          <textarea
            autoFocus
            aria-label="Search prompt"
            placeholder="Describe the businesses to find"
            value={prompt}
            onChange={(event) => onChange(event.target.value)}
          />
        </label>
        {running ? (
          <p className="rerun-search-status" role="status">
            Finding and scoring contacts. Keep this dialog open while the run finishes.
          </p>
        ) : null}
        <div className="dialog-actions">
          <button className="secondary" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="runbtn" disabled={!ready || running} type="submit">
            {running ? "Running..." : "Run again"}
            <ArrowRight size={13} />
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ScheduleSearchDialog({
  busy,
  onClose,
  onSave,
  resolution,
  territory,
}: {
  busy: boolean;
  onClose: () => void;
  onSave: (settings: {
    batch_size: number;
    min_fit: Territory["min_fit"];
    refill_policy: Territory["refill_policy"];
  }) => Promise<void>;
  resolution: TerritoryResolution | null;
  territory?: Territory;
}) {
  const [batchSize, setBatchSize] = useState(territory?.batch_size || 25);
  const [minFit, setMinFit] = useState<Territory["min_fit"]>(territory?.min_fit || "maybe");
  const [refillPolicy, setRefillPolicy] = useState<Territory["refill_policy"]>(territory?.refill_policy || "weekly");
  const label = territory?.label || (
    resolution ? `${resolution.niche_label} · ${resolution.market_label}` : "Audience"
  );

  return (
    <Modal title={territory ? "Audience settings" : "Schedule audience"} onClose={onClose}>
      <form
        className="schedule-search-form"
        onSubmit={(event) => {
          event.preventDefault();
          void onSave({ batch_size: batchSize, min_fit: minFit, refill_policy: refillPolicy });
        }}
      >
        <div className="schedule-search-summary">
          <CalendarClock size={17} />
          <span>
            <strong>{label}</strong>
            <small>Each batch excludes businesses already delivered to this audience.</small>
          </span>
        </div>
        <div className="schedule-search-fields">
          <label className="field">
            <span>Contacts per delivery</span>
            <input
              max={100}
              min={1}
              type="number"
              value={batchSize}
              onChange={(event) => setBatchSize(Math.max(1, Math.min(100, Number(event.target.value) || 1)))}
            />
          </label>
          <label className="field">
            <span>Refill</span>
            <select value={refillPolicy} onChange={(event) => setRefillPolicy(event.target.value as Territory["refill_policy"])}>
              <option value="when_depleted">When depleted</option>
              <option value="weekly">Weekly</option>
              <option value="biweekly">Every two weeks</option>
              <option value="monthly">Monthly</option>
              <option value="manual">Manual</option>
            </select>
          </label>
          <label className="field">
            <span>Minimum fit</span>
            <select value={minFit} onChange={(event) => setMinFit(event.target.value as Territory["min_fit"])}>
              <option value="maybe">Good and possible fit</option>
              <option value="good_fit">Good fit only</option>
            </select>
          </label>
        </div>
        <div className="dialog-actions">
          <button className="secondary" disabled={busy} type="button" onClick={onClose}>Cancel</button>
          <button className="runbtn" disabled={busy} type="submit">
            {busy ? "Saving..." : territory ? "Save settings" : "Create schedule"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function BulkOutreachPanel({
  gmailConnected,
  product,
  readyContacts,
  skippedContacts,
  onApproveDrafts,
  onClose,
  onCreateDrafts,
  onSendDrafts,
  onUpdateMessage,
}: {
  gmailConnected: boolean;
  product: Product | undefined;
  readyContacts: DiscoveryResult[];
  skippedContacts: DiscoveryResult[];
  onApproveDrafts: (input?: { message_ids?: string[]; notes?: string | null }) => Promise<CampaignMessageBatchResult | null>;
  onClose: () => void;
  onCreateDrafts: (input: CampaignOutreachDraftInput) => Promise<CampaignMessageBatchResult | null>;
  onSendDrafts: (input?: { message_ids?: string[] }) => Promise<CampaignMessageBatchResult | null>;
  onUpdateMessage: (messageId: string, update: Partial<Message>) => Promise<void>;
}) {
  const { showToast } = useToast();
  const { territoryApi } = useAppData();
  const [selectedLeadIds, setSelectedLeadIds] = useState<string[]>([]);
  const [previewLeadId, setPreviewLeadId] = useState("");
  const [subject, setSubject] = useState(bulkOutreachDefaultSubject);
  const [body, setBody] = useState(bulkOutreachDefaultBody);
  const [emailOverrides, setEmailOverrides] = useState<Record<string, BulkEmailOverride>>({});
  const [preparedResult, setPreparedResult] = useState<CampaignMessageBatchResult | null>(null);
  const [approvalResult, setApprovalResult] = useState<CampaignMessageBatchResult | null>(null);
  const [sendResult, setSendResult] = useState<CampaignMessageBatchResult | null>(null);
  const [sending, setSending] = useState(false);
  const [senderProfile, setSenderProfile] = useState<SenderProfile | null>(null);
  const selectAllRef = useRef<HTMLInputElement | null>(null);
  const selectableContacts = useMemo(() => [...readyContacts, ...skippedContacts], [readyContacts, skippedContacts]);
  const selectableContactIds = useMemo(() => selectableContacts.map((contact) => contact.id), [selectableContacts]);
  const selectableContactKey = selectableContactIds.join("|");
  const readyContactIds = useMemo(() => readyContacts.map((contact) => contact.id), [readyContacts]);
  const readyContactKey = readyContactIds.join("|");
  // Ready contacts are checked by default; not-ready contacts stay visible
  // and selectable so the API can either prepare them or return exact skip
  // reasons after the user intentionally includes them.
  const recipientContacts = selectableContacts.filter((contact) => selectedLeadIds.includes(contact.id));
  const allSelected = selectableContacts.length > 0 && selectedLeadIds.length === selectableContacts.length;
  const someSelected = selectedLeadIds.length > 0 && !allSelected;
  // Preview can show any ready contact regardless of whether it's checked -
  // it's just "what would this look like", independent of who's included.
  // An empty previewLeadId keeps the right side on the editable template.
  const previewContact = previewLeadId ? selectableContacts.find((contact) => contact.id === previewLeadId) : undefined;
  const showingTemplate = !previewContact;
  const renderedSubject = renderBulkTemplatePreview(subject, previewContact, product);
  const renderedBody = renderBulkTemplatePreview(body, previewContact, product);
  const previewOverride = previewContact ? emailOverrides[previewContact.id] : undefined;
  const previewSubject = previewOverride?.subject ?? renderedSubject;
  const previewBody = previewOverride?.body ?? renderedBody;
  const selectedOverridesValid = selectedLeadIds.every((leadId) => {
    const override = emailOverrides[leadId];
    return !override || Boolean(override.subject.trim() && override.body.trim());
  });
  const canSendSelected = Boolean(subject.trim() && body.trim() && recipientContacts.length && selectedOverridesValid && !sending);

  useEffect(() => {
    setSelectedLeadIds((current) => {
      const validCurrent = current.filter((leadId) => selectableContactIds.includes(leadId));
      return validCurrent.length ? validCurrent : readyContactIds;
    });
  }, [readyContactKey, selectableContactKey]);

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someSelected;
    }
  }, [someSelected]);

  useEffect(() => {
    void territoryApi.getSenderProfile().then(setSenderProfile).catch(() => setSenderProfile(null));
  }, [territoryApi]);

  const toggleSelectedLead = (leadId: string) => {
    setPreparedResult(null);
    setApprovalResult(null);
    setSendResult(null);
    setSelectedLeadIds((current) =>
      current.includes(leadId) ? current.filter((id) => id !== leadId) : [...current, leadId],
    );
  };

  const toggleSelectAll = () => {
    setPreparedResult(null);
    setApprovalResult(null);
    setSendResult(null);
    setSelectedLeadIds(allSelected ? [] : selectableContactIds);
  };

  const resetBatchState = () => {
    setPreparedResult(null);
    setApprovalResult(null);
    setSendResult(null);
  };

  const updatePreviewEmail = (field: keyof BulkEmailOverride, value: string) => {
    if (!previewContact) return;
    resetBatchState();
    setEmailOverrides((current) => {
      const currentOverride = current[previewContact.id] || {
        subject: previewSubject,
        body: previewBody,
      };
      return {
        ...current,
        [previewContact.id]: {
          ...currentOverride,
          [field]: value,
        },
      };
    });
  };

  const sendSelectedEmails = async () => {
    if (!canSendSelected) return;
    if (!gmailConnected) {
      showToast({
        title: "Connect Gmail first",
        message: "Selected outreach sends from the connected Gmail account.",
        tone: "amber",
      });
      return;
    }
    setSending(true);
    setPreparedResult(null);
    setApprovalResult(null);
    setSendResult(null);
    try {
      const preparedAggregate = emptyCampaignMessageBatchResult();
      const approvalAggregate = emptyCampaignMessageBatchResult();
      const sendAggregate = emptyCampaignMessageBatchResult();
      const editedIds = selectedLeadIds.filter((leadId) => Boolean(emailOverrides[leadId]));
      const defaultTemplateIds = selectedLeadIds.filter((leadId) => !emailOverrides[leadId]);

      if (defaultTemplateIds.length) {
        await prepareApproveAndSend({
          leadIds: defaultTemplateIds,
          subject: subject.trim(),
          body: body.trim(),
          onCreateDrafts,
          onApproveDrafts,
          onSendDrafts,
          onUpdateMessage,
          preparedAggregate,
          approvalAggregate,
          sendAggregate,
        });
      }

      for (const leadId of editedIds) {
        const override = emailOverrides[leadId];
        if (!override) continue;
        await prepareApproveAndSend({
          leadIds: [leadId],
          subject: override.subject.trim(),
          body: override.body.trim(),
          onCreateDrafts,
          onApproveDrafts,
          onSendDrafts,
          onUpdateMessage,
          preparedAggregate,
          approvalAggregate,
          sendAggregate,
        });
      }

      setPreparedResult(preparedAggregate);
      setApprovalResult(approvalAggregate);
      setSendResult(sendAggregate);

      const skippedCount = preparedAggregate.skipped.length + approvalAggregate.skipped.length + sendAggregate.skipped.length;
      const failedCount = sendAggregate.failed_count;
      const sentCount = sendAggregate.sent_count;
      showToast({
        title: sentCount ? "Emails sent" : "No emails sent",
        message: `${sentCount} sent · ${skippedCount} skipped${failedCount ? ` · ${failedCount} failed` : ""}`,
        tone: sentCount ? "green" : "amber",
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      showToast({ title: "Sending failed", message, tone: "red" });
    } finally {
      setSending(false);
    }
  };

  return (
    <section className="bulk-outreach-panel">
      <header className="bulk-outreach-header">
        <div>
          <strong>Send outreach</strong>
          <p>
            Select contacts, review the email, then send from your connected Gmail.
          </p>
        </div>
        <button className="link-button" type="button" aria-label="Close outreach batch" onClick={onClose}>
          <X size={17} />
        </button>
      </header>

      <div className="bulk-outreach-workspace">
        <section className="bulk-outreach-section bulk-recipients-section" aria-label="Recipients">
          <div className="bulk-section-heading">
            <span>Batch</span>
            <strong>{selectedLeadIds.length} selected</strong>
          </div>
          <div className="bulk-draft-category">
            <button
              className={`bulk-draft-row${showingTemplate ? " is-active" : ""}`}
              type="button"
              onClick={() => setPreviewLeadId("")}
            >
              <Mail size={13} />
              <span>
                <strong>Draft template</strong>
                <em>Subject and body</em>
              </span>
            </button>
          </div>
          <div className="bulk-recipient-list">
            {selectableContacts.length ? (
              <>
                <div className="bulk-recipient-list-head">
                  <label>
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      checked={allSelected}
                      aria-label="Select all contacts"
                      onChange={toggleSelectAll}
                    />
                    <strong>All contacts</strong>
                  </label>
                  <span>{selectedLeadIds.length} of {selectableContacts.length}</span>
                </div>
                {readyContacts.map((contact) => (
                  <div
                    className={`bulk-recipient-row${contact.id === previewContact?.id ? " is-active" : ""}`}
                    key={contact.id}
                  >
                    <input
                      aria-label={`Include ${contact.company_name}`}
                      type="checkbox"
                      checked={selectedLeadIds.includes(contact.id)}
                      onChange={() => toggleSelectedLead(contact.id)}
                    />
                    <button
                      className="bulk-recipient-select"
                      type="button"
                      onClick={() => setPreviewLeadId(contact.id)}
                    >
                      <strong>{contact.company_name}</strong>
                      <em>{bulkOutreachEmail(contact)}</em>
                    </button>
                  </div>
                ))}
              </>
            ) : (
              <p className="bulk-empty-note">No contacts in this run yet.</p>
            )}
            {skippedContacts.length ? (
              <>
                <div className="bulk-recipient-list-divider">
                  <span>{skippedContacts.length} need review</span>
                </div>
                {skippedContacts.map((contact) => (
                  <div
                    className={`bulk-recipient-row is-warning${contact.id === previewContact?.id ? " is-active" : ""}`}
                    key={contact.id}
                  >
                    <input
                      aria-label={`Include ${contact.company_name}`}
                      type="checkbox"
                      checked={selectedLeadIds.includes(contact.id)}
                      onChange={() => toggleSelectedLead(contact.id)}
                    />
                    <button
                      className="bulk-recipient-select"
                      type="button"
                      onClick={() => setPreviewLeadId(contact.id)}
                    >
                      <strong>{contact.company_name}</strong>
                      <em>{bulkOutreachEmail(contact) || bulkOutreachSkipReason(contact)}</em>
                    </button>
                  </div>
                ))}
              </>
            ) : null}
          </div>
        </section>

        <section className="bulk-outreach-section bulk-message-section">
          <div className="bulk-message-heading">
            <div>
              <span>{showingTemplate ? "Template" : "Preview"}</span>
              <strong>{showingTemplate ? "Draft content" : "Selected email"}</strong>
            </div>
          </div>
          {showingTemplate ? (
            <div className="bulk-compose-fields">
              <label className="bulk-field">
                <span>Subject</span>
                <input
                  value={subject}
                  onChange={(event) => {
                    resetBatchState();
                    setSubject(event.target.value);
                  }}
                />
              </label>
              <label className="bulk-field">
                <span>Body</span>
                <textarea
                  value={body}
                  onChange={(event) => {
                    resetBatchState();
                    setBody(event.target.value);
                  }}
                />
              </label>
              <ComplianceFooterPreview profile={senderProfile} />
              <div className="bulk-token-row" aria-label="Supported template tokens">
                {bulkOutreachTokens.map((token) => (
                  <code key={token}>{token}</code>
                ))}
              </div>
            </div>
          ) : (
            <div className="bulk-message-preview">
              <label className="bulk-field">
                <span>Subject</span>
                <input
                  value={previewSubject}
                  onChange={(event) => updatePreviewEmail("subject", event.target.value)}
                />
              </label>
              <label className="bulk-field">
                <span>Body</span>
                <textarea
                  value={previewBody}
                  onChange={(event) => updatePreviewEmail("body", event.target.value)}
                />
              </label>
              <ComplianceFooterPreview profile={senderProfile} />
            </div>
          )}
        </section>
      </div>

      <footer className="bulk-outreach-footer">
        <div className="bulk-send-summary">
          <strong>{recipientContacts.length} selected</strong>
          <span>
            {gmailConnected
              ? "Unavailable contacts will be skipped."
              : "Connect Gmail before sending. Unavailable contacts will be skipped."}
          </span>
        </div>
        <button
          className="runbtn bulk-send-selected"
          type="button"
          disabled={!canSendSelected}
          onClick={() => void sendSelectedEmails()}
        >
          <Send size={14} />
          {sending ? "Sending..." : "Send"}
        </button>
        {!gmailConnected ? (
          <p className="bulk-warning">Connect Gmail before sending selected emails.</p>
        ) : null}
        {preparedResult?.skipped.length || approvalResult?.skipped.length || sendResult?.skipped.length ? (
          <details className="bulk-skipped-list">
            <summary>Batch notes</summary>
            <ul>
              {[...(preparedResult?.skipped || []), ...(approvalResult?.skipped || []), ...(sendResult?.skipped || [])]
                .slice(0, 8)
                .map((skip, index) => (
                  <li key={`${skip.lead_id || skip.message_id || index}`}>
                    <strong>{skip.company_name || "Message"}</strong>
                    <span>{skip.reason}</span>
                  </li>
                ))}
            </ul>
          </details>
        ) : null}
      </footer>
    </section>
  );
}

function ComplianceFooterPreview({ profile }: { profile: SenderProfile | null }) {
  if (!profile?.complete) return null;
  return (
    <div className="bulk-compliance-preview">
      <span>{profile.sender_legal_name}</span>
      <span>{profile.sender_mailing_address}</span>
      <span>{profile.sender_contact}</span>
      <span>Unsubscribe</span>
    </div>
  );
}

function emptyCampaignMessageBatchResult(): CampaignMessageBatchResult {
  return {
    messages: [],
    skipped: [],
    created_count: 0,
    reused_count: 0,
    approved_count: 0,
    sent_count: 0,
    failed_count: 0,
  };
}

function appendCampaignMessageBatchResult(
  target: CampaignMessageBatchResult,
  source: CampaignMessageBatchResult,
) {
  target.messages = mergeBatchMessages(target.messages, source.messages);
  target.skipped.push(...source.skipped);
  target.created_count += source.created_count;
  target.reused_count += source.reused_count;
  target.approved_count += source.approved_count;
  target.sent_count += source.sent_count;
  target.failed_count += source.failed_count;
}

async function prepareApproveAndSend({
  approvalAggregate,
  body,
  leadIds,
  onApproveDrafts,
  onCreateDrafts,
  onSendDrafts,
  onUpdateMessage,
  preparedAggregate,
  sendAggregate,
  subject,
}: {
  approvalAggregate: CampaignMessageBatchResult;
  body: string;
  leadIds: string[];
  onApproveDrafts: (input?: { message_ids?: string[]; notes?: string | null }) => Promise<CampaignMessageBatchResult | null>;
  onCreateDrafts: (input: CampaignOutreachDraftInput) => Promise<CampaignMessageBatchResult | null>;
  onSendDrafts: (input?: { message_ids?: string[] }) => Promise<CampaignMessageBatchResult | null>;
  onUpdateMessage: (messageId: string, update: Partial<Message>) => Promise<void>;
  preparedAggregate: CampaignMessageBatchResult;
  sendAggregate: CampaignMessageBatchResult;
  subject: string;
}) {
  const prepared = await onCreateDrafts({
    audience: "selected",
    lead_ids: leadIds,
    subject,
    body,
    approach_tag: "bulk_outreach",
  });
  if (!prepared) return;
  appendCampaignMessageBatchResult(preparedAggregate, prepared);

  let currentMessages = prepared.messages;
  const editableMessages = currentMessages.filter((message) => (
    message.status === "pending_approval" || message.status === "draft"
  ));
  if (leadIds.length === 1 && editableMessages.length) {
    await Promise.all(
      editableMessages.map((message) => onUpdateMessage(message.id, { subject, body })),
    );
  }

  const draftIds = editableMessages.map((message) => message.id);
  if (draftIds.length) {
    const approved = await onApproveDrafts({ message_ids: draftIds });
    if (approved) {
      appendCampaignMessageBatchResult(approvalAggregate, approved);
      currentMessages = mergeBatchMessages(currentMessages, approved.messages);
    }
  }

  const approvedIds = currentMessages
    .filter((message) => message.status === "approved")
    .map((message) => message.id);
  if (approvedIds.length) {
    const sent = await onSendDrafts({ message_ids: approvedIds });
    if (sent) {
      appendCampaignMessageBatchResult(sendAggregate, sent);
    }
  }
}

function ContactCard({
  contact,
  onOpen,
  onToggleShortlist,
  selected = false,
}: {
  contact: DiscoveryResult;
  onOpen: () => void;
  onToggleShortlist: () => void;
  selected?: boolean;
}) {
  const opportunity = contactOpportunityAssessment(contact);
  const opportunityReason = contactListPrimarySignal(contact);
  const category = contactListCategoryLabel(contact);
  const geography = contact.geography || contact.research?.geography || "";
  const needsVerification = searchMatchStatus(contact) === "unknown";
  const cardClass = [
    "contact-card",
    isReachableContact(contact) ? "" : "no-contact",
    selected ? "is-selected" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <li>
      <article
        className={cardClass}
        role="button"
        tabIndex={0}
        onClick={onOpen}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onOpen();
          }
        }}
      >
        <span className={`lead-opportunity-dot opportunity-${opportunity.level}`} aria-hidden="true" />
        <div className="contact-main">
          <span className="contact-identity">
            <span className="contact-title-line">
              <strong>{contact.company_name}</strong>
            </span>
            <small className="contact-meta-line">
              <span>{category}</span>
              {geography ? (
                <>
                  <MapPin size={12} />
                  <span>{geography}</span>
                </>
              ) : null}
            </small>
            {needsVerification ? (
              <span className="contact-evidence-line">Needs verification against search criteria</span>
            ) : opportunityReason ? (
              <span className="contact-evidence-line">{opportunityReason}</span>
            ) : null}
          </span>
        </div>
        <div className="contact-actions" aria-label="Contact availability">
          <time dateTime={contact.updated_at || contact.created_at}>{formatLeadAge(contact.updated_at || contact.created_at)}</time>
          <button
            aria-label={contact.shortlisted_at ? "Remove from shortlist" : "Add to shortlist"}
            className={contact.shortlisted_at ? "lead-star active" : "lead-star"}
            disabled={needsVerification}
            title={needsVerification ? "Resolve search criteria before shortlisting" : undefined}
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onToggleShortlist();
            }}
          >
            <Star size={14} fill={contact.shortlisted_at ? "currentColor" : "none"} />
          </button>
        </div>
      </article>
    </li>
  );
}

function ContactDrawer({
  contact,
  gmailConnected,
  message,
  onClose,
  persistent = false,
  onApproveMessage,
  onCreateDraft,
  onQualifyLead,
  onMarkMessageReplied,
  onGenerateApproach,
  onRecordOutcome,
  onSendMessage,
  onUpdateContactPolicy,
  onUpdateLead,
  onUpdateMessage,
}: {
  contact: DiscoveryResult;
  gmailConnected: boolean;
  message: Message | undefined;
  onClose: () => void;
  persistent?: boolean;
  onApproveMessage: (messageId: string) => Promise<void>;
  onCreateDraft: (leadId: string) => Promise<Message | null>;
  onQualifyLead: (leadId: string) => Promise<void>;
  onMarkMessageReplied: (messageId: string, body?: string) => Promise<void>;
  onGenerateApproach?: (leadId: string) => Promise<void>;
  onRecordOutcome?: (leadId: string, outcome: LeadOutcomeValue) => Promise<void>;
  onSendMessage: (messageId: string) => Promise<void>;
  onUpdateContactPolicy: (leadId: string, update: LeadContactPolicyInput) => Promise<void>;
  onUpdateLead: (leadId: string, update: LeadUpdateInput) => Promise<void>;
  onUpdateMessage: (messageId: string, update: Partial<Message>) => Promise<void>;
}) {
  const { showToast } = useToast();
  const currentReviewStatus = reviewStatus(contact);
  const agentAssessment = getAgentAssessment(contact);
  const policyStatus = contactPolicyStatus(contact);
  const blocked = isContactBlocked(contact);
  const canShortlist = canShortlistContact(contact) && !blocked;
  const shortlisted = Boolean(contact.shortlisted_at);
  const [reviewNote, setReviewNote] = useState("");
  const [qualifying, setQualifying] = useState(false);
  const [savingReview, setSavingReview] = useState(false);
  const [draftSubject, setDraftSubject] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [savingDraft, setSavingDraft] = useState(false);
  const [activeTab, setActiveTab] = useState<DrawerTab>("overview");
  const [outreachOpen, setOutreachOpen] = useState(false);
  const [selectedOutcome, setSelectedOutcome] = useState<LeadOutcomeValue | "">("");
  const [savingOutcome, setSavingOutcome] = useState(false);
  const [generatingApproach, setGeneratingApproach] = useState(false);
  const signals = contactSignals(contact);
  const website = contact.website_url || contact.research?.website_url || "";
  const contactUrl = getContactUrl(contact);
  const email = contact.contact_email || contact.research?.contact_email || "";
  const verified = isVerifiedContact(contact);
  const canDraft = Boolean(!blocked && shortlisted && canShortlist && verified && email);
  const sendBlockReason =
    blocked
      ? "This contact is blocked from outreach."
      : !email
        ? "Add or find an email before sending."
        : !canDraft
          ? "Keep this contact shortlisted before sending."
          : !gmailConnected
            ? "Connect Gmail in Integrations before sending."
            : "";
  const canSend = Boolean(message && message.status === "approved" && !sendBlockReason);
  const approvedBy =
    message?.approval && typeof message.approval === "object" && "approved_by" in message.approval
      ? String((message.approval as Record<string, unknown>).approved_by)
      : undefined;
  const phone = getPhone(contact);
  const contactName = getContactName(contact);
  const address = getAddress(contact);
  const rating = getRating(contact);
  const reviewCount = getReviewCount(contact);
  const price = getPrice(contact);
  const posted = getPostedDate(contact);
  const confidence = contact.research?.confidence ? `${contact.research.confidence}%` : "—";
  const evidenceNotes = [
    ...(contact.research?.pain_indicators || []),
    ...(contact.research?.disqualifiers || []),
    ...(contact.qualification?.criteria || []).flatMap((criterion) => criterion.evidence || []),
  ].filter(Boolean);
  const drawerCategory = contactListCategoryLabel(contact);
  const drawerGeography = contact.geography || contact.research?.geography || "";
  const drawerSummary = contactDrawerSummary(contact);
  const agentFitStatus = displayAgentFitStatus(contact);
  const fitScore = contactFitScore(contact);
  const verification = verificationStatus(contact);
  const verificationDetails = verificationDetailChips(contact.verification_details);
  const activityItems = contactActivityItems(contact, message);
  const opportunity = contactOpportunityAssessment(contact);
  const opportunityReasons = opportunity.signals;
  const contacted = Boolean(contact.last_contacted_at || contact.latest_outcome === "contacted");
  const evidenceCount = new Set([
    ...signals,
    ...evidenceNotes,
    ...verificationDetails,
    contact.verification_reason || "",
    agentAssessment?.rationale || "",
  ].filter(Boolean)).size;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    setReviewNote(contact.review_note || "");
  }, [contact.id, contact.review_note]);

  useEffect(() => {
    setDraftSubject(message?.subject || "");
    setDraftBody(message?.body || "");
  }, [message?.id, message?.subject, message?.body]);

  useEffect(() => {
    setActiveTab("overview");
    setOutreachOpen(false);
    setSelectedOutcome("");
  }, [contact.id]);

  const recordOutcome = async () => {
    if (!onRecordOutcome || !selectedOutcome || savingOutcome) return;
    setSavingOutcome(true);
    try {
      await onRecordOutcome(contact.id, selectedOutcome);
      showToast({ title: "Outcome recorded", tone: "green" });
      setSelectedOutcome("");
    } catch (err) {
      showToast({ title: "Outcome update failed", message: err instanceof Error ? err.message : String(err), tone: "red" });
    } finally {
      setSavingOutcome(false);
    }
  };

  const markContacted = async () => {
    if (!onRecordOutcome || savingOutcome) return;
    setSavingOutcome(true);
    try {
      await onRecordOutcome(contact.id, "contacted");
      showToast({ title: "Marked contacted", tone: "green" });
    } catch (err) {
      showToast({ title: "Outcome update failed", message: err instanceof Error ? err.message : String(err), tone: "red" });
    } finally {
      setSavingOutcome(false);
    }
  };

  const generateApproach = async () => {
    if (!onGenerateApproach || generatingApproach) return;
    setGeneratingApproach(true);
    try {
      await onGenerateApproach(contact.id);
      showToast({ title: "Approach generated", tone: "green" });
    } catch (err) {
      showToast({ title: "Approach generation failed", message: err instanceof Error ? err.message : String(err), tone: "red" });
    } finally {
      setGeneratingApproach(false);
    }
  };

  const saveLeadUpdate = async (update: LeadUpdateInput, successTitle: string) => {
    if (savingReview) return;
    setSavingReview(true);
    try {
      await onUpdateLead(contact.id, update);
      showToast({ title: successTitle, tone: "green" });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      showToast({ title: "Update failed", message, tone: "red" });
    } finally {
      setSavingReview(false);
    }
  };

  const runAgentCheck = async () => {
    if (qualifying) return;
    setQualifying(true);
    try {
      await onQualifyLead(contact.id);
      showToast({ title: "Agent assessment updated", tone: "green" });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      showToast({ title: "Agent check failed", message, tone: "red" });
    } finally {
      setQualifying(false);
    }
  };

  const chooseReviewStatus = (nextStatus: LeadReviewStatus) => {
    if (blocked) {
      showToast({ title: "Contact blocked", message: contactPolicyDescription(contact), tone: "amber" });
      return;
    }
    void saveLeadUpdate(
      {
        review_status: nextStatus,
        shortlisted: nextStatus === "not_fit" ? false : undefined,
      },
      "Review saved",
    );
  };

  const toggleShortlist = () => {
    if (!canShortlist) return;
    void saveLeadUpdate(
      { shortlisted: !shortlisted },
      shortlisted ? "Removed from shortlist" : "Shortlisted",
    );
  };

  const updateContactPolicy = async (update: LeadContactPolicyInput, successTitle: string) => {
    if (savingReview) return;
    const isBlocking = update.status !== "allowed";
    if (isBlocking) {
      const confirmed = window.confirm(`${successTitle}? This contact will be removed from shortlist and blocked from outreach.`);
      if (!confirmed) return;
    }
    setSavingReview(true);
    try {
      await onUpdateContactPolicy(contact.id, update);
      showToast({ title: successTitle, tone: "green" });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      showToast({ title: "Contact policy failed", message, tone: "red" });
    } finally {
      setSavingReview(false);
    }
  };

  const saveReviewNote = () => {
    void saveLeadUpdate({ review_note: reviewNote }, "Review note saved");
  };

  const generateDraft = async () => {
    if (savingDraft) return;
    setSavingDraft(true);
    try {
      const created = await onCreateDraft(contact.id);
      if (created) {
        setDraftSubject(created.subject || "");
        setDraftBody(created.body || "");
      }
      showToast({ title: "Draft ready", tone: "green" });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      showToast({ title: "Draft failed", message: errorMessage, tone: "red" });
    } finally {
      setSavingDraft(false);
    }
  };

  const saveDraft = async () => {
    if (!message || savingDraft || !draftBody.trim()) return;
    setSavingDraft(true);
    try {
      await onUpdateMessage(message.id, {
        subject: draftSubject.trim() || undefined,
        body: draftBody.trim(),
      });
      showToast({ title: "Draft saved", tone: "green" });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      showToast({ title: "Draft save failed", message: errorMessage, tone: "red" });
    } finally {
      setSavingDraft(false);
    }
  };

  const approveDraft = async () => {
    if (!message || savingDraft) return;
    setSavingDraft(true);
    try {
      await onApproveMessage(message.id);
      showToast({ title: "Draft approved", tone: "green" });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      showToast({ title: "Approval failed", message: errorMessage, tone: "red" });
    } finally {
      setSavingDraft(false);
    }
  };

  const sendDraft = async () => {
    if (!message || savingDraft) return;
    const confirmed = window.confirm("Send this approved email now?");
    if (!confirmed) return;
    setSavingDraft(true);
    try {
      await onSendMessage(message.id);
      showToast({ title: "Email sent", tone: "green" });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      showToast({ title: "Send failed", message: errorMessage, tone: "red" });
    } finally {
      setSavingDraft(false);
    }
  };

  const markReplied = async () => {
    if (!message || savingDraft) return;
    const body = window.prompt("Optional reply note", "Marked as replied manually.");
    if (body === null) return;
    setSavingDraft(true);
    try {
      await onMarkMessageReplied(message.id, body.trim() || undefined);
      showToast({ title: "Marked replied", tone: "green" });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      showToast({ title: "Reply update failed", message: errorMessage, tone: "red" });
    } finally {
      setSavingDraft(false);
    }
  };

  const copyDraft = () => {
    const text = [draftSubject ? `Subject: ${draftSubject}` : "", draftBody].filter(Boolean).join("\n\n");
    void copy(text, "Draft");
  };

  const copy = async (value: string, label: string) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      showToast({ title: `${label} copied`, tone: "green" });
    } catch {
      showToast({ title: "Copy failed", message: `Could not copy ${label.toLowerCase()}.`, tone: "red" });
    }
  };

  return (
    <div className={persistent ? "contact-drawer-overlay open is-persistent" : "contact-drawer-overlay open"}>
      {persistent ? null : (
        <button className="contact-drawer-backdrop" type="button" aria-label="Close details" onClick={onClose} />
      )}
      <aside className="contact-drawer-panel" aria-label="Contact details">
        <header className="contact-drawer-header">
          <div className="drawer-title-row">
            <div className="drawer-title-copy">
              <h2>{contact.company_name}</h2>
              <span className="drawer-ready-status">
                <span />
                {shortlisted ? "Shortlisted" : canShortlist ? "Ready to shortlist" : "Needs review"}
              </span>
              <p className="drawer-subtitle">
                <span>{drawerCategory}</span>
                {drawerGeography ? (
                  <>
                    <MapPin size={12} />
                    <span>{drawerGeography}</span>
                  </>
                ) : null}
              </p>
            </div>
          </div>
          <div className="drawer-header-actions">
            {website ? (
              <a aria-label="Open website" href={website} target="_blank" rel="noreferrer" title="Open website">
                <ExternalLink size={17} />
              </a>
            ) : null}
            <button
              aria-label={shortlisted ? "Remove from shortlist" : "Add to shortlist"}
              className={shortlisted ? "active" : ""}
              disabled={savingReview || !canShortlist}
              type="button"
              title={shortlisted ? "Remove from shortlist" : "Add to shortlist"}
              onClick={toggleShortlist}
            >
              <Star size={17} fill={shortlisted ? "currentColor" : "none"} />
            </button>
            <button
              aria-label="Close details"
              className="drawer-close"
              title="Close details"
              type="button"
              onClick={onClose}
            >
              <X size={18} />
            </button>
          </div>
        </header>

            <section className="drawer-location-banner">
              <MapPin size={20} />
              <div>
                <strong>{contact.company_name}</strong>
                <span>{address || drawerGeography || "Location unavailable"}</span>
              </div>
              {address ? (
                <a
                  aria-label="Open location"
                  href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink size={15} />
                </a>
              ) : null}
            </section>

            <section className="drawer-signal-summary" aria-label="Contact summary">
              <div className={`drawer-fit-verdict ${agentFitStatus.className}`}>
                <Check size={14} />
                <span>Fit · {agentFitStatus.label}</span>
              </div>
              <div className="drawer-availability-row">
                <span className={`availability-pill opportunity-${opportunity.level}`}>
                  <Sparkles size={13} />
                  Opportunity · {opportunity.label}
                </span>
                <span className={`availability-pill verification-${verification}`}>
                  <Mail size={13} />
                  Contact · {contactReadinessLabel(contact)}
                </span>
                {blocked ? (
                  <span className={`availability-pill policy-${policyStatus}`}>
                    <AlertTriangle size={13} />
                    {contactPolicyStatusLabel(policyStatus)}
                  </span>
                ) : null}
              </div>
            </section>

            <nav className="drawer-tabs" aria-label="Contact detail sections">
              <button
                className={activeTab === "overview" ? "active" : ""}
                type="button"
                onClick={() => setActiveTab("overview")}
              >
                Overview
              </button>
              <button
                className={activeTab === "evidence" ? "active" : ""}
                type="button"
                onClick={() => setActiveTab("evidence")}
              >
                Evidence
                <span>{evidenceCount}</span>
              </button>
            </nav>

            <div className="drawer-body">
              {activeTab === "overview" ? (
                <>
                  <section className="drawer-opportunity-panel">
                    <div className="drawer-section-heading">
                      <h3>Why this lead?</h3>
                      <span>{opportunity.label}</span>
                    </div>
                    {opportunityReasons.length ? (
                      <ul>
                        {opportunityReasons.slice(0, 4).map((reason) => (
                          <li key={reason}>{reason}</li>
                        ))}
                      </ul>
                    ) : (
                      <p>
                        {opportunity.level === "unknown"
                          ? "This business has not been audited for a digital opportunity yet."
                          : "No specific digital opportunity was confirmed by the audit."}
                      </p>
                    )}
                  </section>

                  <p className="drawer-summary">{drawerSummary}</p>

                  {contact.approach ? (
                    <section className="drawer-approach-panel">
                      <div className="drawer-section-heading">
                        <h3>Suggested approach</h3>
                        <span>{contact.approach.best_channel.replace(/_/g, " ")}</span>
                      </div>
                      <p>{contact.approach.channel_reason}</p>
                      {contact.approach.opener ? <strong>{contact.approach.opener}</strong> : null}
                      {contact.approach.talk_track?.length ? (
                        <ul>
                          {contact.approach.talk_track.slice(0, 3).map((item) => <li key={item}>{item}</li>)}
                        </ul>
                      ) : null}
                    </section>
                  ) : onGenerateApproach ? (
                    <section className="drawer-approach-panel is-empty">
                      <div className="drawer-section-heading">
                        <h3>Suggested approach</h3>
                        <button disabled={generatingApproach} type="button" onClick={() => void generateApproach()}>
                          <Sparkles size={13} />
                          {generatingApproach ? "Generating..." : "Generate"}
                        </button>
                      </div>
                      <p>Generate an evidence-grounded opener and talk track for this contact.</p>
                    </section>
                  ) : null}

                  <section className="drawer-structured-section">
                    <h3>Evidence</h3>
                    <dl className="drawer-detail-list drawer-info-card">
                    <DrawerRow icon={<Sparkles size={16} />} label="Source">
                      {contact.source || "Public business source"}
                    </DrawerRow>
                    <DrawerRow icon={<Globe size={16} />} label="Website">
                      {website ? (
                        <a href={website} target="_blank" rel="noreferrer">
                          {displayUrl(website)}
                        </a>
                      ) : (
                        <span>{contactWebsitePresenceLabel(contact)}</span>
                      )}
                    </DrawerRow>
                    </dl>
                  </section>

                  <section className="drawer-structured-section">
                    <h3>Contact</h3>
                    <dl className="drawer-detail-list drawer-info-card">
                    <DrawerRow icon={<Mail size={16} />} label="Email">
                      {email ? (
                        <button type="button" onClick={() => copy(email, "Email")}>
                          {email}
                          <span className={`inline-status verification-${verification}`}>
                            <Check size={11} />
                            {emailAvailabilityLabel(contact)}
                          </span>
                          <Copy size={13} />
                        </button>
                      ) : (
                        <span>No email found</span>
                      )}
                    </DrawerRow>
                    <DrawerRow icon={<ExternalLink size={16} />} label="Form / Contact URL">
                      {contactUrl ? (
                        <a href={contactUrl} target="_blank" rel="noreferrer">Open contact page</a>
                      ) : (
                        <span>No contact page found</span>
                      )}
                    </DrawerRow>
                    <DrawerRow icon={<Phone size={16} />} label="Phone">
                      {phone || "No phone found"}
                    </DrawerRow>
                  </dl>
                  </section>

                  <div className="drawer-mini-grid">
                    <Mini label="Rating" value={rating || "—"} />
                    <Mini label="Reviews" value={reviewCount || "—"} />
                    <Mini label="Price" value={price || "—"} />
                    <Mini label="Posted" value={posted || "—"} />
                    <Mini label="Confidence" value={confidence} />
                  </div>

                  <ContactActivityTrail items={activityItems} />

                  {onRecordOutcome ? (
                    <section className="drawer-outcome-panel">
                      <div className="drawer-section-heading">
                        <h3>Sales outcome</h3>
                        <span>{contact.latest_outcome ? outcomeLabel(contact.latest_outcome) : "Not recorded"}</span>
                      </div>
                      <div className="drawer-outcome-control">
                        <select
                          aria-label="Sales outcome"
                          value={selectedOutcome}
                          onChange={(event) => setSelectedOutcome(event.target.value as LeadOutcomeValue | "")}
                        >
                          <option value="">Choose outcome</option>
                          {leadOutcomeOptions.map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </select>
                        <button disabled={!selectedOutcome || savingOutcome} type="button" onClick={() => void recordOutcome()}>
                          {savingOutcome ? "Saving..." : "Record"}
                        </button>
                      </div>
                    </section>
                  ) : null}
                </>
              ) : null}

              {activeTab === "evidence" ? (
                <>
                  <section className="drawer-verification-panel">
                    <div className="drawer-section-heading">
                      <h3>Contact verification</h3>
                      <span>{contactVerificationSummary(contact)}</span>
                    </div>
                    <p>{contact.verification_reason || verificationStatusDescription(contact)}</p>
                    {verificationDetails.length ? (
                      <div className="verification-detail-row">
                        {verificationDetails.map((detail) => (
                          <span key={detail}>{detail}</span>
                        ))}
                      </div>
                    ) : null}
                  </section>

                  <section className={blocked ? "drawer-contact-policy-panel is-blocked" : "drawer-contact-policy-panel"}>
                    <div className="drawer-section-heading">
                      <h3>Contact policy</h3>
                      <span>{contactPolicyStatusLabel(policyStatus)}</span>
                    </div>
                    <p>{contactPolicyDescription(contact)}</p>
                    <div className="review-secondary-row contact-policy-actions">
                      <button
                        type="button"
                        disabled={savingReview || policyStatus === "suppressed"}
                        onClick={() =>
                          void updateContactPolicy(
                            { status: "suppressed", reason: "Manually marked do-not-contact.", scope: "product" },
                            "Do not contact",
                          )
                        }
                      >
                        Do not contact
                      </button>
                      <button
                        type="button"
                        disabled={savingReview || policyStatus === "bounced"}
                        onClick={() =>
                          void updateContactPolicy(
                            { status: "bounced", reason: "Email bounced or failed delivery.", scope: "product" },
                            "Marked bounced",
                          )
                        }
                      >
                        Mark bounced
                      </button>
                      <button
                        type="button"
                        disabled={savingReview || policyStatus === "unsubscribed"}
                        onClick={() =>
                          void updateContactPolicy(
                            { status: "unsubscribed", reason: "Contact requested no further outreach.", scope: "product" },
                            "Marked unsubscribed",
                          )
                        }
                      >
                        Unsubscribed
                      </button>
                      {blocked ? (
                        <button
                          type="button"
                          disabled={savingReview}
                          onClick={() => void updateContactPolicy({ status: "allowed" }, "Contact allowed")}
                        >
                          Clear block
                        </button>
                      ) : null}
                    </div>
                  </section>

                  <section className="drawer-agent-panel">
                    <div className="drawer-section-heading">
                      <h3>Agent assessment</h3>
                      <span>
                        {agentAssessment
                          ? `${agentFitStatusLabel(agentAssessment.fitStatus)} · fit ${fitScore}`
                          : "Not assessed"}
                      </span>
                    </div>
                    {agentAssessment ? (
                      <>
                        <p className="agent-rationale">{agentAssessment.rationale}</p>
                        <div className="agent-evidence-grid">
                          <EvidenceList title="Positive signals" items={agentAssessment.positiveSignals} empty="No strong positive signals captured." />
                          <EvidenceList title="Missing evidence" items={agentAssessment.missingEvidence} empty="No missing evidence called out." />
                          <EvidenceList title="Risks" items={agentAssessment.risks} empty="No specific risks captured." />
                        </div>
                      </>
                    ) : (
                      <p className="agent-rationale">Run an agent check to score this contact against the product criteria.</p>
                    )}
                    <div className="review-secondary-row">
                      <button type="button" disabled={qualifying} onClick={runAgentCheck}>
                        {qualifying ? "Checking..." : agentAssessment ? "Recheck fit" : "Run agent check"}
                      </button>
                      {agentAssessment && currentReviewStatus === "unreviewed" ? (
                        <button
                          type="button"
                          disabled={qualifying || savingReview}
                          onClick={() => chooseReviewStatus(agentAssessment.fitStatus)}
                        >
                          Use recommendation
                        </button>
                      ) : null}
                    </div>
                  </section>

                  <section className="drawer-review-panel">
                    <div className="drawer-section-heading">
                      <h3>Review</h3>
                      <span>{reviewStatusLabel(currentReviewStatus)}</span>
                    </div>
                    <div className="review-action-row">
                      {(["good_fit", "maybe", "not_fit"] as LeadReviewStatus[]).map((status) => (
                        <button
                          className={currentReviewStatus === status ? "active" : ""}
                          disabled={savingReview}
                          key={status}
                          type="button"
                          onClick={() => chooseReviewStatus(status)}
                        >
                          {reviewStatusLabel(status)}
                        </button>
                      ))}
                    </div>
                    <label className="review-note-field">
                      <span>Note</span>
                      <textarea
                        placeholder="Why this contact is or is not worth pursuing"
                        value={reviewNote}
                        onChange={(event) => setReviewNote(event.target.value)}
                      />
                    </label>
                    <div className="review-secondary-row">
                      <button type="button" disabled={savingReview} onClick={saveReviewNote}>
                        Save note
                      </button>
                    </div>
                  </section>

                  <div className="drawer-chip-row">
                    {signals.slice(0, 6).map((signal) => (
                      <span key={signal}>{signal}</span>
                    ))}
                  </div>

                  {evidenceNotes.length ? (
                    <section className="drawer-section">
                      <h3>Evidence notes</h3>
                      <ul className="drawer-notes">
                        {evidenceNotes.slice(0, 5).map((note) => (
                          <li key={note}>{note}</li>
                        ))}
                      </ul>
                    </section>
                  ) : null}
                </>
              ) : null}

            </div>

            <footer className="drawer-footer drawer-action-footer">
              <div className="drawer-footer-secondary">
                {shortlisted ? (
                  <button
                    type="button"
                    disabled={savingReview || !canShortlist}
                    onClick={toggleShortlist}
                  >
                    Remove shortlist
                  </button>
                ) : null}
                <button
                  className={currentReviewStatus === "not_fit" ? "active" : ""}
                  type="button"
                  disabled={savingReview || blocked}
                  onClick={() => chooseReviewStatus("not_fit")}
                >
                  Dismiss
                </button>
              </div>
              <button
                className="drawer-primary-action"
                type="button"
                disabled={shortlisted ? savingOutcome || contacted : savingReview || !canShortlist}
                onClick={shortlisted ? () => void markContacted() : toggleShortlist}
              >
                {shortlisted ? <Check size={14} /> : <Star size={14} />}
                {shortlisted ? (contacted ? "Contacted" : "Mark contacted") : "Shortlist"}
              </button>
            </footer>
      </aside>

      {outreachOpen ? (
        <Modal title={contactName || "Outreach"} onClose={() => setOutreachOpen(false)}>
          <div className="outreach-modal-body">
          <div className="outreach-modal-recipient">
            <span>To</span>
            <strong>{contactName || "Unknown contact"}</strong>
            <span>{email || "No email on file"}</span>
          </div>
          <div className="drawer-section-heading">
            <h3>Status</h3>
            <span>{message ? messageStatusLabel(message.status) : canDraft ? "Not generated" : "Shortlist required"}</span>
          </div>
          {message ? (
            <>
              <label className="draft-field">
                <span>Subject</span>
                <input
                  value={draftSubject}
                  onChange={(event) => setDraftSubject(event.target.value)}
                  disabled={message.status === "sent"}
                />
              </label>
              <label className="draft-field">
                <span>Body</span>
                <textarea
                  value={draftBody}
                  onChange={(event) => setDraftBody(event.target.value)}
                  disabled={message.status === "sent"}
                />
              </label>
              {approvedBy && (message.status === "approved" || message.status === "sent") ? (
                <p className="outreach-modal-approved">Approved by {approvedBy}</p>
              ) : null}
              <div className="draft-action-row">
                <button type="button" disabled={savingDraft || !draftBody.trim() || message.status === "sent"} onClick={saveDraft}>
                  Save
                </button>
                <button type="button" disabled={savingDraft || !draftBody.trim()} onClick={copyDraft}>
                  <Copy size={13} />
                  Copy
                </button>
                {message.status === "pending_approval" || message.status === "draft" ? (
                  <button type="button" disabled={savingDraft || !draftBody.trim()} onClick={approveDraft}>
                    Approve
                  </button>
                ) : null}
                {message.status === "approved" ? (
                  <button type="button" disabled={savingDraft || !canSend} onClick={sendDraft}>
                    Send email
                  </button>
                ) : null}
                {message.status === "sent" ? (
                  <button type="button" disabled={savingDraft} onClick={markReplied}>
                    Mark replied
                  </button>
                ) : null}
              </div>
              {message.status === "approved" && !canSend ? (
                <p className="draft-warning">{sendBlockReason}</p>
              ) : null}
            </>
          ) : canDraft ? (
            <button className="generate-draft-button" type="button" disabled={savingDraft} onClick={generateDraft}>
              Generate draft
            </button>
          ) : (
            <p className="draft-warning">
              {blocked
                ? "This contact is blocked from outreach."
                : shortlisted && !verified
                  ? "Verify this contact before generating outreach."
                  : !email
                    ? "Find an email before generating outreach."
                    : "Mark this contact as Good fit or Maybe, then shortlist it before drafting."}
            </p>
          )}
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

function DrawerRow({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <div className="drawer-row">
      <dt>
        <span className="drawer-row-icon">{icon}</span>
        <span className="drawer-row-label">{label}</span>
      </dt>
      <dd>{children}</dd>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="drawer-mini">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ContactActivityTrail({ items }: { items: ContactActivityItem[] }) {
  const completedCount = items.filter((item) => item.complete).length;

  return (
    <section className="drawer-activity-panel">
      <div className="drawer-section-heading">
        <h3>Activity</h3>
        <span>
          {completedCount}/{items.length}
        </span>
      </div>
      <ol className="drawer-activity-list">
        {items.map((item) => (
          <li className={`activity-${item.tone}`} key={item.label}>
            <span className="activity-marker" aria-hidden="true">
              {item.complete ? <Check size={11} /> : null}
            </span>
            <span className="activity-copy">
              <strong>{item.label}</strong>
              <span>{item.detail}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function EvidenceList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  const visibleItems = items.filter(Boolean).slice(0, 3);
  return (
    <div className="agent-evidence-list">
      <strong>{title}</strong>
      {visibleItems.length ? (
        <ul>
          {visibleItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>{empty}</p>
      )}
    </div>
  );
}

function getRunPrompt(run: { source_input?: string | null; source_inputs?: Record<string, unknown> } | undefined) {
  const prompt = run?.source_inputs?.source_request_prompt;
  if (typeof prompt === "string" && prompt.trim()) return prompt.trim();
  const compiledQuery = run?.source_inputs?.compiled_query;
  if (typeof compiledQuery === "string" && compiledQuery.trim() && !compiledQuery.startsWith("http")) {
    return compiledQuery.trim();
  }
  if (run?.source_input?.trim() && !run.source_input.trim().startsWith("http")) return run.source_input.trim();
  return "";
}

function requestedResultCount(
  run: { max_leads?: number; source_inputs?: Record<string, unknown> } | undefined,
) {
  const value = run?.source_inputs?.requested_result_count;
  if (typeof value === "number" && Number.isFinite(value) && value > 0) return value;
  return run?.max_leads || 25;
}

function storedSearchContract(
  run: { source_inputs?: Record<string, unknown> } | undefined,
): Record<string, unknown> {
  const raw = run?.source_inputs?.business_index_contract;
  const contract = isRecord(raw) ? { ...raw } : {};
  const contractHash = storedSearchContractHash(run);
  if (contractHash) contract.contract_hash = contractHash;
  return contract;
}

function storedSearchContractHash(
  run: { source_inputs?: Record<string, unknown> } | undefined,
): string {
  const value = run?.source_inputs?.search_contract_hash;
  return typeof value === "string" ? value : "";
}

function storedEvidenceMaxAge(
  run: { source_inputs?: Record<string, unknown> } | undefined,
): number {
  const contract = run?.source_inputs?.business_index_contract;
  const value = isRecord(contract) ? contract.evidence_max_age_days : undefined;
  return typeof value === "number" && value > 0 ? value : 30;
}

function isReachableContact(contact: DiscoveryResult) {
  return Boolean(
    !isContactBlocked(contact)
      && verificationStatus(contact) !== "invalid"
      && (contact.contact_email || contact.research?.contact_email || getPhone(contact)),
  );
}

function isBulkOutreachReadyContact(contact: DiscoveryResult) {
  return Boolean(
    !isContactBlocked(contact)
      && canShortlistContact(contact)
      && isVerifiedContact(contact)
      && bulkOutreachEmail(contact),
  );
}

function bulkOutreachEmail(contact: DiscoveryResult) {
  return contact.contact_email || contact.research?.contact_email || "";
}

function bulkOutreachSkipReason(contact: DiscoveryResult) {
  if (isContactBlocked(contact)) return contactPolicyDescription(contact);
  if (!canShortlistContact(contact)) return "Needs a Good fit or Maybe decision.";
  if (!bulkOutreachEmail(contact)) return "Missing email.";
  if (!isVerifiedContact(contact)) return "Email is not verified.";
  return "Not ready for outreach.";
}

function contactStatusLabel(contact: DiscoveryResult) {
  if (contact.qualification?.qualified) return "Qualified";
  if (contact.status === "disqualified") return "Disqualified";
  return "Review";
}

function reviewStatus(contact: DiscoveryResult): LeadReviewStatus {
  return contact.review_status || "unreviewed";
}

function reviewStatusLabel(status: LeadReviewStatus) {
  const labels: Record<LeadReviewStatus, string> = {
    unreviewed: "Needs review",
    good_fit: "Accepted",
    maybe: "Maybe",
    not_fit: "Rejected",
  };
  return labels[status];
}

function verificationStatus(contact: DiscoveryResult): ContactVerificationStatus {
  return contact.verification_status || "unverified";
}

function verificationStatusLabel(status: ContactVerificationStatus) {
  const labels: Record<ContactVerificationStatus, string> = {
    unverified: "Unverified",
    valid: "Verified",
    risky: "Risky",
    invalid: "Invalid",
    unknown: "Unknown",
  };
  return labels[status];
}

function emailAvailabilityLabel(contact: DiscoveryResult) {
  const status = verificationStatus(contact);
  if (status === "valid") return "deliverable";
  if (status === "risky") return "risky";
  if (status === "invalid") return "invalid";
  if (status === "unknown") return "unknown";
  return "found";
}

function verificationStatusDescription(contact: DiscoveryResult) {
  const status = verificationStatus(contact);
  if (status === "valid") return "This contact passed the configured verification check.";
  if (status === "risky") return "The contact may be reachable but has verification risk.";
  if (status === "invalid") return "The contact failed the configured verification check.";
  if (status === "unknown") return "The configured verification check could not confirm this contact.";
  return "This contact has not been verified yet.";
}

function contactPolicyStatus(contact: DiscoveryResult): ContactPolicyStatus {
  return contact.contact_policy_status || "allowed";
}

function isContactBlocked(contact: DiscoveryResult) {
  return contactPolicyStatus(contact) !== "allowed";
}

function contactPolicyStatusLabel(status: ContactPolicyStatus) {
  const labels: Record<ContactPolicyStatus, string> = {
    allowed: "Allowed",
    suppressed: "Do not contact",
    unsubscribed: "Unsubscribed",
    bounced: "Bounced",
  };
  return labels[status];
}

function contactPolicyDescription(contact: DiscoveryResult | undefined) {
  if (!contact) return "No contact policy has been set.";
  if (contact.contact_policy_reason) return contact.contact_policy_reason;
  const status = contactPolicyStatus(contact);
  if (status === "suppressed") return "This contact is manually blocked from outreach.";
  if (status === "unsubscribed") return "This contact requested no further outreach.";
  if (status === "bounced") return "This contact is blocked because email delivery bounced.";
  return "This contact can be shortlisted, drafted, and sent after the normal checks pass.";
}

function contactVerificationSummary(contact: DiscoveryResult) {
  const status = verificationStatus(contact);
  const score = typeof contact.verification_score === "number" ? ` · ${contact.verification_score}` : "";
  const provider = contact.verification_provider ? ` via ${contact.verification_provider}` : "";
  return `${verificationStatusLabel(status)}${score}${provider}`;
}

function verificationDetailChips(details: Record<string, unknown> | null | undefined) {
  if (!details) return [];
  const chips: string[] = [];
  const providerStatus = rawValueToString(details.provider_status);
  const providerReason = rawValueToString(details.provider_reason);
  if (providerStatus) chips.push(providerStatus.replace(/_/g, " "));
  if (providerReason && providerReason !== providerStatus) chips.push(providerReason.replace(/_/g, " "));
  if (truthyDetail(details.accept_all)) chips.push("accept-all");
  if (truthyDetail(details.disposable)) chips.push("disposable");
  if (truthyDetail(details.role)) chips.push("role account");
  if (truthyDetail(details.free)) chips.push("free email");
  if (truthyDetail(details.toxic)) chips.push(`toxicity: ${rawValueToString(details.toxic)}`);
  const suggestion = rawValueToString(details.did_you_mean);
  if (suggestion) chips.push(`suggested: ${suggestion}`);
  return chips.slice(0, 6);
}

function truthyDetail(value: unknown) {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return !["", "false", "no", "0", "unknown"].includes(value.trim().toLowerCase());
  if (typeof value === "number") return value > 0;
  return false;
}

function isVerifiedContact(contact: DiscoveryResult) {
  return verificationStatus(contact) === "valid";
}

function agentFitStatusLabel(status: AgentFitStatus) {
  const labels: Record<AgentFitStatus, string> = {
    good_fit: "Good fit",
    maybe: "Maybe",
    not_fit: "Not fit",
  };
  return labels[status];
}

function getAgentAssessment(contact: DiscoveryResult) {
  const qualification = contact.qualification;
  if (!qualification) return undefined;
  const fitStatus = legacyAdjustedFitStatus(
    contact,
    qualification.fit_status || deriveAgentFitStatus(qualification.qualified, qualification.score, qualification.recommended_next_step),
  );
  const criteriaEvidence = (qualification.criteria || []).flatMap((criterion) => criterion.evidence || []);
  const criteriaMissing = (qualification.criteria || []).flatMap((criterion) => criterion.missing_evidence || []);
  const scoreBreakdown = getScoreBreakdown(contact);
  return {
    fitStatus,
    score: clampScore(qualification.score),
    scoreBreakdown,
    rationale: qualification.rationale || "No rationale captured.",
    positiveSignals: [...new Set([...(qualification.positive_signals || []), ...criteriaEvidence])],
    missingEvidence: [...new Set([...(qualification.missing_evidence || []), ...criteriaMissing])],
    risks: [...new Set([...(qualification.risks || []), ...(contact.research?.disqualifiers || [])])],
  };
}

function deriveAgentFitStatus(qualified: boolean, score: number, nextStep?: string): AgentFitStatus {
  if (qualified && score >= 65) return "good_fit";
  if (score >= 50 && !/do not/i.test(nextStep || "")) return "maybe";
  return "not_fit";
}

function canShortlistContact(contact: DiscoveryResult) {
  if (searchMatchStatus(contact) === "unknown") return false;
  const status = reviewStatus(contact);
  if (status === "not_fit") return false;
  if (status === "good_fit" || status === "maybe") return true;
  const assessment = getAgentAssessment(contact);
  return assessment?.fitStatus === "good_fit" || assessment?.fitStatus === "maybe";
}

function searchMatchStatus(contact: DiscoveryResult): "matched" | "not_matched" | "unknown" | "" {
  return contactSearchMatch(contact).status;
}

function contactSearchMatch(contact: DiscoveryResult): {
  status: "matched" | "not_matched" | "unknown" | "";
  reason: string;
} {
  for (const raw of getRawObjects(contact)) {
    const status = rawValueToString(getRawValue(raw, "search_match.status"));
    if (status === "matched" || status === "not_matched" || status === "unknown") {
      return {
        status,
        reason: rawValueToString(getRawValue(raw, "search_match.reason")),
      };
    }
  }
  return { status: "", reason: "" };
}

function displayReviewDecision(contact: DiscoveryResult): { label: string; className: string } | null {
  const status = reviewStatus(contact);
  if (status === "unreviewed") return null;
  if (status === "good_fit") return { label: "Accepted", className: "fit-good" };
  if (status === "maybe") return { label: "Maybe", className: "fit-maybe" };
  return { label: "Rejected", className: "fit-bad" };
}

function displayAgentFitStatus(contact: DiscoveryResult): { label: string; className: string } {
  if (searchMatchStatus(contact) === "unknown") {
    return { label: "Needs verification", className: "fit-neutral" };
  }
  const assessment = getAgentAssessment(contact);
  if (assessment?.fitStatus === "good_fit") return { label: "Strong fit", className: "fit-good" };
  if (assessment?.fitStatus === "maybe") return { label: "Possible fit", className: "fit-maybe" };
  if (assessment?.fitStatus === "not_fit") return { label: "Low evidence", className: "fit-neutral" };
  return { label: "Needs review", className: "fit-neutral" };
}

function getScoreBreakdown(contact: DiscoveryResult) {
  const breakdown = contact.qualification?.score_breakdown;
  return {
    fitScore: clampScore(breakdown?.fit_score ?? legacyFitScore(contact)),
    reachabilityScore: clampScore(breakdown?.reachability_score ?? derivedReachabilityScore(contact)),
    sourceQualityScore: clampScore(breakdown?.source_quality_score ?? contact.research?.confidence ?? 0),
    notes: breakdown?.scoring_notes || [],
  };
}

function clampScore(value: number | null | undefined) {
  return Math.max(0, Math.min(100, Math.round(Number(value || 0))));
}

function contactFitScore(contact: DiscoveryResult) {
  return getScoreBreakdown(contact).fitScore;
}

function contactReachabilityScore(contact: DiscoveryResult) {
  return getScoreBreakdown(contact).reachabilityScore;
}

function contactSourceQualityScore(contact: DiscoveryResult) {
  return getScoreBreakdown(contact).sourceQualityScore;
}

function legacyFitScore(contact: DiscoveryResult) {
  const qualification = contact.qualification;
  let score = clampScore(qualification?.score ?? contact.research?.confidence ?? 0);
  if (!qualification?.score_breakdown && legacyMissingProblemEvidence(contact)) {
    score = Math.min(score, 74);
  }
  if (!qualification?.score_breakdown && qualification?.fit_status === "maybe") {
    score = Math.min(score, 79);
  }
  if (!qualification?.score_breakdown && qualification?.fit_status === "not_fit") {
    score = Math.min(score, 49);
  }
  return score;
}

function legacyAdjustedFitStatus(contact: DiscoveryResult, status: AgentFitStatus): AgentFitStatus {
  if (contact.qualification?.score_breakdown || status !== "good_fit") return status;
  return legacyMissingProblemEvidence(contact) ? "maybe" : status;
}

function legacyMissingProblemEvidence(contact: DiscoveryResult) {
  const qualification = contact.qualification;
  if (!qualification) return false;
  const missing = [
    ...(qualification.missing_evidence || []),
    ...((qualification.criteria || []).flatMap((criterion) => criterion.missing_evidence || [])),
  ];
  return missing.some((item) => /quote|quoting|estimate|estimating|pricing|workflow|software usage|product\/problem|problem signal|problem fit/i.test(item || ""));
}

function derivedReachabilityScore(contact: DiscoveryResult) {
  let score = 0;
  if (bulkOutreachEmail(contact)) score += 40;
  if (getPhone(contact)) score += 25;
  const verification = verificationStatus(contact);
  if (verification === "valid") score += 20;
  if (verification === "risky") score -= 10;
  if (verification === "invalid") score -= 35;
  return score;
}

function contactReadinessLabel(contact: DiscoveryResult) {
  const score = contactReachabilityScore(contact);
  const email = bulkOutreachEmail(contact);
  if (verificationStatus(contact) === "invalid") return "Contact invalid";
  if (score >= 75 && email && isVerifiedContact(contact)) return "Email verified";
  if (score >= 65) return "Reachable";
  if (email) return "Email found";
  if (getPhone(contact)) return "Phone only";
  return "No contact";
}

function contactReachabilityClass(contact: DiscoveryResult) {
  const score = contactReachabilityScore(contact);
  if (verificationStatus(contact) === "invalid") return "quality-bad";
  if (score >= 65) return "quality-good";
  if (score >= 25) return "quality-warn";
  return "quality-muted";
}

function sourceQualityTierLabel(contact: DiscoveryResult) {
  const score = contactSourceQualityScore(contact);
  if (score >= 80) return "Strong";
  if (score >= 65) return "OK";
  if (score >= 45) return "Weak";
  return "Unclear";
}

function contactSourceQualityLabel(contact: DiscoveryResult) {
  return `${sourceQualityTierLabel(contact)} source`;
}

function contactSourceQualityClass(contact: DiscoveryResult) {
  const score = contactSourceQualityScore(contact);
  if (score >= 80) return "quality-good";
  if (score >= 65) return "quality-neutral";
  if (score >= 45) return "quality-warn";
  return "quality-muted";
}

function contactEvidenceLine(contact: DiscoveryResult) {
  const assessment = getAgentAssessment(contact);
  const evidence =
    assessment?.positiveSignals[0] ||
    contact.research?.signals?.[0] ||
    contact.research?.summary ||
    contact.description ||
    "Open details to review public evidence.";
  return truncateText(cleanContactEvidenceText(evidence) || evidence, 128);
}

function contactListCategoryLabel(contact: DiscoveryResult) {
  const explicitType = cleanContactListText(contact.research?.business_type || "");
  if (explicitType && !isNoisyEnrichmentText(explicitType) && !isContactMetadataText(explicitType)) {
    return truncateText(explicitType, 42);
  }

  const combined = [
    contact.company_name,
    contact.description,
    contact.research?.summary,
    ...(contact.research?.signals || []),
  ]
    .filter(Boolean)
    .join(" ");
  if (/paint|stain|wallpaper|drywall|coating/i.test(combined)) return "Painting provider";
  if (/contract|renovation|repair|install/i.test(combined)) return "Service contractor";
  if (/landscap|roof|plumb|hvac|electric|clean/i.test(combined)) return "Local service provider";
  return "Local business";
}

function contactListEvidenceLine(contact: DiscoveryResult) {
  const assessment = getAgentAssessment(contact);
  const candidates = [
    assessment?.positiveSignals[0],
    contact.research?.signals?.[0],
    assessment?.rationale,
    contact.research?.summary,
    contact.description,
  ];
  for (const candidate of candidates) {
    const cleaned = cleanContactEvidenceText(candidate || "");
    if (
      cleaned &&
      !isNoisyEnrichmentText(cleaned) &&
      !isInternalQualificationText(cleaned) &&
      !isLowValueContactListText(cleaned)
    ) {
      return truncateText(cleaned, 88);
    }
  }
  if (bulkOutreachEmail(contact) && isVerifiedContact(contact)) return "Verified email available";
  if (bulkOutreachEmail(contact)) return "Email available";
  if (getPhone(contact)) return "Phone available";
  return "";
}

function contactListPrimarySignal(contact: DiscoveryResult) {
  const opportunity = contactOpportunityAssessment(contact);
  if (opportunity.level !== "unknown" && opportunity.signals[0]) {
    return truncateText(opportunity.signals[0], 88);
  }

  const rating = getRating(contact);
  const reviews = getReviewCount(contact);
  if (rating && reviews) return `${rating} stars · ${reviews} reviews`;
  if (isVerifiedContact(contact) && bulkOutreachEmail(contact)) return "Verified email available";
  if (contact.website_url || contact.research?.website_url) return "Public website available";
  if (bulkOutreachEmail(contact)) return "Public email available";
  if (getPhone(contact)) return "Public phone available";
  return "Public business listing available";
}

function contactWebsitePresenceLabel(contact: DiscoveryResult) {
  const status = contactResolvedWebsiteStatus(contact);
  if (status === "unavailable") return "Website unavailable";
  if (status === "parked") return "Parked website recorded";
  return "Website not verified";
}

function contactDrawerSummary(contact: DiscoveryResult) {
  const summary = cleanContactListText(contact.research?.summary || "");
  if (summary && !isNoisyEnrichmentText(summary) && summary.length <= 260) {
    return summary;
  }

  const assessment = getAgentAssessment(contact);
  const rationale = cleanContactListText(assessment?.rationale || "");
  if (rationale && !isNoisyEnrichmentText(rationale) && !isInternalQualificationText(rationale)) {
    return truncateText(rationale, 260);
  }

  const signals = [
    ...(assessment?.positiveSignals || []),
    ...(contact.research?.signals || []),
  ]
    .map(cleanContactEvidenceText)
    .filter((signal) => signal && !isNoisyEnrichmentText(signal) && !isLowValueContactListText(signal))
    .slice(0, 2);
  const geography = contact.geography || contact.research?.geography || "";
  const website = contact.website_url || contact.research?.website_url || "";
  const contactSignal = bulkOutreachEmail(contact)
    ? isVerifiedContact(contact)
      ? "a verified email"
      : "an email"
    : getPhone(contact)
      ? "a phone number"
      : "";
  const description = [
    `${contact.company_name} is listed as a ${contactListCategoryLabel(contact).toLowerCase()}${geography ? ` in ${geography}` : ""}.`,
    website ? `Public website evidence is available from ${displayUrl(website)}.` : "",
    contactSignal ? `ScoutLead found ${contactSignal} for outreach review.` : "",
    signals.length ? `Signals: ${signals.join("; ")}.` : "",
  ]
    .filter(Boolean)
    .join(" ");
  return description || "No research summary captured yet.";
}

function cleanContactListText(value: string) {
  return value
    .replace(/\s+/g, " ")
    .replace(/\bfrom\s+\d+\s+inspected\s+pages?\b/gi, "")
    .replace(/\bcontact\s+us\b/gi, "")
    .trim()
    .replace(/[|,;\s]+$/g, "")
    .trim();
}

function cleanContactEvidenceText(value: string) {
  const cleaned = cleanContactListText(value);
  const parts = cleaned
    .split(/\s+\|\s+/)
    .map((part) => part.trim())
    .filter((part) => part && !isContactMetadataText(part));
  return parts.join(" ").trim();
}

function isNoisyEnrichmentText(value: string) {
  return /website enrichment found|inspected pages|skip to content|home kitchen cabinet|call us or fill out/i.test(value);
}

function isInternalQualificationText(value: string) {
  return /matched (?:cached|existing) (?:public )?business evidence|fit \d+|source quality \d+|reachability \d+/i.test(value);
}

function isLowValueContactListText(value: string) {
  return /^(public email|email found|phone found|verified|unknown)$/i.test(value.trim()) || isContactMetadataText(value);
}

function isContactMetadataText(value: string) {
  const text = value.trim();
  return (
    isAddressLikeText(text) ||
    /^(phone|rating|reviews?):/i.test(text) ||
    /^reviews?\s+\d+/i.test(text)
  );
}

function isAddressLikeText(value: string) {
  return /\b\d{1,6}\s+[^|,;]*(?:\bst(?:reet)?\b|\brd\b|\broad\b|\bave(?:nue)?\b|\bdr(?:ive)?\b|\bblvd\b|\bboulevard\b|\bunit\b|\bsuite\b|\bste\b|#)/i.test(
    value,
  );
}

function contactMissingEvidenceLine(contact: DiscoveryResult) {
  const missing = getAgentAssessment(contact)?.missingEvidence.find((item) => {
    const cleaned = cleanContactListText(item || "");
    return cleaned && !isNoisyMissingEvidence(cleaned);
  });
  if (missing) return `Missing: ${truncateText(missing, 110)}`;
  if (!contact.contact_email && !contact.research?.contact_email) return `Missing: email`;
  if (!isVerifiedContact(contact)) return `Missing: verified contact`;
  return "";
}

function isNoisyMissingEvidence(value: string) {
  return /solo|owner[-\s]?operated|company size|number of employees|employee count|crew size|owner name not found|specific product\/problem (fit evidence is (weak|limited)|signal not found)|explicit quote or estimate workflow signal not found/i.test(
    value,
  );
}

function messageStatusLabel(status: string) {
  const labels: Record<string, string> = {
    draft: "Draft",
    pending_approval: "Pending approval",
    approved: "Approved",
    sent: "Sent",
    failed: "Failed",
    replied: "Replied",
    cancelled: "Cancelled",
  };
  return labels[status] || status.replace(/_/g, " ");
}

function contactActivityItems(contact: DiscoveryResult, message: Message | undefined): ContactActivityItem[] {
  const review = reviewStatus(contact);
  const verification = verificationStatus(contact);
  const policy = contactPolicyStatus(contact);
  const reviewed = review !== "unreviewed";
  const approvedAt = messageApprovalDate(message);
  const sentAt = message?.sent_at || contact.last_contacted_at || "";
  const messageFailed = message?.status === "failed" || message?.status === "cancelled";
  const messageSent = Boolean(sentAt || message?.status === "sent" || message?.status === "replied");
  const messageApproved = Boolean(approvedAt || messageSent || message?.status === "approved");
  const items: ContactActivityItem[] = [
    {
      label: "Found",
      detail: formatActivityDate(contact.created_at) || "Captured",
      complete: true,
      tone: "done",
    },
    {
      label: "Verified",
      detail: [
        verificationStatusLabel(verification),
        contact.verification_checked_at ? formatActivityDate(contact.verification_checked_at) : "",
      ]
        .filter(Boolean)
        .join(" · "),
      complete: verification !== "unverified",
      tone: activityToneForVerification(verification),
    },
    {
      label: "Reviewed",
      detail: [reviewStatusLabel(review), contact.reviewed_at ? formatActivityDate(contact.reviewed_at) : ""]
        .filter(Boolean)
        .join(" · "),
      complete: reviewed,
      tone: reviewed ? activityToneForReview(review) : "pending",
    },
    {
      label: "Shortlisted",
      detail: contact.shortlisted_at ? formatActivityDate(contact.shortlisted_at) || "Shortlisted" : "Not shortlisted",
      complete: Boolean(contact.shortlisted_at),
      tone: contact.shortlisted_at ? "done" : "pending",
    },
    {
      label: "Draft",
      detail: message
        ? [messageStatusLabel(message.status), formatActivityDate(message.created_at)].filter(Boolean).join(" · ")
        : "No draft yet",
      complete: Boolean(message),
      tone: messageFailed ? "blocked" : message ? "done" : "pending",
    },
    {
      label: "Approved",
      detail: messageApproved ? formatActivityDate(approvedAt || message?.updated_at || sentAt) || "Approved" : "Not approved",
      complete: messageApproved,
      tone: messageApproved ? "done" : messageFailed ? "blocked" : "pending",
    },
    {
      label: "Outreach",
      detail: message?.status === "replied"
        ? `Replied · ${formatActivityDate(message.updated_at) || "Marked replied"}`
        : messageSent
          ? `Sent · ${formatActivityDate(sentAt || message?.updated_at) || "Sent"}`
          : message?.status === "approved"
            ? "Approved, not sent"
            : "Not sent",
      complete: messageSent,
      tone: messageFailed ? "blocked" : message?.status === "approved" ? "warning" : messageSent ? "done" : "pending",
    },
  ];

  if (policy !== "allowed") {
    items.push({
      label: "Blocked",
      detail: [
        contactPolicyStatusLabel(policy),
        contact.contact_policy_checked_at ? formatActivityDate(contact.contact_policy_checked_at) : "",
      ]
        .filter(Boolean)
        .join(" · "),
      complete: true,
      tone: "blocked",
    });
  }

  return items;
}

function renderBulkTemplatePreview(
  template: string,
  contact: DiscoveryResult | undefined,
  product: Product | undefined,
) {
  if (!contact) return template.trim();
  const geography = contact.geography || contact.research?.geography || product?.target_geography || "";
  const fitReason =
    contact.qualification?.rationale ||
    contact.research?.summary ||
    contact.description ||
    "";
  const contactName = getContactName(contact);
  const tokens: Record<string, string> = {
    business_name: contact.company_name,
    company_name: contact.company_name,
    contact_name: contactName || `${contact.company_name} team`,
    recipient_name: contactName || `${contact.company_name} team`,
    geography,
    service_area: geography,
    fit_reason: fitReason,
    website_url: contact.website_url || contact.research?.website_url || "",
    product_name: product?.product_name || "our product",
    product_description: product?.product_description || "",
    value_proposition: product?.value_proposition || "",
    problem: product?.problem_being_solved || "field-service quoting",
    outreach_objective: product?.outreach_objective || "",
  };
  return template
    .replace(/{{\s*([a-zA-Z0-9_]+)\s*}}/g, (_match, key: string) => tokens[key.toLowerCase()] || "")
    .trim();
}

function mergeBatchMessages(current: Message[], updates: Message[]) {
  const merged = new Map(current.map((message) => [message.id, message]));
  for (const message of updates) {
    merged.set(message.id, message);
  }
  return Array.from(merged.values());
}

function activityToneForVerification(status: ContactVerificationStatus): ContactActivityTone {
  if (status === "valid") return "done";
  if (status === "risky" || status === "unknown") return "warning";
  if (status === "invalid") return "blocked";
  return "pending";
}

function activityToneForReview(status: LeadReviewStatus): ContactActivityTone {
  if (status === "not_fit") return "blocked";
  if (status === "maybe") return "warning";
  if (status === "good_fit") return "done";
  return "pending";
}

function messageApprovalDate(message: Message | undefined) {
  if (!isRecord(message?.approval)) return "";
  return rawValueToString(message.approval.approved_at);
}

function formatActivityDate(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return formatDate(date.toISOString());
}

function emptyBatchCopy(
  contactCount: number,
  state?: "setup" | "scoring" | "retrying" | "ready" | "empty" | "partial" | "failed",
  failureClass?: "rate_limit" | "quota" | "other" | null,
) {
  if (contactCount) {
    return {
      title: "No leads match this view.",
      detail: "Change the search or filter to inspect the leads in this batch.",
    };
  }
  if (state === "retrying") {
    return {
      title: "Retrying this lead batch.",
      detail: "The previous attempt failed. The worker has queued an automatic retry.",
    };
  }
  if (state === "scoring" || state === "setup") {
    return {
      title: "Building this lead batch.",
      detail: "Candidate evaluation is still running. Results will appear automatically.",
    };
  }
  if (state === "failed") {
    const cause = failureClass === "rate_limit"
      ? "The scoring worker hit a provider rate limit."
      : failureClass === "quota"
        ? "The scoring worker has no remaining provider quota."
        : "The scoring worker exhausted its retries.";
    return {
      title: "This lead batch could not be completed.",
      detail: `${cause} Check the worker logs before trying again.`,
    };
  }
  return {
    title: "No eligible leads in this batch.",
    detail: "No indexed business passed the audience criteria for this delivery.",
  };
}

function formatCompactDate(value?: string | null) {
  if (!value) return "not scheduled";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "not scheduled";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function outcomeLabel(value: string) {
  return leadOutcomeOptions.find((option) => option.value === value)?.label || value.replace(/_/g, " ");
}

function workflowViewLabel(view: LeadWorkflowView) {
  if (view === "inbox") return "Leads";
  if (view === "this_week") return "This week";
  if (view === "shortlisted") return "Shortlisted";
  if (view === "contacted") return "Contacted";
  if (view === "dismissed") return "Dismissed";
  return "All leads";
}

function refillPolicyLabel(value: Territory["refill_policy"]) {
  if (value === "when_depleted") return "Refill when depleted";
  if (value === "biweekly") return "Every two weeks";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function profileTradeLabel(value: string) {
  const labels: Record<string, string> = {
    painters: "Painters",
    hvac: "HVAC",
    roofers: "Roofers",
    plumbers: "Plumbers",
    electricians: "Electricians",
  };
  return labels[value] || profileValueLabel(value);
}

function profileSignalLabel(value: string) {
  const labels: Record<string, string> = {
    website_unavailable: "Missing or unavailable website",
    no_quote_flow: "No quote or booking flow",
    no_contact_form: "No contact form",
    reviews_under_15: "Reviews under 15",
  };
  return labels[value] || profileValueLabel(value);
}

function profileExclusionLabel(value: string) {
  const labels: Record<string, string> = {
    closed: "Closed or inactive",
    chains: "Chains",
    franchises: "Franchises",
    directories: "Directories",
    agencies: "Marketing agencies",
  };
  return labels[value] || profileValueLabel(value);
}

function profileValueLabel(value: string) {
  return titleCase(value.replace(/_/g, " "));
}

function matchesWorkflowView(
  contact: DiscoveryResult,
  view: LeadWorkflowView,
  context: { includeAllLeads: boolean; thisWeekCutoffMs: number },
) {
  if (view === "inbox") return reviewStatus(contact) === "unreviewed";
  if (view === "this_week") {
    if (context.includeAllLeads) return true;
    const createdAt = new Date(contact.created_at).getTime();
    return Number.isFinite(createdAt) && createdAt >= context.thisWeekCutoffMs;
  }
  if (view === "shortlisted") return Boolean(contact.shortlisted_at);
  if (view === "contacted") return Boolean(contact.last_contacted_at || contact.latest_outcome);
  if (view === "dismissed") return reviewStatus(contact) === "not_fit" || isContactBlocked(contact);
  return true;
}

function deduplicateContacts(contacts: DiscoveryResult[]) {
  const unique = new Map<string, DiscoveryResult>();
  const order: string[] = [];

  for (const contact of contacts) {
    const key = contactBusinessKey(contact);
    const existing = unique.get(key);
    if (!existing) {
      unique.set(key, contact);
      order.push(key);
      continue;
    }
    if (contactRecordPriority(contact) > contactRecordPriority(existing)) {
      unique.set(key, contact);
    }
  }

  return order.map((key) => unique.get(key)).filter((contact): contact is DiscoveryResult => Boolean(contact));
}

function contactBusinessKey(contact: DiscoveryResult) {
  const name = contact.company_name.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const website = contact.website_url || contact.research?.website_url || "";
  try {
    const domain = new URL(website).hostname.replace(/^www\./, "").toLowerCase();
    if (domain) return `domain:${domain}`;
  } catch {
    // Continue with canonical and public-listing identity fields.
  }

  const phone = getPhone(contact).replace(/\D+/g, "");
  if (name && phone) return `name-phone:${name}|${phone}`;
  if (contact.business_id) return `business:${contact.business_id}`;

  const geography = (contact.geography || contact.research?.geography || "")
    .toLowerCase()
    .split(",")
    .slice(0, 2)
    .join(" ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
  if (name) return `${name}|${geography}`;
  return contact.id;
}

function contactRecordPriority(contact: DiscoveryResult) {
  return (
    Number(Boolean(contact.shortlisted_at)) * 1_000
    + Number(reviewStatus(contact) !== "unreviewed") * 400
    + Number(isVerifiedContact(contact)) * 200
    + Number(Boolean(bulkOutreachEmail(contact))) * 100
    + Number(Boolean(contact.research)) * 25
    + contactOpportunityAssessment(contact).score
  );
}

function formatLeadAge(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const elapsed = Date.now() - date.getTime();
  const hours = Math.max(0, Math.floor(elapsed / 3_600_000));
  if (hours < 1) return "Now";
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

type ContactOpportunity = {
  label: string;
  level: "high" | "moderate" | "low" | "none" | "unknown";
  score: number;
  signals: string[];
};

function contactOpportunityAssessment(contact: DiscoveryResult): ContactOpportunity {
  const searchMatch = contactSearchMatch(contact);
  if (searchMatch.status === "unknown") {
    return {
      label: "Needs verification",
      level: "unknown",
      score: 0,
      signals: [
        searchMatch.reason || "Current evidence is still being checked against the search criteria.",
      ],
    };
  }
  const profileOpportunity = contactProfileMatchOpportunity(contact);
  if (profileOpportunity) return profileOpportunity;
  const websiteStatus = contactResolvedWebsiteStatus(contact);
  for (const raw of getRawObjects(contact).reverse()) {
    const value = getRawValue(raw, "digital_opportunity")
      ?? getRawValue(raw, "raw_payload.digital_opportunity")
      ?? getRawValue(raw, "evidence.digital_opportunity")
      ?? getRawValue(raw, "business_index_opportunity_evidence.digital_opportunity");
    if (!isRecord(value)) continue;
    const levelValue = typeof value.level === "string" ? value.level.toLowerCase() : "unknown";
    const level = (["high", "moderate", "low", "none"] as const).find((item) => item === levelValue) || "unknown";
    const score = typeof value.score === "number" && Number.isFinite(value.score) ? value.score : 0;
    const signalRecords = Array.isArray(value.signals)
      ? value.signals
          .filter(isRecord)
      : [];
    const noWebsiteSignals = signalRecords.filter((signal) =>
      ["no_website_found", "no_website_listed"].includes(rawValueToString(signal.key)),
    );
    const signals = signalRecords
      .filter(
        (signal) =>
          websiteStatus !== "present"
          || !["no_website_found", "no_website_listed"].includes(rawValueToString(signal.key)),
      )
      .map((signal) => (typeof signal.message === "string" ? signal.message.trim() : ""))
      .filter(Boolean);
    if (websiteStatus === "present" && noWebsiteSignals.length && !signals.length) {
      return { label: "No clear signal", level: "none", score: 0, signals: [] };
    }
    if (
      websiteStatus !== "present"
      && noWebsiteSignals.length > 0
      && noWebsiteSignals.length === signalRecords.length
    ) {
      return {
        label: "Needs verification",
        level: "unknown",
        score: 0,
        signals: ["No website is recorded in the checked sources; verify before outreach."],
      };
    }
    return { label: opportunityLabel(level), level, score, signals };
  }
  return { label: "Not audited", level: "unknown", score: 0, signals: [] };
}

function contactProfileMatchOpportunity(contact: DiscoveryResult): ContactOpportunity | null {
  for (const raw of getRawObjects(contact).reverse()) {
    const profileMatch = getRawValue(raw, "profile_match");
    if (!isRecord(profileMatch)) continue;
    const evidence = isRecord(profileMatch.signals) ? profileMatch.signals : {};
    const selectedSignals = Object.entries(evidence).flatMap(([key, value]) =>
      isRecord(value) ? [[key, value] as const] : [],
    );
    if (!selectedSignals.length) {
      return { label: "Not requested", level: "unknown", score: 0, signals: [] };
    }
    const matchedSignals = selectedSignals.filter(([, value]) => value.matched === true);
    if (!matchedSignals.length) {
      return { label: "No clear signal", level: "none", score: 0, signals: [] };
    }
    const confirmedSignals = matchedSignals.filter(([, value]) =>
      rawValueToString(value.confidence || "confirmed") === "confirmed",
    );
    if (!confirmedSignals.length) {
      return {
        label: "Possible",
        level: "moderate",
        score: Math.min(65, 50 + (matchedSignals.length - 1) * 5),
        signals: matchedSignals.map(([key, value]) => profileSignalMessage(key, value)),
      };
    }
    return {
      label: "Confirmed",
      level: "high",
      score: Math.min(100, 70 + (matchedSignals.length - 1) * 10),
      signals: matchedSignals.map(([key, value]) => profileSignalMessage(key, value)),
    };
  }
  return null;
}

function profileSignalMessage(signalKey: string, evidence: Record<string, unknown>) {
  const value = evidence.value;
  if (signalKey === "website_unavailable") {
    if (rawValueToString(value) === "not_listed") {
      return "No website is listed in the source profile; website presence is not yet independently verified.";
    }
    return `Website status is confirmed as ${rawValueToString(value) || "unavailable"}.`;
  }
  if (signalKey === "no_quote_flow") {
    return "No quote or booking flow was found in the stored inspection.";
  }
  if (signalKey === "no_contact_form") {
    return "No contact form was found in the stored inspection.";
  }
  if (signalKey === "reviews_under_15") {
    const count = typeof value === "number" && Number.isFinite(value) ? value : 0;
    return `The business has ${count} public review${count === 1 ? "" : "s"}.`;
  }
  const factKey = rawValueToString(evidence.fact_key) || signalKey;
  return `${factKey}: ${rawValueToString(value) || String(value)}`;
}

function contactResolvedWebsiteStatus(contact: DiscoveryResult) {
  let storedStatus = "";
  for (const raw of getRawObjects(contact)) {
    const status = rawValueToString(
      getRawValue(raw, "business_facts.website_status.value")
      ?? getRawValue(raw, "business_facts.website_status"),
    );
    if (["unavailable", "parked"].includes(status)) return status;
    if (status && !storedStatus) storedStatus = status;
  }
  if (contact.website_url || contact.research?.website_url) return "present";
  return storedStatus || "unknown";
}

function opportunityLabel(level: ContactOpportunity["level"]) {
  if (level === "high") return "High";
  if (level === "moderate") return "Moderate";
  if (level === "low") return "Low";
  if (level === "none") return "No clear signal";
  return "Not audited";
}

function contactOpportunityReasons(contact: DiscoveryResult) {
  const assessment = contactOpportunityAssessment(contact);
  if (assessment.signals.length) return assessment.signals;

  const painSignals = (contact.research?.pain_indicators || [])
    .map((signal) => signal.trim())
    .filter(Boolean);
  if (painSignals.length) return [...new Set(painSignals)];

  const missing = contactMissingEvidenceLine(contact)
    .replace(/^Missing:\s*/i, "")
    .trim();
  if (missing && !/specific product\/problem fit evidence is weak/i.test(missing)) return [missing];

  const evidence = contactListEvidenceLine(contact).trim();
  return evidence ? [evidence] : [];
}

function contactScore(contact: DiscoveryResult) {
  if (contact.qualification?.score_breakdown) return clampScore(contact.qualification.score);
  return legacyFitScore(contact);
}

function contactSignals(contact: DiscoveryResult) {
  const signals = [
    ...(contact.research?.signals || []),
    ...(contact.research?.pain_indicators || []).map((signal) => `Pain: ${signal}`),
    ...(contact.qualification?.criteria || []).flatMap((criterion) => criterion.evidence || []),
  ];
  return signals.length ? [...new Set(signals)].slice(0, 5) : [contact.status.replace(/_/g, " ")];
}

function disqualificationReason(contact: DiscoveryResult) {
  if (contact.status !== "disqualified") return "";
  const flags = contact.research?.disqualifiers?.length ? `Flags: ${contact.research.disqualifiers.join(", ")}` : "";
  return [contact.qualification?.rationale, flags].filter(Boolean).join(" ");
}

function runTitle(runName: string, query: string) {
  const cleaned = runName.replace(/\s+discovery\s+\d{4}-.*/i, "").trim();
  if (cleaned && !/^contacts$/i.test(cleaned) && !/\bdiscovery\b/i.test(runName)) return titleCase(cleaned);
  const intentTitle = titleFromQuery(query);
  if (intentTitle) return intentTitle;
  const beforeWith = query.split(/\s+with\s+/i)[0]?.trim();
  return titleCase(beforeWith || "Contact list");
}

function titleFromQuery(query: string) {
  const clean = query
    .replace(/^(list|find|get|show)\s+/i, "")
    .replace(/^(independent|local|small)\s+/i, "")
    .trim();
  const match = clean.match(/^(.+?)\s+(?:in|near|around)\s+(.+?)(?:\s+(?:with|that|who|which|where)\b|$)/i);
  if (!match) return "";
  const subject = match[1]
    .replace(/\bcontacts?\b/gi, "")
    .replace(/\bcompanies\b/gi, "businesses")
    .trim();
  const location = match[2].replace(/[,.].*$/, "").trim();
  if (!subject || !location) return "";
  return `${titleCase(subject)} · ${titleCase(location)}`;
}

function titleCase(value: string) {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => `${word.slice(0, 1).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}

function displayUrl(value: string) {
  if (!value) return "";
  try {
    const parsed = new URL(value);
    return parsed.hostname.replace(/^www\./, "");
  } catch {
    return value;
  }
}

function truncateText(value: string, maxLength: number) {
  const compact = value.replace(/\s+/g, " ").trim();
  if (compact.length <= maxLength) return compact;
  return `${compact.slice(0, Math.max(0, maxLength - 3)).trim()}...`;
}

function getAddress(contact: DiscoveryResult) {
  return getRawString(contact, [
    "formattedAddress",
    "formatted_address",
    "address",
    "streetAddress",
    "fullAddress",
    "location.address",
    "location.name",
    "data.location",
  ]);
}

function getRating(contact: DiscoveryResult) {
  const value = getRawNumber(contact, ["rating", "averageRating", "stars", "reviewRating", "stats.rating"]);
  return value ? value.toFixed(1) : "";
}

function getReviewCount(contact: DiscoveryResult) {
  const value = getRawNumber(contact, [
    "userRatingCount",
    "user_ratings_total",
    "reviewCount",
    "reviewsCount",
    "reviews",
    "stats.reviews",
  ]);
  return value ? String(value) : "";
}

function getPhone(contact: DiscoveryResult) {
  return getRawString(contact, [
    "normalized_contact_phone",
    "contact_phone",
    "nationalPhoneNumber",
    "internationalPhoneNumber",
    "phone",
    "phoneNumber",
    "phone_number",
    "telephone",
    "contactPhone",
    "sellerPhone",
    "ownerPhone",
    "seller.phone",
    "contact.phone",
    "data.phone",
  ]);
}

function getContactUrl(contact: DiscoveryResult) {
  return getRawString(contact, [
    "contact_url",
    "contactUrl",
    "contactPageUrl",
    "contact_page_url",
    "quote_url",
    "quoteUrl",
    "booking_url",
    "bookingUrl",
    "website_enrichment.contact_url",
    "messagingUrl",
    "messaging_url",
    "seller.messagingUrl",
    "seller.profileUrl",
    "seller.profile_url",
    "profileUrl",
    "profile_url",
    "source_url",
    "listingUrl",
    "adUrl",
  ]);
}

function getContactName(contact: DiscoveryResult) {
  return getRawString(contact, [
    "normalized_contact_name",
    "contact_name",
    "contactName",
    "sellerName",
    "ownerName",
    "seller.name",
    "contact.name",
    "data.sellerName",
  ]);
}

function getPrice(contact: DiscoveryResult) {
  return getRawString(contact, ["price", "priceText", "price.text", "amount", "listing.price", "data.price"]);
}

function getPostedDate(contact: DiscoveryResult) {
  return getRawString(contact, [
    "postedAt",
    "posted_at",
    "datePosted",
    "publishedAt",
    "createdAt",
    "listing.postedAt",
    "data.postedAt",
  ]);
}

function getRawString(contact: DiscoveryResult, keys: string[]) {
  for (const raw of getRawObjects(contact)) {
    for (const key of keys) {
      const text = rawValueToString(getRawValue(raw, key));
      if (text) return text;
    }
  }
  return "";
}

function getRawNumber(contact: DiscoveryResult, keys: string[]) {
  for (const raw of getRawObjects(contact)) {
    for (const key of keys) {
      const value = getRawValue(raw, key);
      if (typeof value === "number" && Number.isFinite(value)) return value;
      if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
    }
  }
  return 0;
}

function getRawObjects(contact: DiscoveryResult) {
  const values: Record<string, unknown>[] = [];
  for (const source of contact.raw_sources || []) {
    values.push(source);
    if (isRecord(source.raw)) {
      values.push(source.raw);
      if (isRecord(source.raw.raw)) values.push(source.raw.raw);
    }
  }
  return values;
}

function getRawValue(raw: Record<string, unknown>, key: string): unknown {
  if (key in raw) return raw[key];
  return key.split(".").reduce<unknown>((value, part) => {
    if (Array.isArray(value)) {
      const index = Number(part);
      return Number.isInteger(index) ? value[index] : undefined;
    }
    if (!isRecord(value)) return undefined;
    return value[part];
  }, raw);
}

function rawValueToString(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (isRecord(value)) {
    return rawValueToString(
      value.text ?? value.name ?? value.value ?? value.formatted ?? value.display ?? value.label,
    );
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const text = rawValueToString(item);
      if (text) return text;
    }
  }
  return "";
}

function exportContactsCsv(contacts: DiscoveryResult[], fileName: string) {
  const rows = contacts.map((contact) => ({
    company: contact.company_name,
    contact_name: getContactName(contact) || contact.research?.contact_name || "",
    email: exportContactEmail(contact.contact_email || contact.research?.contact_email),
    phone: getPhone(contact),
    website: contact.website_url || contact.research?.website_url || "",
    geography: contact.geography || contact.research?.geography || "",
  }));
  const headers = Object.keys(rows[0] || { company: "" });
  const csv = [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => csvCell(row[header as keyof typeof row])).join(",")),
  ].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = normalizeExportFileName(fileName);
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value: string | number | undefined) {
  const text = String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
}

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = normalizeExportFileName(fileName);
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function formatVerificationDetails(details: Record<string, unknown> | null | undefined) {
  return verificationDetailChips(details).join("; ");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
