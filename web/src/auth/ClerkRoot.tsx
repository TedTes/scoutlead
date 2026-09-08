import {
  ArrowRight,
  Ban,
  ChevronDown,
  CheckCircle2,
  Download,
  Globe,
  ListChecks,
  Mail,
  MapPin,
  MoreVertical,
  Phone,
  Plug,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Target,
  UserCheck,
} from "lucide-react";
import { lazy, type ReactNode, Suspense, useEffect, useRef, useState } from "react";

const AuthenticatedApp = lazy(() => import("./AuthenticatedApp"));

export function RootApp() {
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const handlePopState = () => setPath(window.location.pathname);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  if (!isAppRoute(path)) return <LandingPage />;

  return (
    <Suspense fallback={<AppRouteLoading />}>
      <AuthenticatedApp />
    </Suspense>
  );
}

function isAppRoute(path: string) {
  return path === "/app" || path.startsWith("/app/") || path === "/trace" || path === "/debug/trace";
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function useRevealOnScroll<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [active, setActive] = useState(false);

  useEffect(() => {
    if (active) return;
    const node = ref.current;
    if (!node) return;
    if (prefersReducedMotion()) {
      setActive(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setActive(true);
          observer.disconnect();
        }
      },
      { threshold: 0.35 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [active]);

  return [ref, active] as const;
}

function LandingPage() {
  useEffect(() => {
    document.body.classList.add("landing-route");
    return () => document.body.classList.remove("landing-route");
  }, []);

  return (
    <main className="landing-page">
      <div className="landing-shell">
        <nav className="landing-nav" aria-label="ScoutLead">
          <div className="landing-brand">
            <span className="landing-mark">S</span>
            <div>
              <strong>ScoutLead</strong>
              <span>Discovery Console</span>
            </div>
          </div>
          <div className="landing-nav-actions">
            <a className="landing-nav-button" href="/app">
              Sign in
            </a>
          </div>
        </nav>

        <section className="landing-hero">
          <div className="landing-copy">
            <p className="landing-eyebrow">Lead qualification workspace</p>
            <h1>ScoutLead</h1>
            <p className="landing-lede">
              Find local businesses, score why they fit your product, and build a reviewed outreach pipeline that
              remembers every contact you've already seen.
            </p>
            <div className="landing-actions">
              <a className="landing-primary" href="/app">
                Sign in <ArrowRight size={16} />
              </a>
              <a className="landing-secondary" href="/app?signup=1">
                Create account
              </a>
            </div>
            <div className="landing-proof-row" aria-label="Product safeguards">
              <span>
                <ShieldCheck size={16} /> Verified contacts
              </span>
              <span>
                <CheckCircle2 size={16} /> Approval before send
              </span>
            </div>
            <div className="landing-fit-row" aria-label="Best fit">
              <span>Founder-led validation</span>
              <span>Early outbound</span>
              <span>Local service SaaS</span>
            </div>
          </div>

          <AnimatedPreview />
        </section>

        <section className="landing-section landing-workflow-section" aria-label="How ScoutLead works">
          <div className="landing-workflow-layout">
            <div>
              <div className="landing-section-heading">
                <p className="landing-eyebrow">How it works</p>
                <h2>From one sentence to a reviewed shortlist</h2>
                <p className="landing-lede">
                  Public sources are raw material. ScoutLead makes the useful layer: deduped businesses, product-fit
                  judgment, evidence, and contact state you can keep working.
                </p>
              </div>
              <div className="landing-workflow-steps">
                <LandingStep number="01" icon={<Search size={16} />} title="Describe the niche">
                  ScoutLead checks known businesses first, then refreshes public sources only to fill gaps.
                </LandingStep>
                <LandingStep number="02" icon={<Target size={16} />} title="Qualify with evidence">
                  Candidates are scored against your product with fit reasons, contactability, and missing proof
                  visible.
                </LandingStep>
                <LandingStep number="03" icon={<UserCheck size={16} />} title="Approve the next action">
                  Shortlist, pass, draft, export, or send from reviewed contacts instead of raw search results.
                </LandingStep>
              </div>
            </div>

            <WorkflowProofPreview />
          </div>
        </section>

        <section className="landing-section landing-settings-section" aria-label="Product settings">
          <div className="landing-workflow-layout landing-workflow-layout-reverse">
            <SettingsRevealPreview />
            <div>
              <div className="landing-section-heading">
                <p className="landing-eyebrow">One product, scored consistently</p>
                <h2>Fit scoring reads from your product description, not a generic checklist</h2>
                <p className="landing-lede">
                  The name, description, and optional focus hints you set once are what every candidate gets scored
                  against — the same painter can be a strong fit for one product and a weak fit for another.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="landing-section landing-integrations-section" aria-label="Integrations">
          <div className="landing-workflow-layout">
            <div>
              <div className="landing-section-heading">
                <p className="landing-eyebrow">Connect once, use everywhere</p>
                <h2>Gmail and your workflow tools — wired to your account, not each product</h2>
                <p className="landing-lede">
                  Approved outreach sends from your own connected Gmail. Nothing sends or exports until a contact is
                  approved.
                </p>
              </div>
            </div>
            <IntegrationsRevealPreview />
          </div>
        </section>

        <TrustSection />

        <section className="landing-cta" aria-label="Get started">
          <h2>Build a shortlist that gets smarter every run</h2>
          <p className="landing-lede">
            Describe your target customer and turn public business data into a private, reviewed pipeline.
          </p>
          <div className="landing-proof-row landing-cta-proof" aria-label="Included with every account">
            <span>
              <CheckCircle2 size={14} /> Verified before outreach
            </span>
            <span>
              <CheckCircle2 size={14} /> Human approval required
            </span>
            <span>
              <CheckCircle2 size={14} /> Sends from your own Gmail
            </span>
          </div>
          <div className="landing-actions">
            <a className="landing-primary" href="/app">
              Sign in <ArrowRight size={16} />
            </a>
            <a className="landing-secondary" href="/app?signup=1">
              Create account
            </a>
          </div>
        </section>

        <footer className="landing-footer">
          <div className="landing-brand">
            <span className="landing-mark">S</span>
            <div>
              <strong>ScoutLead</strong>
              <span>Discovery Console</span>
            </div>
          </div>
          <p>Discovery and outreach, built to be reviewed, not automated blindly.</p>
        </footer>
      </div>
    </main>
  );
}

function AppRouteLoading() {
  return (
    <main className="landing-page">
      <div className="landing-shell">
        <section className="landing-hero">
          <div className="landing-copy">
            <p className="landing-eyebrow">Account access</p>
            <h1>Loading ScoutLead</h1>
            <p className="landing-lede">Preparing the workspace.</p>
          </div>
        </section>
      </div>
    </main>
  );
}

const PREVIEW_LEADS = [
  {
    name: "Esposito's Painting Services",
    category: "painting contractor",
    location: "Mississauga, ON, Canada",
    score: 90,
    status: "Unknown",
    statusTone: "amber",
    fit: "Agent good fit",
    body: "Professional painting service with strong customer reviews.",
    missing: "Missing: Direct contact email or name for outreach",
  },
  {
    name: "Precision Painting Inc.",
    category: "Painting services business",
    location: "Mississauga, ON, Canada",
    score: 90,
    status: "Verified",
    statusTone: "green",
    fit: "Agent good fit",
    body: "Operating full-service painting company since 2004.",
    missing: "",
  },
  {
    name: "Buffalo Painters - Professional Painting Services Mississauga",
    category: "professional painting service",
    location: "Mississauga, ON, Canada",
    score: 90,
    status: "Verified",
    statusTone: "green",
    fit: "Agent good fit",
    body: "Professional painting service matching intended user role for QuoteVan.",
    missing: "Missing: Explicit customer problem statements from the lead.",
  },
  {
    name: "DewDrop - Professional Painting Services Mississauga",
    category: "Professional Painting Services",
    location: "Mississauga, ON, Canada",
    score: 90,
    status: "Unknown",
    statusTone: "amber",
    fit: "Agent good fit",
    body: "Painter business with a local service footprint.",
    missing: "Missing: email",
  },
];

const PREVIEW_QUERY =
  "independent residential painters in Toronto with a website, quote form, and owner contact";

const PREVIEW_RUNS = [
  { title: "Mississauga Painters", meta: "new search", count: "", date: "draft", tone: "blue" },
  { title: "Toronto Painting Services", meta: "6 · 3 verified", count: "completed", date: "Sep 7", tone: "green" },
  { title: "GTA Solo Painters", meta: "4 · 3 verified", count: "completed", date: "Sep 7", tone: "green" },
  { title: "Quote-Ready Painters", meta: "3 found", count: "researching", date: "Sep 7", tone: "amber" },
];

function AnimatedPreview() {
  const [typed, setTyped] = useState(0);
  const [showResults, setShowResults] = useState(false);
  const [visibleLeads, setVisibleLeads] = useState(0);
  const [cycle, setCycle] = useState(0);

  useEffect(() => {
    const reduceMotion =
      typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduceMotion) {
      setTyped(PREVIEW_QUERY.length);
      setShowResults(true);
      setVisibleLeads(PREVIEW_LEADS.length);
      return;
    }

    const timers: number[] = [];
    const at = (ms: number, run: () => void) => timers.push(window.setTimeout(run, ms));

    setTyped(0);
    setShowResults(false);
    setVisibleLeads(0);

    const CHAR_MS = 24;
    for (let i = 1; i <= PREVIEW_QUERY.length; i++) {
      at(i * CHAR_MS, () => setTyped(i));
    }
    const typingDone = PREVIEW_QUERY.length * CHAR_MS;

    at(typingDone + 500, () => setShowResults(true));

    const REVEAL_GAP = 260;
    PREVIEW_LEADS.forEach((_, idx) => {
      at(typingDone + 700 + idx * REVEAL_GAP, () => setVisibleLeads(idx + 1));
    });
    const revealDone = typingDone + 700 + PREVIEW_LEADS.length * REVEAL_GAP;

    at(revealDone + 2600, () => setCycle((c) => c + 1));

    return () => timers.forEach(clearTimeout);
  }, [cycle]);

  return (
    <div className="landing-preview preview-app" aria-label="ScoutLead product preview">
      <PreviewRail activeManage="" activeRun="Mississauga Painters" />
      <div className="preview-main-panel">
        <PreviewAppTopbar pageName="Mississauga Painters" />
        <div className="preview-stage">
          {showResults ? (
            <PreviewResults visibleCount={visibleLeads} />
          ) : (
            <PreviewDiscovery typedLength={typed} />
          )}
        </div>
      </div>
    </div>
  );
}

function WorkflowProofPreview() {
  const [ref, active] = useRevealOnScroll<HTMLDivElement>();
  const [visibleLeads, setVisibleLeads] = useState(0);
  const [clickedIndex, setClickedIndex] = useState(-1);
  const [drawerVisible, setDrawerVisible] = useState(false);

  useEffect(() => {
    if (!active) return;

    if (prefersReducedMotion()) {
      setVisibleLeads(PREVIEW_LEADS.length);
      setDrawerVisible(true);
      return;
    }

    const timers: number[] = [];
    const at = (ms: number, run: () => void) => timers.push(window.setTimeout(run, ms));

    const REVEAL_GAP = 220;
    PREVIEW_LEADS.forEach((_, idx) => {
      at(idx * REVEAL_GAP, () => setVisibleLeads(idx + 1));
    });
    const revealDone = PREVIEW_LEADS.length * REVEAL_GAP;

    // pause so the list settles, then simulate clicking the first result before the drawer opens
    at(revealDone + 550, () => setClickedIndex(0));
    at(revealDone + 550 + 220, () => setDrawerVisible(true));

    return () => timers.forEach(clearTimeout);
  }, [active]);

  return (
    <div className="landing-preview landing-preview-focused" aria-label="Example lead detail" ref={ref}>
      <div className="preview-main-panel">
        <PreviewAppTopbar pageName="Painting Services" />
        <div className="preview-stage">
          <PreviewResults
            showDrawer
            visibleCount={visibleLeads}
            drawerVisible={drawerVisible}
            clickedIndex={clickedIndex}
          />
        </div>
      </div>
    </div>
  );
}

function SettingsRevealPreview() {
  const [ref, active] = useRevealOnScroll<HTMLDivElement>();
  const [step, setStep] = useState(0);
  const [hintClicked, setHintClicked] = useState(false);
  const [hintAdded, setHintAdded] = useState(false);

  useEffect(() => {
    if (!active) return;

    if (prefersReducedMotion()) {
      setStep(3);
      setHintClicked(true);
      setHintAdded(true);
      return;
    }

    const timers: number[] = [];
    const at = (ms: number, run: () => void) => timers.push(window.setTimeout(run, ms));
    at(150, () => setStep(1));
    at(600, () => setStep(2));
    at(1150, () => setStep(3));
    at(1700, () => setHintClicked(true));
    at(1920, () => setHintAdded(true));

    return () => timers.forEach(clearTimeout);
  }, [active]);

  return (
    <div className="landing-preview landing-preview-focused" aria-label="Example product settings" ref={ref}>
      <div className="preview-main-panel">
        <PreviewAppTopbar pageName="Painting Services" />
        <div className="preview-stage">
          <PreviewSettings revealStep={step} hintClicked={hintClicked && !hintAdded} hintAdded={hintAdded} />
        </div>
      </div>
    </div>
  );
}

function IntegrationsRevealPreview() {
  const [ref, active] = useRevealOnScroll<HTMLDivElement>();
  const [step, setStep] = useState(0);
  const [connectClicked, setConnectClicked] = useState(false);
  const [gmailConnected, setGmailConnected] = useState(false);

  useEffect(() => {
    if (!active) return;

    if (prefersReducedMotion()) {
      setStep(3);
      setConnectClicked(true);
      setGmailConnected(true);
      return;
    }

    const timers: number[] = [];
    const at = (ms: number, run: () => void) => timers.push(window.setTimeout(run, ms));
    at(150, () => setStep(1));
    at(600, () => setStep(2));
    at(1050, () => setStep(3));
    at(2000, () => setConnectClicked(true));
    at(2000 + 220, () => setGmailConnected(true));

    return () => timers.forEach(clearTimeout);
  }, [active]);

  return (
    <div className="landing-preview landing-preview-focused" aria-label="Example integrations page" ref={ref}>
      <div className="preview-main-panel">
        <PreviewAppTopbar pageName="Painting Services" />
        <div className="preview-stage">
          <PreviewIntegrations revealStep={step} gmailConnected={gmailConnected} connectClicked={connectClicked} />
        </div>
      </div>
    </div>
  );
}

function PreviewRail({ activeManage, activeRun }: { activeManage: string; activeRun: string }) {
  return (
    <aside className="preview-rail" aria-label="Preview run history">
      <div className="preview-rail-brand">
        <span>S</span>
        <div>
          <strong>ScoutLead</strong>
          <em>Discovery Console</em>
        </div>
      </div>
      <div className="preview-rail-heading">
        <span>Run History</span>
        <button type="button" tabIndex={-1} aria-label="Add preview run">
          <Plus size={13} />
        </button>
      </div>
      <div className="preview-run-list">
        {PREVIEW_RUNS.map((run) => (
          <div className={`preview-run${run.title === activeRun ? " is-active" : ""}`} key={run.title}>
            <strong>{run.title}</strong>
            <span>
              <i className={`preview-dot tone-${run.tone}`} />
              {run.meta}
              {run.count ? <em>{run.count}</em> : null}
              <time>{run.date}</time>
            </span>
          </div>
        ))}
      </div>
      <div className="preview-manage">
        <span>Manage</span>
        <PreviewManageRow icon={<Settings size={13} />} active={activeManage === "Product settings"} label="Product settings" />
        <PreviewManageRow icon={<Plug size={13} />} active={activeManage === "Integrations"} label="Integrations" />
        <PreviewManageRow icon={<Download size={13} />} active={false} label="Export all contacts" />
      </div>
    </aside>
  );
}

function PreviewManageRow({ active, icon, label }: { active: boolean; icon: ReactNode; label: string }) {
  return (
    <div className={`preview-manage-row${active ? " is-active" : ""}`}>
      {icon}
      <strong>{label}</strong>
    </div>
  );
}

function PreviewAppTopbar({ pageName }: { pageName: string }) {
  return (
    <div className="preview-appbar">
      <button className="preview-product-trigger" type="button" tabIndex={-1}>
        <span>Product</span>
        <strong>Quotevan</strong>
        <em>- {pageName}</em>
        <ChevronDown size={13} />
      </button>
      <button className="preview-icon-button" type="button" tabIndex={-1} aria-label="Add preview page">
        <Plus size={15} />
      </button>
      <button className="preview-avatar" type="button" tabIndex={-1} aria-label="Preview account" />
    </div>
  );
}

function PreviewDiscovery({ typedLength = PREVIEW_QUERY.length }: { typedLength?: number }) {
  return (
    <section className="preview-discovery-screen" aria-label="Preview discovery input">
      <h3>Who should we find?</h3>
      <p>Describe the businesses you want to reach. ScoutLead finds them, scores fit, and pulls reachable contacts.</p>
      <div className="preview-composer">
        <span>
          {PREVIEW_QUERY.slice(0, typedLength)}
          <span className="preview-cursor" aria-hidden="true" />
        </span>
        <button type="button" tabIndex={-1} aria-label="Run preview search">
          <ArrowRight size={14} />
        </button>
      </div>
      <span className="preview-section-label">Or start from an example</span>
      <div className="preview-template-grid">
        <PreviewTemplate title="Local service shops" tag="Local">
          independent painting businesses in Toronto with a website, strong reviews, and owner contact details
        </PreviewTemplate>
        <PreviewTemplate title="Recent listings" tag="Listings">
          painting providers in Toronto with direct phone numbers, recent listings, and clear service descriptions
        </PreviewTemplate>
        <PreviewTemplate title="Quote-ready businesses" tag="Forms">
          painting businesses in Toronto with quote forms, public contact details, and proof they serve customers
        </PreviewTemplate>
      </div>
    </section>
  );
}

function PreviewTemplate({ children, tag, title }: { children: ReactNode; tag: string; title: string }) {
  return (
    <div className="preview-template">
      <div>
        <strong>{title}</strong>
        <span>{tag}</span>
      </div>
      <p>{children}</p>
    </div>
  );
}

function PreviewResults({
  showDrawer = false,
  visibleCount = PREVIEW_LEADS.length,
  drawerVisible = true,
  clickedIndex = -1,
}: {
  showDrawer?: boolean;
  visibleCount?: number;
  drawerVisible?: boolean;
  clickedIndex?: number;
}) {
  return (
    <section
      className={`preview-results-screen${showDrawer ? " has-detail" : ""}${showDrawer && drawerVisible ? " is-open" : ""}`}
      aria-label="Preview results"
    >
      <div className="preview-results-meta">6 found · 6 reachable · 3 verified · 6 good fit</div>
      <div className="preview-results-controls">
        <div className="preview-tabs">
          <strong>All <span>6</span></strong>
          <span>Shortlisted <em>0</em></span>
          <span>Needs review <em>6</em></span>
        </div>
        <div className="preview-sort-actions">
          <button type="button" tabIndex={-1}>Filter <strong>All</strong></button>
          <button type="button" tabIndex={-1}>Sort <strong>Contact</strong></button>
          <button type="button" tabIndex={-1} aria-label="More preview actions">
            <MoreVertical size={14} />
          </button>
        </div>
      </div>
      <div className="preview-results-body">
        <div className="preview-lead-list">
          {PREVIEW_LEADS.map((lead, idx) => (
            <PreviewLeadCard
              lead={lead}
              key={lead.name}
              visible={idx < visibleCount}
              clicked={idx === clickedIndex}
              selected={idx === clickedIndex}
            />
          ))}
        </div>
        {showDrawer ? <PreviewDetailDrawer visible={drawerVisible} /> : null}
      </div>
    </section>
  );
}

function PreviewLeadCard({
  clicked = false,
  lead,
  selected = false,
  visible = true,
}: {
  clicked?: boolean;
  lead: (typeof PREVIEW_LEADS)[number];
  selected?: boolean;
  visible?: boolean;
}) {
  return (
    <article
      aria-hidden={!visible}
      className={`preview-lead-card${visible ? "" : " is-hidden"}${clicked ? " is-clicked" : ""}${selected ? " is-selected" : ""}`}
    >
      <span className="preview-lead-score">{lead.score}</span>
      <div className="preview-lead-copy">
        <div className="preview-lead-title">
          <strong>{lead.name}</strong>
          <em>{lead.fit}</em>
        </div>
        <span>
          {lead.category} <MapPin size={11} /> {lead.location}
        </span>
        <p>{lead.body}</p>
        {lead.missing ? <small>{lead.missing}</small> : null}
      </div>
      <div className="preview-lead-actions">
        <strong className={`preview-status-chip tone-${lead.statusTone}`}>{lead.status}</strong>
        <Mail size={13} />
        <Phone size={13} />
      </div>
    </article>
  );
}

function PreviewDetailDrawer({ visible = true }: { visible?: boolean }) {
  return (
    <aside
      aria-hidden={!visible}
      aria-label="Preview lead drawer"
      className={`preview-detail-drawer${visible ? "" : " is-hidden"}`}
    >
      <div className={`preview-detail-drawer-content${visible ? "" : " is-hidden"}`}>
      <div className="preview-detail-head">
        <span className="preview-lead-score">90</span>
        <div>
          <strong>Esposito's Painting Services</strong>
          <span>painting contractor · Mississauga, ON, Canada</span>
        </div>
        <button type="button" tabIndex={-1} aria-label="Close preview drawer">×</button>
      </div>
      <div className="preview-detail-chips">
        <span><CheckCircle2 size={12} /> Agent good fit · 90</span>
        <span className="tone-amber"><Mail size={12} /> Email · missing</span>
        <span><Phone size={12} /> Phone</span>
      </div>
      <div className="preview-detail-tabs">
        <strong>Overview</strong>
        <span>Evidence <em>9</em></span>
      </div>
      <p>
        Esposito's Painting Services is a professional painting contractor in Mississauga with strong customer
        reviews and direct phone contact.
      </p>
      <dl className="preview-detail-list">
        <PreviewDetailRow icon={<MapPin size={14} />} label="Address" value="7199 Fayette Cir, Mississauga, ON" />
        <PreviewDetailRow icon={<Globe size={14} />} label="Website" value="espositospaintingservices.com" />
        <PreviewDetailRow icon={<UserCheck size={14} />} label="Contact" value="No contact name found" />
        <PreviewDetailRow icon={<Mail size={14} />} label="Email" value="No email found" />
        <PreviewDetailRow icon={<Phone size={14} />} label="Phone" value="(416) 809-3641" />
      </dl>
      <div className="preview-detail-footer">
        <button type="button" tabIndex={-1}>Shortlist</button>
        <button type="button" tabIndex={-1}>Pass</button>
        <button type="button" tabIndex={-1}>Review outreach <ArrowRight size={13} /></button>
      </div>
      </div>
    </aside>
  );
}

function PreviewDetailRow({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div>
      {icon}
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function PreviewIntegrations({
  connectClicked = false,
  gmailConnected = false,
  revealStep = 3,
}: {
  connectClicked?: boolean;
  gmailConnected?: boolean;
  revealStep?: number;
}) {
  return (
    <section className="preview-integrations-screen" aria-label="Preview integrations">
      <p>
        Connect where Quotevan's approved contacts and outreach go. Nothing sends or exports until you approve a
        contact.
      </p>
      <div aria-hidden={revealStep < 1} className={`preview-reveal${revealStep >= 1 ? "" : " is-hidden"}`}>
        <div className="preview-account-banner">
          <CheckCircle2 size={14} />
          <strong>Gmail & account services connect once, on your account</strong>
          <span>Account connections <ArrowRight size={12} /></span>
        </div>
      </div>
      <div aria-hidden={revealStep < 2} className={`preview-reveal${revealStep >= 2 ? "" : " is-hidden"}`}>
        <PreviewIntegrationGroup label="Sending">
          <PreviewIntegrationRow
            actionClicked={connectClicked && !gmailConnected}
            badge="G"
            green={gmailConnected}
            title="Gmail"
            status={gmailConnected ? "Connected" : "Off"}
            body={
              gmailConnected
                ? "Approved outreach now sends from your connected Gmail account."
                : "Send approved outreach from your connected Gmail account."
            }
            action={gmailConnected ? undefined : "Connect"}
          />
          <PreviewIntegrationRow badge="R" dark title="Resend" status="Disabled" body="Transactional sending from a verified domain - alternative to Gmail" action="Enable" />
        </PreviewIntegrationGroup>
      </div>
      <div aria-hidden={revealStep < 3} className={`preview-reveal${revealStep >= 3 ? "" : " is-hidden"}`}>
        <PreviewIntegrationGroup label="Workflow outputs">
          <PreviewIntegrationRow badge="S" green title="Google Sheets" body="needs Google connected - connect in account" toggle />
          <PreviewIntegrationRow badge="{}" purple title="Webhook" body="POST approved contacts as JSON - Airtable, Notion, custom, Zapier" action="Configure" toggle />
          <PreviewIntegrationRow badge="H" coral title="HubSpot" status="Later" body="Create/update CRM contacts with fit verdict and evidence" action="Soon" />
        </PreviewIntegrationGroup>
      </div>
    </section>
  );
}

function PreviewIntegrationGroup({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="preview-integration-group">
      <span className="preview-section-label">{label}</span>
      <div>{children}</div>
    </div>
  );
}

function PreviewIntegrationRow({
  action,
  actionClicked = false,
  badge,
  body,
  coral = false,
  dark = false,
  green = false,
  purple = false,
  status,
  title,
  toggle = false,
}: {
  action?: string;
  actionClicked?: boolean;
  badge: string;
  body: string;
  coral?: boolean;
  dark?: boolean;
  green?: boolean;
  purple?: boolean;
  status?: string;
  title: string;
  toggle?: boolean;
}) {
  const badgeTone = dark ? " dark" : green ? " green" : purple ? " purple" : coral ? " coral" : "";
  return (
    <div className="preview-integration-row">
      <span className={`preview-integration-badge${badgeTone}`}>{badge}</span>
      <div>
        <strong>
          {title} {status ? <em>{status}</em> : null}
        </strong>
        <p>{body}</p>
      </div>
      <div className="preview-integration-actions">
        {action ? (
          <button className={actionClicked ? "is-clicked" : ""} tabIndex={-1} type="button">
            {action}
          </button>
        ) : null}
        {toggle ? <span className="preview-toggle" /> : null}
      </div>
    </div>
  );
}

function PreviewSettings({
  revealStep = 3,
  hintClicked = false,
  hintAdded = true,
}: {
  revealStep?: number;
  hintClicked?: boolean;
  hintAdded?: boolean;
}) {
  return (
    <section className="preview-settings-screen" aria-label="Preview product settings">
      <div className="preview-settings-head">
        <span>4 runs</span>
        <span>14 contacts</span>
        <span>updated Sep 7</span>
        <button type="button" tabIndex={-1}>
          <ArrowRight size={13} /> Finder
        </button>
      </div>
      <div aria-hidden={revealStep < 1} className={`preview-reveal${revealStep >= 1 ? "" : " is-hidden"}`}>
        <PreviewSettingsField label="Product name" value="Quotevan" />
      </div>
      <div aria-hidden={revealStep < 2} className={`preview-reveal${revealStep >= 2 ? "" : " is-hidden"}`}>
        <div className="preview-settings-field">
          <strong>Product description</strong>
          <div className="preview-settings-textarea">
            QuoteVan turns a job walkthrough into a professional, priced quote you can send before you leave the
            driveway - built for solo painters and field-service pros.
          </div>
          <span>285 chars</span>
        </div>
        <p className="preview-settings-help">
          This is what the finder scores against. The more specific the product context, the sharper the fit
          scoring.
        </p>
      </div>
      <div aria-hidden={revealStep < 3} className={`preview-reveal${revealStep >= 3 ? "" : " is-hidden"}`}>
        <div className="preview-settings-field">
          <strong>Focus hints <em>optional</em></strong>
          <div className="preview-settings-chips">
            <span>Toronto / GTA</span>
            <span>Solo & small crews</span>
            <span aria-hidden={!hintAdded} className={`preview-reveal preview-settings-chip-new${hintAdded ? "" : " is-hidden"}`}>
              Insured & licensed
            </span>
            <button type="button" tabIndex={-1} className={hintClicked ? "is-clicked" : ""}>
              + add hint
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function PreviewSettingsField({ label, value }: { label: string; value: string }) {
  return (
    <div className="preview-settings-field">
      <strong>{label}</strong>
      <div className="preview-settings-input">{value}</div>
    </div>
  );
}

function LandingStep({
  children,
  icon,
  number,
  title,
}: {
  children: ReactNode;
  icon: ReactNode;
  number: string;
  title: string;
}) {
  return (
    <div className="landing-step">
      <div className="landing-step-marker">
        <span className="landing-feature-icon">{icon}</span>
        <span className="landing-step-number">{number}</span>
      </div>
      <div className="landing-step-copy">
        <h3>{title}</h3>
        <p>{children}</p>
      </div>
    </div>
  );
}

function TrustSection() {
  const [ref, active] = useRevealOnScroll<HTMLDivElement>();

  return (
    <section className="landing-section landing-trust-section" aria-label="Privacy and compliance">
      <div className="landing-section-heading">
        <p className="landing-eyebrow">Privacy and compliance</p>
        <h2>Outreach has guardrails before it reaches Gmail, exports, or webhooks</h2>
        <p className="landing-lede">
          Verification, suppression, human approval, and provider checks are handled once in the workflow.
        </p>
      </div>
      <div className={`landing-trust-row${active ? " is-active" : ""}`} ref={ref}>
        <LandingTrustItem icon={<ShieldCheck size={15} />} title="Verify first">
          Leads need a reachable email or phone before they move into outreach.
        </LandingTrustItem>
        <LandingTrustItem icon={<Ban size={15} />} title="Respect suppression">
          Bounced, opted-out, and never-contact contacts stay blocked across future runs.
        </LandingTrustItem>
        <LandingTrustItem icon={<UserCheck size={15} />} title="Require approval">
          Drafts, exports, and sends wait for a human decision.
        </LandingTrustItem>
        <LandingTrustItem icon={<ListChecks size={15} />} title="Check providers">
          Campaigns surface missing search, verification, or sending configuration before work proceeds.
        </LandingTrustItem>
      </div>
    </section>
  );
}

function LandingTrustItem({ children, icon, title }: { children: ReactNode; icon: ReactNode; title: string }) {
  return (
    <div className="landing-trust-item">
      <span>{icon}</span>
      <strong>{title}</strong>
      <p>{children}</p>
    </div>
  );
}
