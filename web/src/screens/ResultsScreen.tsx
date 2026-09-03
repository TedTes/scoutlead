import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronDown,
  Copy,
  Download,
  Globe,
  Mail,
  MapPin,
  MoreVertical,
  Phone,
  Play,
  PlugZap,
  RotateCw,
  Search,
  Trash2,
  User,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { OverviewScreen } from "./OverviewScreen";
import { useToast } from "../shared-ui";
import { useAppData } from "../state/app-data";
import type {
  AgentFitStatus,
  ContactPolicyStatus,
  ContactVerificationStatus,
  DiscoveryResult,
  LeadContactPolicyInput,
  LeadReviewStatus,
  LeadUpdateInput,
  Message,
  SourceRequestSource,
} from "../types/domain";
import { mergeSourceProviders, normalizeActiveSourceIds } from "../utils/source-providers";

type ResultStage = "all" | "shortlisted" | "needs_review";
type ResultAttributeFilter = "good_fit" | "verified" | "not_fit" | "has_draft";
type ResultSort = "contact" | "score" | "name";
type DrawerTab = "overview" | "evidence" | "outreach";

export function ResultsScreen() {
  const {
    activeSourceIds,
    runSourceRequest,
    rerunSourceRequest,
    selectedDiscoveryRun,
    selectedDiscoveryRunId,
    selectedProduct,
    selectedProductId,
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
    markMessageReplied,
    sendApprovedShortlistWebhook,
    snapshot,
    sourceProviders,
  } = useAppData();
  const { showToast } = useToast();
  const [selectedContactId, setSelectedContactId] = useState("");
  const [draftPrompt, setDraftPrompt] = useState("");
  const [stage, setStage] = useState<ResultStage>("all");
  const [attributeFilter, setAttributeFilter] = useState<ResultAttributeFilter | null>(null);
  const [sort, setSort] = useState<ResultSort>("contact");
  const [selectedSources, setSelectedSources] = useState<SourceRequestSource[]>([]);
  const [running, setRunning] = useState(false);
  const [draftingShortlist, setDraftingShortlist] = useState(false);
  const [sendingWebhook, setSendingWebhook] = useState(false);
  const [filterMenuOpen, setFilterMenuOpen] = useState(false);
  const [sortMenuOpen, setSortMenuOpen] = useState(false);
  const [runMenuOpen, setRunMenuOpen] = useState(false);
  const filterMenuRef = useRef<HTMLDivElement | null>(null);
  const sortMenuRef = useRef<HTMLDivElement | null>(null);
  const runMenuRef = useRef<HTMLDivElement | null>(null);

  const contacts = selectedDiscoveryRunId ? snapshot.results : [];
  const providers = useMemo(() => mergeSourceProviders(sourceProviders), [sourceProviders]);
  const connectedProviders = useMemo(() => providers.filter((provider) => provider.configured), [providers]);
  const runPrompt = getRunPrompt(selectedDiscoveryRun);
  const query = draftPrompt.trim() || runPrompt;
  const selectedSource = selectedSources[0] || getRunSource(selectedDiscoveryRun) || "";
  const activeMessages = snapshot.messages.filter((message) => message.status !== "cancelled");
  const messageByLeadId = new Map(activeMessages.map((message) => [message.lead_id, message]));
  const approvedLeadIds = new Set(
    activeMessages
      .filter((message) => message.status === "approved" || message.status === "sent")
      .map((message) => message.lead_id),
  );
  const verifiedContacts = contacts.filter(isVerifiedContact).length;
  const goodFitContacts = contacts.filter(canShortlistContact).length;
  const shortlistedContacts = contacts.filter((contact) => contact.shortlisted_at).length;
  const needsReviewContacts = contacts.filter((contact) => reviewStatus(contact) === "unreviewed").length;
  const notFitContacts = contacts.filter((contact) => reviewStatus(contact) === "not_fit").length;
  const draftedLeadIds = new Set(activeMessages.map((message) => message.lead_id));
  const draftedContacts = contacts.filter((contact) => draftedLeadIds.has(contact.id)).length;
  const approvedShortlistContacts = contacts.filter(
    (contact) => contact.shortlisted_at && approvedLeadIds.has(contact.id),
  );
  const webhookReady = Boolean(
    selectedProduct?.webhook_enabled && selectedProduct.webhook_url && approvedShortlistContacts.length,
  );
  const draftableShortlistContacts = contacts.filter(
    (contact) => contact.shortlisted_at && isVerifiedContact(contact) && canShortlistContact(contact) && !draftedLeadIds.has(contact.id),
  );
  const attributeFilterOptions: Array<{ id: ResultAttributeFilter; label: string; count: number }> = [
    { id: "good_fit", label: "Good fit", count: goodFitContacts },
    { id: "verified", label: "Verified", count: verifiedContacts },
    { id: "has_draft", label: "Has draft", count: draftedContacts },
    { id: "not_fit", label: "Not fit", count: notFitContacts },
  ];
  const sortOptions: Array<{ id: ResultSort; label: string }> = [
    { id: "contact", label: "Contact" },
    { id: "score", label: "Score" },
    { id: "name", label: "Name" },
  ];
  const activeAttributeFilter = attributeFilterOptions.find((option) => option.id === attributeFilter);
  const activeSort = sortOptions.find((option) => option.id === sort) || sortOptions[0];
  const visibleContacts = contacts
    .filter((contact) => {
      if (stage === "shortlisted") return Boolean(contact.shortlisted_at);
      if (stage === "needs_review") return reviewStatus(contact) === "unreviewed";
      return true;
    })
    .filter((contact) => {
      if (attributeFilter === "verified") return isVerifiedContact(contact);
      if (attributeFilter === "good_fit") return canShortlistContact(contact);
      if (attributeFilter === "not_fit") return reviewStatus(contact) === "not_fit";
      if (attributeFilter === "has_draft") return draftedLeadIds.has(contact.id);
      return true;
    })
    .sort((a, b) => {
      if (sort === "name") return a.company_name.localeCompare(b.company_name);
      if (sort === "score") return contactScore(b) - contactScore(a);
      return Number(isReachableContact(b)) - Number(isReachableContact(a)) || contactScore(b) - contactScore(a);
    });
  const exportName = selectedDiscoveryRun?.name || selectedProduct?.product_name || "contacts";
  const selectedContact = contacts.find((contact) => contact.id === selectedContactId);
  const selectedMessage = selectedContact ? messageByLeadId.get(selectedContact.id) : undefined;

  useEffect(() => {
    setDraftPrompt(runPrompt);
    setSelectedContactId("");
    setStage("all");
    setAttributeFilter(null);
  }, [selectedDiscoveryRunId, runPrompt]);

  useEffect(() => {
    setRunMenuOpen(false);
    setFilterMenuOpen(false);
    setSortMenuOpen(false);
  }, [selectedDiscoveryRunId]);

  useEffect(() => {
    if (!runMenuOpen && !filterMenuOpen && !sortMenuOpen) return undefined;
    const closeMenus = (event: MouseEvent) => {
      if (!runMenuRef.current?.contains(event.target as Node)) {
        setRunMenuOpen(false);
      }
      if (!filterMenuRef.current?.contains(event.target as Node)) {
        setFilterMenuOpen(false);
      }
      if (!sortMenuRef.current?.contains(event.target as Node)) {
        setSortMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", closeMenus);
    return () => document.removeEventListener("mousedown", closeMenus);
  }, [filterMenuOpen, runMenuOpen, sortMenuOpen]);

  useEffect(() => {
    setSelectedSources((current) => {
      const fromRun = getRunSource(selectedDiscoveryRun);
      const validCurrent = current.filter((sourceId) => connectedProviders.some((provider) => provider.id === sourceId));
      const validActive = normalizeActiveSourceIds(activeSourceIds, connectedProviders).slice(0, 1);
      if (validActive.length) return validActive;
      if (validCurrent.length) return validCurrent.slice(0, 1);
      if (fromRun && connectedProviders.some((provider) => provider.id === fromRun)) return [fromRun];
      return connectedProviders[0] ? [connectedProviders[0].id] : [];
    });
  }, [activeSourceIds, connectedProviders, selectedDiscoveryRun]);

  const updateSearch = async () => {
    const request = draftPrompt.trim() || runPrompt;
    if (!selectedProductId || !request || !selectedSource || running) return;
    setRunning(true);
    try {
      const result = await runSourceRequest({
        product_id: selectedProductId,
        source: selectedSource,
        name: selectedDiscoveryRun?.name || undefined,
        prompt: request,
        max_results: selectedDiscoveryRun?.max_leads || 25,
        run_immediately: true,
      });
      if (result) {
        const foundCount = result.summary?.discovered_lead_count ?? 0;
        showToast({
          title: foundCount ? "Updated search complete" : "Search finished",
          message: foundCount ? `${foundCount} contact${foundCount === 1 ? "" : "s"} found.` : "No contacts were returned. Try another search.",
          tone: foundCount ? "green" : "amber",
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
    const nextName = window.prompt("Rename run", selectedDiscoveryRun.name || runTitle("", query));
    if (!nextName?.trim()) return;
    await renameDiscoveryRun(selectedDiscoveryRun.id, nextName.trim());
    setRunMenuOpen(false);
    showToast({ title: "Run renamed", tone: "green" });
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

  const rerunCurrentSearch = async () => {
    if (!selectedDiscoveryRun || running) return;
    setRunMenuOpen(false);
    setRunning(true);
    try {
      const result = await rerunSourceRequest(selectedDiscoveryRun.id);
      if (result) {
        const foundCount = result.summary?.discovered_lead_count ?? 0;
        showToast({
          title: foundCount ? "Re-run complete" : "Re-run finished",
          message: foundCount ? `${foundCount} contact${foundCount === 1 ? "" : "s"} found.` : "No contacts were returned. Try another search.",
          tone: foundCount ? "green" : "amber",
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      showToast({ title: "Re-run failed", message, tone: "red" });
    } finally {
      setRunning(false);
    }
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

  if (!selectedDiscoveryRun) {
    return <OverviewScreen />;
  }

  if (!contacts.length) {
    return <OverviewScreen emptyMessage="No contacts were returned for this run. Try a different business type, location, or wording." />;
  }

  return (
    <section className="results-workspace">
      <SearchStrip
        draftPrompt={draftPrompt}
        onChange={setDraftPrompt}
        onSubmit={updateSearch}
        query={runPrompt}
        running={running}
        ready={Boolean(selectedProductId && draftPrompt.trim().length >= 4 && selectedSource)}
      />

      <div className="results-controlbar">
        <div className="workflow-tabs" aria-label="Workflow stage">
          <button className={stage === "all" ? "active" : ""} type="button" onClick={() => setStage("all")}>
            All
            <span>{contacts.length}</span>
          </button>
          <button className={stage === "shortlisted" ? "active" : ""} type="button" onClick={() => setStage("shortlisted")}>
            Shortlisted
            <span>{shortlistedContacts}</span>
          </button>
          <button className={stage === "needs_review" ? "active" : ""} type="button" onClick={() => setStage("needs_review")}>
            Needs review
            <span>{needsReviewContacts}</span>
          </button>
        </div>

        <div className="results-control-actions">
          <div className="filter-menu-control" ref={filterMenuRef}>
            <button
              aria-expanded={filterMenuOpen}
              className={attributeFilter ? "filter-button active" : "filter-button"}
              type="button"
              onClick={() => setFilterMenuOpen((open) => !open)}
            >
              <span className="control-label">Filter</span>
              <strong>{activeAttributeFilter?.label || "All"}</strong>
              <ChevronDown size={14} />
            </button>
            {filterMenuOpen ? (
              <div className="action-menu filter-menu">
                {attributeFilter ? (
                  <button
                    type="button"
                    onClick={() => {
                      setAttributeFilter(null);
                      setFilterMenuOpen(false);
                    }}
                  >
                    Clear filter
                    <span>{contacts.length}</span>
                  </button>
                ) : null}
                {attributeFilterOptions.map((option) => (
                  <button
                    className={attributeFilter === option.id ? "active" : ""}
                    key={option.id}
                    type="button"
                    onClick={() => {
                      setAttributeFilter((current) => (current === option.id ? null : option.id));
                      setFilterMenuOpen(false);
                    }}
                  >
                    {option.label}
                    <span>{option.count}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          <div className="sort-menu-control" ref={sortMenuRef}>
            <button
              aria-expanded={sortMenuOpen}
              className="sort-button"
              type="button"
              onClick={() => setSortMenuOpen((open) => !open)}
            >
              <span className="control-label">Sort</span>
              <strong>{activeSort.label}</strong>
              <ChevronDown size={14} />
            </button>
            {sortMenuOpen ? (
              <div className="action-menu sort-menu">
                {sortOptions.map((option) => (
                  <button
                    className={sort === option.id ? "active" : ""}
                    key={option.id}
                    type="button"
                    onClick={() => {
                      setSort(option.id);
                      setSortMenuOpen(false);
                    }}
                  >
                    {option.label}
                    <span className="sort-indicator">{sort === option.id ? <Check size={12} /> : null}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          <div className="results-menu-control" ref={runMenuRef}>
            <button
              aria-expanded={runMenuOpen}
              aria-label="Run actions"
              className="menu-button"
              type="button"
              onClick={() => setRunMenuOpen((open) => !open)}
            >
              <MoreVertical size={18} />
            </button>
            {runMenuOpen ? (
              <div className="action-menu">
                <button
                  type="button"
                  disabled={!contacts.length}
                  onClick={() => exportContactsCsv(contacts, exportName, activeMessages)}
                >
                  <Download size={14} />
                  Export all contacts
                </button>
                <button
                  type="button"
                  disabled={!shortlistedContacts}
                  onClick={() => exportContactsCsv(contacts.filter((contact) => contact.shortlisted_at), `${exportName}-shortlist`, activeMessages)}
                >
                  <Download size={14} />
                  Export shortlist
                </button>
                <button
                  type="button"
                  disabled={!approvedShortlistContacts.length}
                  onClick={() => exportContactsCsv(approvedShortlistContacts, `${exportName}-approved-shortlist`, activeMessages)}
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
                  disabled={!draftableShortlistContacts.length || draftingShortlist}
                  onClick={() => void draftCurrentShortlist()}
                >
                  <Mail size={14} />
                  Generate drafts for shortlist
                </button>
                <button type="button" onClick={() => void renameCurrentRun()}>
                  Rename run
                </button>
                <button type="button" disabled={running} onClick={() => void rerunCurrentSearch()}>
                  <RotateCw size={14} />
                  Re-run search
                </button>
                <button className="danger-item" type="button" onClick={() => void deleteCurrentRun()}>
                  <Trash2 size={14} />
                  Delete this run
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {visibleContacts.length ? (
        <ul className="contact-card-list">
          {visibleContacts.map((contact) => (
            <ContactCard
              contact={contact}
              key={contact.id}
              onOpen={() => setSelectedContactId(contact.id)}
            />
          ))}
        </ul>
      ) : (
        <section className="result-empty-card">
          <strong>No contacts match this view.</strong>
          <p>
            {contacts.length
              ? "Change the filter to inspect the contacts in this run."
              : "This run has no contacts yet."}
          </p>
        </section>
      )}

      <ContactDrawer
        contact={selectedContact}
        message={selectedMessage}
        onClose={() => setSelectedContactId("")}
        onApproveMessage={approveMessage}
        onCreateDraft={createOutreachDraft}
        onQualifyLead={qualifyLead}
        onMarkMessageReplied={markMessageReplied}
        onSendMessage={sendMessage}
        onUpdateContactPolicy={updateLeadContactPolicy}
        onUpdateLead={updateLead}
        onUpdateMessage={updateMessage}
      />
    </section>
  );
}

function SearchStrip({
  draftPrompt,
  onChange,
  onSubmit,
  query,
  ready,
  running,
}: {
  draftPrompt: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  query: string;
  ready: boolean;
  running: boolean;
}) {
  return (
    <form
      className={running ? "searchbar is-running" : "searchbar"}
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <Search size={15} />
      <input
        aria-label="Search prompt"
        placeholder={query || "Describe the businesses to find"}
        value={draftPrompt}
        onChange={(event) => onChange(event.target.value)}
      />
      <button
        aria-label={running ? "Finding contacts" : "Find contacts"}
        className="runbtn icon-run"
        disabled={!ready || running}
        title={running ? "Finding contacts" : "Find contacts"}
        type="submit"
      >
        <Play size={13} />
      </button>
    </form>
  );
}

function ContactCard({ contact, onOpen }: { contact: DiscoveryResult; onOpen: () => void }) {
  const score = contactScore(contact);
  const fitStatus = displayFitStatus(contact);
  const evidence = contactEvidenceLine(contact);
  const missing = contactMissingEvidenceLine(contact);
  const verification = verificationStatus(contact);
  const policy = contactPolicyStatus(contact);
  const blocked = isContactBlocked(contact);

  return (
    <li>
      <article
        className={isReachableContact(contact) ? "contact-card" : "contact-card no-contact"}
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
        <div className="contact-main">
          <span className={`score-ring ${scoreClass(score)}`}>
            <strong>{score}</strong>
          </span>
          <span className="contact-identity">
            <span className="contact-title-line">
              <strong>{contact.company_name}</strong>
              <em className={`fit-badge ${fitStatus.className}`}>{fitStatus.label}</em>
            </span>
            <small>
              {contact.research?.business_type || contact.description || "Business"}
              {contact.geography || contact.research?.geography ? (
                <>
                  <MapPin size={12} />
                  {contact.geography || contact.research?.geography}
                </>
              ) : null}
            </small>
            <span className="contact-evidence-line">{evidence}</span>
            {missing ? <span className="contact-missing-line">{missing}</span> : null}
          </span>
        </div>
        <div className="contact-actions" aria-label="Contact availability">
          {blocked ? (
            <span className={`contact-policy-pill policy-${policy}`}>
              {contactPolicyStatusLabel(policy)}
            </span>
          ) : null}
          <span className={`verification-label verification-${verification}`}>
            {verificationStatusLabel(verification)}
          </span>
          {contact.contact_email || contact.research?.contact_email ? (
            <span className="contact-icon has" title="Email found">
              <Mail size={15} />
            </span>
          ) : (
            <span className="contact-icon missing" title="No email found">
              <Mail size={15} />
            </span>
          )}
          {getPhone(contact) ? (
            <span className="contact-icon has" title="Phone found">
              <Phone size={15} />
            </span>
          ) : (
            <span className="contact-icon missing" title="No phone found">
              <Phone size={15} />
            </span>
          )}
          {!isReachableContact(contact) ? (
            <span className="no-contact-pill">
              <AlertTriangle size={13} />
              No contact
            </span>
          ) : null}
        </div>
      </article>
    </li>
  );
}

function ContactDrawer({
  contact,
  message,
  onClose,
  onApproveMessage,
  onCreateDraft,
  onQualifyLead,
  onMarkMessageReplied,
  onSendMessage,
  onUpdateContactPolicy,
  onUpdateLead,
  onUpdateMessage,
}: {
  contact: DiscoveryResult | undefined;
  message: Message | undefined;
  onClose: () => void;
  onApproveMessage: (messageId: string) => Promise<void>;
  onCreateDraft: (leadId: string) => Promise<Message | null>;
  onQualifyLead: (leadId: string) => Promise<void>;
  onMarkMessageReplied: (messageId: string, body?: string) => Promise<void>;
  onSendMessage: (messageId: string) => Promise<void>;
  onUpdateContactPolicy: (leadId: string, update: LeadContactPolicyInput) => Promise<void>;
  onUpdateLead: (leadId: string, update: LeadUpdateInput) => Promise<void>;
  onUpdateMessage: (messageId: string, update: Partial<Message>) => Promise<void>;
}) {
  const { showToast } = useToast();
  const open = Boolean(contact);
  const score = contact ? contactScore(contact) : 0;
  const currentReviewStatus = contact ? reviewStatus(contact) : "unreviewed";
  const agentAssessment = contact ? getAgentAssessment(contact) : undefined;
  const policyStatus = contact ? contactPolicyStatus(contact) : "allowed";
  const blocked = contact ? isContactBlocked(contact) : false;
  const canShortlist = contact ? canShortlistContact(contact) && !blocked : false;
  const shortlisted = Boolean(contact?.shortlisted_at);
  const [reviewNote, setReviewNote] = useState("");
  const [qualifying, setQualifying] = useState(false);
  const [savingReview, setSavingReview] = useState(false);
  const [draftSubject, setDraftSubject] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [savingDraft, setSavingDraft] = useState(false);
  const [activeTab, setActiveTab] = useState<DrawerTab>("overview");
  const signals = contact ? contactSignals(contact) : [];
  const website = contact?.website_url || contact?.research?.website_url || "";
  const email = contact?.contact_email || contact?.research?.contact_email || "";
  const verified = contact ? isVerifiedContact(contact) : false;
  const canDraft = Boolean(!blocked && shortlisted && canShortlist && verified && email);
  const canSend = Boolean(message && message.status === "approved" && email && canDraft);
  const phone = contact ? getPhone(contact) : "";
  const contactName = contact ? getContactName(contact) : "";
  const address = contact ? getAddress(contact) : "";
  const rating = contact ? getRating(contact) : "";
  const reviewCount = contact ? getReviewCount(contact) : "";
  const price = contact ? getPrice(contact) : "";
  const posted = contact ? getPostedDate(contact) : "";
  const confidence = contact?.research?.confidence ? `${contact.research.confidence}%` : "—";
  const evidenceNotes = contact
    ? [
        ...(contact.research?.pain_indicators || []),
        ...(contact.research?.disqualifiers || []),
        ...(contact.qualification?.criteria || []).flatMap((criterion) => criterion.evidence || []),
      ].filter(Boolean)
    : [];
  const fitStatus = contact ? displayFitStatus(contact) : { label: "Needs review", className: "fit-neutral" };
  const fitScore = agentAssessment?.score ?? score;
  const verification = contact ? verificationStatus(contact) : "unverified";
  const verificationDetails = verificationDetailChips(contact?.verification_details);
  const evidenceCount = new Set([
    ...signals,
    ...evidenceNotes,
    ...verificationDetails,
    contact?.verification_reason || "",
    agentAssessment?.rationale || "",
  ].filter(Boolean)).size;

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose, open]);

  useEffect(() => {
    setReviewNote(contact?.review_note || "");
  }, [contact?.id, contact?.review_note]);

  useEffect(() => {
    setDraftSubject(message?.subject || "");
    setDraftBody(message?.body || "");
  }, [message?.id, message?.subject, message?.body]);

  useEffect(() => {
    setActiveTab("overview");
  }, [contact?.id]);

  const saveLeadUpdate = async (update: LeadUpdateInput, successTitle: string) => {
    if (!contact || savingReview) return;
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
    if (!contact || qualifying) return;
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
    if (!contact || !canShortlist) return;
    void saveLeadUpdate(
      { shortlisted: !shortlisted },
      shortlisted ? "Removed from shortlist" : "Shortlisted",
    );
  };

  const updateContactPolicy = async (update: LeadContactPolicyInput, successTitle: string) => {
    if (!contact || savingReview) return;
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
    if (!contact || savingDraft) return;
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
    <div className={`contact-drawer-overlay${open ? " open" : ""}`} aria-hidden={!open}>
      <button className="contact-drawer-backdrop" type="button" aria-label="Close details" onClick={onClose} />
      <aside className="contact-drawer-panel" aria-label="Contact details">
        {contact ? (
          <>
            <header className="contact-drawer-header">
              <div className="drawer-title-row">
                <span className={`score-ring large ${scoreClass(score)}`}>
                  <strong>{score}</strong>
                </span>
                <div className="drawer-title-copy">
                  <h2>{contact.company_name}</h2>
                  <p>
                    {contact.research?.business_type || contact.description || "Business"}
                    {contact.geography || contact.research?.geography ? ` · ${contact.geography || contact.research?.geography}` : ""}
                  </p>
                </div>
              </div>
              <button className="drawer-close" type="button" onClick={onClose} aria-label="Close">
                <X size={18} />
              </button>
            </header>

            <section className="drawer-signal-summary" aria-label="Contact summary">
              <div className={`drawer-fit-verdict ${fitStatus.className}`}>
                <Check size={22} />
                <span>{fitStatus.label}</span>
                <strong>{fitScore}</strong>
              </div>
              <div className="drawer-availability-row">
                <span className={`availability-pill verification-${verification}`}>
                  <Mail size={13} />
                  Email · {email ? emailAvailabilityLabel(contact) : "missing"}
                </span>
                <span className={phone ? "availability-pill has-contact" : "availability-pill is-muted"}>
                  <Phone size={13} />
                  {phone ? "Phone" : "No phone"}
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
              <button
                className={activeTab === "outreach" ? "active" : ""}
                type="button"
                onClick={() => setActiveTab("outreach")}
              >
                Outreach
              </button>
            </nav>

            <div className="drawer-body">
              {activeTab === "overview" ? (
                <>
                  <p className="drawer-summary">{contact.research?.summary || contact.description || "No research captured yet."}</p>

                  <dl className="drawer-detail-list drawer-info-card">
                    <DrawerRow icon={<MapPin size={16} />} label="Address">
                      {address || contact.geography || contact.research?.geography || "No address found"}
                    </DrawerRow>
                    <DrawerRow icon={<Globe size={16} />} label="Website">
                      {website ? (
                        <a href={website} target="_blank" rel="noreferrer">
                          {displayUrl(website)}
                        </a>
                      ) : (
                        <span>No website found</span>
                      )}
                    </DrawerRow>
                    <DrawerRow icon={<User size={16} />} label="Contact">
                      {contactName || contact?.research?.contact_name || "No contact name found"}
                    </DrawerRow>
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
                    <DrawerRow icon={<Phone size={16} />} label="Phone">
                      {phone || "No phone found"}
                    </DrawerRow>
                  </dl>

                  <div className="drawer-mini-grid">
                    <Mini label="Rating" value={rating || "—"} />
                    <Mini label="Reviews" value={reviewCount || "—"} />
                    <Mini label="Price" value={price || "—"} />
                    <Mini label="Posted" value={posted || "—"} />
                    <Mini label="Confidence" value={confidence} />
                  </div>
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
                          ? `${agentFitStatusLabel(agentAssessment.fitStatus)} · ${agentAssessment.score}`
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

              {activeTab === "outreach" ? (
                <section className="drawer-outreach-panel">
                  <div className="drawer-section-heading">
                    <h3>Outreach</h3>
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
                        <p className="draft-warning">
                          {blocked
                            ? "This contact is blocked from outreach."
                            : !email
                              ? "Add or find an email before sending."
                              : "Keep this contact shortlisted before sending."}
                        </p>
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
                </section>
              ) : null}
            </div>

            <footer className="drawer-footer drawer-action-footer">
              <div className="drawer-footer-secondary">
                <button
                  className={shortlisted ? "active" : ""}
                  type="button"
                  disabled={savingReview || !canShortlist}
                  onClick={toggleShortlist}
                >
                  {shortlisted ? "Shortlisted" : "Shortlist"}
                </button>
                <button
                  className={currentReviewStatus === "not_fit" ? "active" : ""}
                  type="button"
                  disabled={savingReview || blocked}
                  onClick={() => chooseReviewStatus("not_fit")}
                >
                  Pass
                </button>
              </div>
              <button className="drawer-primary-action" type="button" onClick={() => setActiveTab("outreach")}>
                Review outreach
                <ArrowRight size={14} />
              </button>
            </footer>
          </>
        ) : null}
      </aside>
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

function getRunSource(run: { source_inputs?: Record<string, unknown> } | undefined) {
  const source = run?.source_inputs?.source_request_source;
  return typeof source === "string" && source.trim() ? source.trim() : "";
}

function isReachableContact(contact: DiscoveryResult) {
  return Boolean(
    !isContactBlocked(contact)
      && verificationStatus(contact) !== "invalid"
      && (contact.contact_email || contact.research?.contact_email || getPhone(contact)),
  );
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
    good_fit: "Good fit",
    maybe: "Maybe",
    not_fit: "Not fit",
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
  const fitStatus = qualification.fit_status || deriveAgentFitStatus(qualification.qualified, qualification.score, qualification.recommended_next_step);
  const criteriaEvidence = (qualification.criteria || []).flatMap((criterion) => criterion.evidence || []);
  const criteriaMissing = (qualification.criteria || []).flatMap((criterion) => criterion.missing_evidence || []);
  return {
    fitStatus,
    score: Math.max(0, Math.min(100, Math.round(qualification.score))),
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
  const status = reviewStatus(contact);
  if (status === "not_fit") return false;
  if (status === "good_fit" || status === "maybe") return true;
  const assessment = getAgentAssessment(contact);
  return assessment?.fitStatus === "good_fit" || assessment?.fitStatus === "maybe";
}

function displayFitStatus(contact: DiscoveryResult): { label: string; className: string } {
  const status = reviewStatus(contact);
  if (status === "good_fit") return { label: "Good fit", className: "fit-good" };
  if (status === "maybe") return { label: "Maybe", className: "fit-maybe" };
  if (status === "not_fit") return { label: "Not fit", className: "fit-bad" };
  const assessment = getAgentAssessment(contact);
  if (assessment?.fitStatus === "good_fit") return { label: "Agent good fit", className: "fit-good" };
  if (assessment?.fitStatus === "maybe") return { label: "Agent maybe", className: "fit-maybe" };
  if (assessment?.fitStatus === "not_fit") return { label: "Agent not fit", className: "fit-bad" };
  return { label: "Needs review", className: "fit-neutral" };
}

function contactEvidenceLine(contact: DiscoveryResult) {
  const assessment = getAgentAssessment(contact);
  const evidence =
    assessment?.positiveSignals[0] ||
    contact.research?.signals?.[0] ||
    contact.research?.summary ||
    contact.description ||
    "Open details to review public evidence.";
  return truncateText(evidence, 128);
}

function contactMissingEvidenceLine(contact: DiscoveryResult) {
  const missing = getAgentAssessment(contact)?.missingEvidence[0];
  if (missing) return `Missing: ${truncateText(missing, 110)}`;
  if (!contact.contact_email && !contact.research?.contact_email) return `Missing: email`;
  if (!isVerifiedContact(contact)) return `Missing: verified contact`;
  return "";
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

function contactScore(contact: DiscoveryResult) {
  return Math.max(0, Math.min(100, Math.round(contact.qualification?.score ?? contact.research?.confidence ?? 0)));
}

function scoreClass(score: number) {
  if (score >= 90) return "score-great";
  if (score >= 80) return "score-good";
  if (score >= 70) return "score-warn";
  return "score-low";
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

function exportContactsCsv(contacts: DiscoveryResult[], runName: string, messages: Message[] = []) {
  const messageByLeadId = new Map(messages.map((message) => [message.lead_id, message]));
  const rows = contacts.map((contact) => ({
    shortlisted: contact.shortlisted_at ? "yes" : "no",
    company: contact.company_name,
    email: contact.contact_email || contact.research?.contact_email || "",
    contact_name: getContactName(contact) || contact.research?.contact_name || "",
    phone: getPhone(contact),
    price: getPrice(contact),
    posted: getPostedDate(contact),
    website: contact.website_url || contact.research?.website_url || "",
    geography: contact.geography || contact.research?.geography || "",
    contact_policy_status: contactPolicyStatusLabel(contactPolicyStatus(contact)),
    contact_policy_reason: contact.contact_policy_reason || "",
    last_contacted_at: contact.last_contacted_at || "",
    verification_status: verificationStatusLabel(verificationStatus(contact)),
    verification_score: contact.verification_score ?? "",
    verification_reason: contact.verification_reason || "",
    verification_details: formatVerificationDetails(contact.verification_details),
    score: String(contactScore(contact)),
    status: contactStatusLabel(contact),
    fit_verdict: displayFitStatus(contact).label,
    review_note: contact.review_note || "",
    evidence: contactEvidenceLine(contact),
    missing_evidence: contactMissingEvidenceLine(contact).replace(/^Missing:\s*/, ""),
    signals: contactSignals(contact).join("; "),
    rationale: contact.qualification?.rationale || "",
    draft_status: messageByLeadId.get(contact.id)?.status || "",
    draft_subject: messageByLeadId.get(contact.id)?.subject || "",
    draft_body: messageByLeadId.get(contact.id)?.body || "",
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
  anchor.download = `${slugify(runName)}-contacts.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value: string | number | undefined) {
  const text = String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
}

function formatVerificationDetails(details: Record<string, unknown> | null | undefined) {
  return verificationDetailChips(details).join("; ");
}

function slugify(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "contacts";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
