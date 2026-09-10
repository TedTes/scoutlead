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
import worldMapTextureUrl from "../assets/world-map-equirectangular.svg";

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

        <GlobeActivityPreview />

        <section className="landing-section landing-story-section" aria-label="How ScoutLead works">
          <div className="landing-story-inner">
            <div className="landing-section-heading landing-story-heading">
              <div className="landing-story-title">
                <p className="landing-eyebrow">How it works</p>
                <h2>How a search becomes a reviewed shortlist</h2>
              </div>
              <p className="landing-lede">
                ScoutLead follows one loop: ask for a niche, reuse what is already known, score each business against
                the product, then review the contact before outreach.
              </p>
            </div>
            <div className="landing-story-steps">
              <LandingStep number="01" icon={<Search size={16} />} title="Describe the niche">
                Start with the kind of business, location, and signals that matter for this product.
              </LandingStep>
              <LandingStep number="02" icon={<ListChecks size={16} />} title="Gather and dedupe">
                Known businesses are checked first, then public sources fill the gaps without repeating contacts.
              </LandingStep>
              <LandingStep number="03" icon={<Target size={16} />} title="Score the fit">
                Each candidate gets product-fit judgment, supporting evidence, and missing proof made visible.
              </LandingStep>
              <LandingStep number="04" icon={<UserCheck size={16} />} title="Review the action">
                Shortlist, pass, export, draft, or send only after the business has been inspected.
              </LandingStep>
            </div>
          </div>
        </section>

        <section className="landing-section landing-proof-section" aria-label="Lead review example">
          <div className="landing-proof-inner">
            <div className="landing-section-heading landing-proof-heading">
              <p className="landing-eyebrow">Lead review</p>
              <h2>Click a candidate and the evidence opens beside the list</h2>
              <p className="landing-lede">
                The results stay scannable on the left while the selected business opens on the right with fit reasons,
                contact state, and approval actions.
              </p>
            </div>
            <WorkflowProofPreview />
          </div>
        </section>

        <section className="landing-section landing-settings-section" aria-label="Product settings">
          <div className="landing-workflow-layout landing-workflow-layout-reverse">
            <FitComparisonPreview />
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
    detail: {
      address: "7199 Fayette Cir, Mississauga, ON",
      contact: "No contact name found",
      email: "No email found",
      emailStatus: "Email · missing",
      evidenceCount: 9,
      overview:
        "Esposito's Painting Services is a professional painting contractor in Mississauga with strong customer reviews and direct phone contact.",
      phone: "(416) 809-3641",
      website: "espositospaintingservices.com",
    },
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
    detail: {
      address: "Mississauga, ON",
      contact: "Owner contact not published",
      email: "info@precisionpaintinginc.ca",
      emailStatus: "Email · deliverable",
      evidenceCount: 7,
      overview:
        "Precision Painting Inc. operates as a full-service painting company with a public website, local service history, and contact paths suitable for reviewed outreach.",
      phone: "Public phone found",
      website: "precisionpaintinginc.ca",
    },
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
    detail: {
      address: "Mississauga, ON",
      contact: "No contact name found",
      email: "Contact form available",
      emailStatus: "Email · review",
      evidenceCount: 8,
      overview:
        "Buffalo Painters matches the painting-service niche and local geography, with enough public evidence to review fit before deciding whether to shortlist.",
      phone: "Public phone found",
      website: "buffalopainters.ca",
    },
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
    detail: {
      address: "Mississauga, ON",
      contact: "No contact name found",
      email: "No email found",
      emailStatus: "Email · missing",
      evidenceCount: 6,
      overview:
        "DewDrop appears to serve the target painting category and location, but needs more contact evidence before it is ready for outreach.",
      phone: "Public phone found",
      website: "dewdroppainting.ca",
    },
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
  const [cursorVisible, setCursorVisible] = useState(false);
  const [cursorPressed, setCursorPressed] = useState(false);
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
    setCursorVisible(false);
    setCursorPressed(false);

    const CHAR_MS = 24;
    for (let i = 1; i <= PREVIEW_QUERY.length; i++) {
      at(i * CHAR_MS, () => setTyped(i));
    }
    const typingDone = PREVIEW_QUERY.length * CHAR_MS;

    // a cursor arrives at the send button and clicks it before results appear
    at(typingDone + 140, () => setCursorVisible(true));
    at(typingDone + 400, () => setCursorPressed(true));
    at(typingDone + 620, () => {
      setShowResults(true);
      setCursorVisible(false);
      setCursorPressed(false);
    });

    const REVEAL_GAP = 260;
    PREVIEW_LEADS.forEach((_, idx) => {
      at(typingDone + 820 + idx * REVEAL_GAP, () => setVisibleLeads(idx + 1));
    });
    const revealDone = typingDone + 820 + PREVIEW_LEADS.length * REVEAL_GAP;

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
            <PreviewDiscovery cursorPressed={cursorPressed} cursorVisible={cursorVisible} typedLength={typed} />
          )}
        </div>
      </div>
    </div>
  );
}

function WorkflowProofPreview() {
  const [ref, active] = useRevealOnScroll<HTMLDivElement>();
  const [visibleLeads, setVisibleLeads] = useState(0);
  const [cursorIndex, setCursorIndex] = useState(-1);
  const [cursorPressed, setCursorPressed] = useState(false);
  const [clickedIndex, setClickedIndex] = useState(-1);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [cycle, setCycle] = useState(0);

  useEffect(() => {
    if (!active) return;

    if (prefersReducedMotion()) {
      setVisibleLeads(PREVIEW_LEADS.length);
      setClickedIndex(0);
      setDrawerVisible(true);
      return;
    }

    const timers: number[] = [];
    const at = (ms: number, run: () => void) => timers.push(window.setTimeout(run, ms));

    const REVEAL_GAP = 220;
    const CLICK_GAP = 1280;

    setCursorIndex(-1);
    setCursorPressed(false);
    if (cycle === 0) {
      setVisibleLeads(0);
      setClickedIndex(-1);
      setDrawerVisible(false);
      PREVIEW_LEADS.forEach((_, idx) => {
        at(idx * REVEAL_GAP, () => setVisibleLeads(idx + 1));
      });
    } else {
      setVisibleLeads(PREVIEW_LEADS.length);
    }

    const revealDone = cycle === 0 ? PREVIEW_LEADS.length * REVEAL_GAP : 0;
    PREVIEW_LEADS.forEach((_, idx) => {
      const clickStart = revealDone + 360 + idx * CLICK_GAP;
      at(clickStart, () => {
        setCursorIndex(idx);
        setCursorPressed(false);
      });
      at(clickStart + 240, () => {
        setCursorPressed(true);
        setClickedIndex(idx);
        setDrawerVisible(true);
      });
      at(clickStart + 480, () => setCursorPressed(false));
      at(clickStart + 760, () => setCursorIndex(-1));
    });

    at(revealDone + 360 + PREVIEW_LEADS.length * CLICK_GAP + 720, () => setCycle((current) => current + 1));

    return () => timers.forEach(clearTimeout);
  }, [active, cycle]);

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
            cursorIndex={cursorIndex}
            cursorPressed={cursorPressed}
          />
        </div>
      </div>
    </div>
  );
}

function FitComparisonPreview() {
  const [ref, active] = useRevealOnScroll<HTMLDivElement>();
  const [nameVisible, setNameVisible] = useState(false);
  const [goodScore, setGoodScore] = useState(0);
  const [badScore, setBadScore] = useState(0);
  const [goodSettled, setGoodSettled] = useState(false);
  const [badSettled, setBadSettled] = useState(false);

  useEffect(() => {
    if (!active) return;

    if (prefersReducedMotion()) {
      setNameVisible(true);
      setGoodScore(90);
      setBadScore(25);
      setGoodSettled(true);
      setBadSettled(true);
      return;
    }

    const timers: number[] = [];
    const at = (ms: number, run: () => void) => timers.push(window.setTimeout(run, ms));

    setNameVisible(false);
    setGoodScore(0);
    setBadScore(0);
    setGoodSettled(false);
    setBadSettled(false);

    at(120, () => setNameVisible(true));

    const GOOD_STEPS = [18, 40, 62, 90];
    GOOD_STEPS.forEach((value, idx) => at(420 + idx * 110, () => setGoodScore(value)));
    const goodDone = 420 + GOOD_STEPS.length * 110;
    at(goodDone + 60, () => setGoodSettled(true));

    const badStart = goodDone + 520;
    const BAD_STEPS = [10, 18, 25];
    BAD_STEPS.forEach((value, idx) => at(badStart + idx * 110, () => setBadScore(value)));
    at(badStart + BAD_STEPS.length * 110 + 60, () => setBadSettled(true));

    return () => timers.forEach(clearTimeout);
  }, [active]);

  return (
    <div
      className="fit-compare"
      aria-label="The same business scored for two different products"
      ref={ref}
    >
      <div className={`fit-compare-name${nameVisible ? " is-visible" : ""}`}>Esposito's Painting Services</div>
      <div className="fit-compare-row">
        <div className={`fit-compare-side${goodSettled ? " is-settled" : ""}`}>
          <span className="fit-compare-score tone-good">{goodScore}</span>
          <strong className="fit-compare-verdict tone-good">Agent good fit</strong>
          <span className="fit-compare-context">for Quotevan</span>
          <span className="fit-compare-context faint">painting quotes</span>
        </div>
        <span className="fit-compare-divider">vs</span>
        <div className={`fit-compare-side${badSettled ? " is-settled" : ""}`}>
          <span className="fit-compare-score tone-bad">{badScore}</span>
          <strong className="fit-compare-verdict tone-bad">Agent not fit</strong>
          <span className="fit-compare-context">for Ledgerly</span>
          <span className="fit-compare-context faint">seller bookkeeping</span>
        </div>
      </div>
    </div>
  );
}

function IntegrationsRevealPreview() {
  const [ref, active] = useRevealOnScroll<HTMLDivElement>();
  const [step, setStep] = useState(0);
  const [cursorVisible, setCursorVisible] = useState(false);
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
    at(1780, () => setCursorVisible(true));
    at(2000, () => setConnectClicked(true));
    at(2000 + 220, () => setGmailConnected(true));

    return () => timers.forEach(clearTimeout);
  }, [active]);

  return (
    <div className="landing-preview landing-preview-focused" aria-label="Example integrations page" ref={ref}>
      <div className="preview-main-panel">
        <PreviewAppTopbar pageName="Painting Services" />
        <div className="preview-stage">
          <PreviewIntegrations
            revealStep={step}
            gmailConnected={gmailConnected}
            connectClicked={connectClicked}
            cursorVisible={cursorVisible && !gmailConnected}
          />
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

function PreviewCursor({
  className = "",
  pressed = false,
  visible = false,
}: {
  className?: string;
  pressed?: boolean;
  visible?: boolean;
}) {
  return (
    <div
      aria-hidden="true"
      className={`preview-cursor-actor${visible ? " is-visible" : ""}${pressed ? " is-pressed" : ""}${className ? ` ${className}` : ""}`}
    >
      <span className="preview-cursor-ring" />
      <svg viewBox="0 0 20 20" width="18" height="18">
        <path
          d="M3.2 1.8 L3.2 15.4 L6.6 12.2 L9 17.6 L11.5 16.5 L9.1 11.1 L14 11.1 Z"
          fill="#1f6feb"
          stroke="#ffffff"
          strokeWidth="1.1"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

function PreviewDiscovery({
  cursorPressed = false,
  cursorVisible = false,
  typedLength = PREVIEW_QUERY.length,
}: {
  cursorPressed?: boolean;
  cursorVisible?: boolean;
  typedLength?: number;
}) {
  return (
    <section className="preview-discovery-screen" aria-label="Preview discovery input">
      <h3>Who should we find?</h3>
      <p>Describe the businesses you want to reach. ScoutLead finds them, scores fit, and pulls reachable contacts.</p>
      <div className="preview-composer">
        <span>
          {PREVIEW_QUERY.slice(0, typedLength)}
          <span className="preview-cursor" aria-hidden="true" />
        </span>
        <div className="preview-composer-send">
          <button type="button" tabIndex={-1} aria-label="Run preview search">
            <ArrowRight size={14} />
          </button>
          <PreviewCursor className="preview-cursor-actor--composer" pressed={cursorPressed} visible={cursorVisible} />
        </div>
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
  cursorIndex = -1,
  cursorPressed = false,
}: {
  showDrawer?: boolean;
  visibleCount?: number;
  drawerVisible?: boolean;
  clickedIndex?: number;
  cursorIndex?: number;
  cursorPressed?: boolean;
}) {
  const selectedLead = PREVIEW_LEADS[Math.max(0, clickedIndex)] ?? PREVIEW_LEADS[0];

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
              showCursor={idx === cursorIndex}
              cursorPressed={idx === cursorIndex && cursorPressed}
            />
          ))}
        </div>
        {showDrawer ? <PreviewDetailDrawer lead={selectedLead} visible={drawerVisible} /> : null}
      </div>
    </section>
  );
}

function PreviewLeadCard({
  clicked = false,
  cursorPressed = false,
  lead,
  selected = false,
  showCursor = false,
  visible = true,
}: {
  clicked?: boolean;
  cursorPressed?: boolean;
  lead: (typeof PREVIEW_LEADS)[number];
  selected?: boolean;
  showCursor?: boolean;
  visible?: boolean;
}) {
  return (
    <article
      aria-hidden={!visible}
      className={`preview-lead-card${visible ? "" : " is-hidden"}${clicked ? " is-clicked" : ""}${selected ? " is-selected" : ""}`}
    >
      <PreviewCursor className="preview-cursor-actor--lead-card" pressed={cursorPressed} visible={showCursor} />
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

function PreviewDetailDrawer({
  lead,
  visible = true,
}: {
  lead: (typeof PREVIEW_LEADS)[number];
  visible?: boolean;
}) {
  const emailChipClass = lead.detail.emailStatus.includes("deliverable") ? "" : "tone-amber";

  return (
    <aside
      aria-hidden={!visible}
      aria-label="Preview lead drawer"
      className={`preview-detail-drawer${visible ? "" : " is-hidden"}`}
    >
      <div className={`preview-detail-drawer-content${visible ? "" : " is-hidden"}`} key={lead.name}>
        <div className="preview-detail-head">
          <span className="preview-lead-score">{lead.score}</span>
          <div>
            <strong>{lead.name}</strong>
            <span>
              {lead.category} · {lead.location}
            </span>
          </div>
          <button type="button" tabIndex={-1} aria-label="Close preview drawer">×</button>
        </div>
        <div className="preview-detail-chips">
          <span>
            <CheckCircle2 size={12} /> {lead.fit} · {lead.score}
          </span>
          <span className={emailChipClass}>
            <Mail size={12} /> {lead.detail.emailStatus}
          </span>
          <span>
            <Phone size={12} /> Phone
          </span>
        </div>
        <div className="preview-detail-tabs">
          <strong>Overview</strong>
          <span>
            Evidence <em>{lead.detail.evidenceCount}</em>
          </span>
        </div>
        <p>{lead.detail.overview}</p>
        <dl className="preview-detail-list">
          <PreviewDetailRow icon={<MapPin size={14} />} label="Address" value={lead.detail.address} />
          <PreviewDetailRow icon={<Globe size={14} />} label="Website" value={lead.detail.website} />
          <PreviewDetailRow icon={<UserCheck size={14} />} label="Contact" value={lead.detail.contact} />
          <PreviewDetailRow icon={<Mail size={14} />} label="Email" value={lead.detail.email} />
          <PreviewDetailRow icon={<Phone size={14} />} label="Phone" value={lead.detail.phone} />
        </dl>
        <div className="preview-detail-footer">
          <button type="button" tabIndex={-1}>Shortlist</button>
          <button type="button" tabIndex={-1}>Pass</button>
          <button type="button" tabIndex={-1}>
            Review outreach <ArrowRight size={13} />
          </button>
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
  cursorVisible = false,
  gmailConnected = false,
  revealStep = 3,
}: {
  connectClicked?: boolean;
  cursorVisible?: boolean;
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
            showCursor={cursorVisible}
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
  showCursor = false,
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
  showCursor?: boolean;
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
        <PreviewCursor className="preview-cursor-actor--connect" pressed={actionClicked} visible={showCursor} />
      </div>
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

type GlobeMarker = {
  lat: number;
  lng: number;
  phase: number;
  speed: number;
};

const THREE_RAD_TO_DEG = 180 / Math.PI;
const GLOBE_MARKERS: GlobeMarker[] = createGlobeMarkers(420);

function createGlobeMarkers(count: number) {
  let seed = 148735;
  const markers: GlobeMarker[] = [];
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));

  for (let index = 0; index < count; index += 1) {
    const latitudeJitter = (nextGlobeRandom() - 0.5) * (1.4 / count);
    const longitudeJitter = (nextGlobeRandom() - 0.5) * goldenAngle * 0.55;
    const y = clamp(1 - (2 * (index + 0.5)) / count + latitudeJitter, -0.98, 0.98);
    const lng = THREE_RAD_TO_DEG * ((index * goldenAngle + longitudeJitter) % (Math.PI * 2)) - 180;

    markers.push({
      lat: THREE_RAD_TO_DEG * Math.asin(y),
      lng,
      phase: nextGlobeRandom() * Math.PI * 2,
      speed: 0.95 + nextGlobeRandom() * 0.9,
    });
  }

  return markers;

  function nextGlobeRandom() {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296;
  }
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function GlobeActivityPreview() {
  const [ref, active] = useRevealOnScroll<HTMLDivElement>();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const host = ref.current;
    if (!active || !canvas || !host) return;
    const canvasElement = canvas;
    const hostElement = host;

    let animationFrame = 0;
    let disposed = false;
    let renderer: import("three").WebGLRenderer | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let disposeScene = () => {};

    void setupGlobe();

    async function setupGlobe() {
      const THREE = await import("three");
      if (disposed) return;

      const radius = 1;
      const inactiveColor = new THREE.Color(0x9aa6b2);
      const activeColor = new THREE.Color(0x00945f);
      const markerTexture = createLocationPinTexture(THREE);
      const landTexture = new THREE.TextureLoader().load(worldMapTextureUrl);
      landTexture.colorSpace = THREE.SRGBColorSpace;
      const scene = new THREE.Scene();
      const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 20);
      camera.position.set(0, 0, 8);

      renderer = new THREE.WebGLRenderer({
        alpha: true,
        antialias: true,
        canvas: canvasElement,
        powerPreference: "low-power",
        preserveDrawingBuffer: true,
      });
      renderer.setClearColor(0xffffff, 0);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

      scene.add(new THREE.AmbientLight(0xffffff, 1.15));
      const keyLight = new THREE.DirectionalLight(0xffffff, 1.7);
      keyLight.position.set(-3.4, 4.2, 5.2);
      scene.add(keyLight);
      const rimLight = new THREE.DirectionalLight(0xcbd5e1, 0.85);
      rimLight.position.set(4.5, 1.5, 3);
      scene.add(rimLight);

      const root = new THREE.Group();
      scene.add(root);

      const globe = new THREE.Group();
      globe.rotation.x = -0.1;
      globe.rotation.z = -0.025;
      root.add(globe);

      const sphere = new THREE.Mesh(
        new THREE.SphereGeometry(radius, 96, 64),
        new THREE.MeshStandardMaterial({
          color: 0xf7f9fb,
          emissive: 0xffffff,
          emissiveIntensity: 0.22,
          metalness: 0,
          roughness: 0.94,
        }),
      );
      globe.add(sphere);

      const landOverlay = new THREE.Mesh(
        new THREE.SphereGeometry(radius + 0.002, 96, 64),
        new THREE.MeshBasicMaterial({
          map: landTexture,
          transparent: true,
          opacity: 0.36,
          depthTest: true,
          depthWrite: false,
        }),
      );
      globe.add(landOverlay);

      const markerEntries = GLOBE_MARKERS.map((marker) => {
        const normal = latLngVector(THREE, marker.lat, marker.lng).normalize();
        const group = new THREE.Group();
        group.position.copy(normal).multiplyScalar(radius + 0.004);
        group.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
        const markerShape = createLocationMarker(THREE, markerTexture, inactiveColor);
        group.add(markerShape.pin);
        globe.add(group);
        return { group, marker, normal, ...markerShape };
      });

      const clock = new THREE.Clock();
      const reducedMotion = prefersReducedMotion();
      const rotationStart = -0.78;
      const rotationSpeed = reducedMotion ? 0 : 0.024;
      const worldPosition = new THREE.Vector3();
      let visibleHalfWidth = 1;
      let globeScale = 1;
      let markerHeight = 0.054;

      const resize = () => {
        const width = Math.max(1, Math.floor(hostElement.clientWidth));
        const height = Math.max(1, Math.floor(hostElement.clientHeight));
        const aspect = width / height;
        renderer?.setSize(width, height, false);
        camera.left = -aspect;
        camera.right = aspect;
        camera.top = 1;
        camera.bottom = -1;
        camera.position.z = 8;
        camera.updateProjectionMatrix();
        visibleHalfWidth = aspect;
        globeScale = Math.max(width < 560 ? 2.7 : 5.2, aspect * (width < 560 ? 1.45 : 1.55));
        root.scale.setScalar(globeScale);
        root.position.y = (width < 560 ? 0.18 : 0.34) - globeScale;
        markerHeight = width < 560 ? 0.034 : 0.028;
        renderer?.render(scene, camera);
      };

      const renderFrame = () => {
        if (disposed || !renderer) return;

        const elapsed = reducedMotion ? 9 : clock.getElapsedTime();
        globe.rotation.y = rotationStart + elapsed * rotationSpeed;

        markerEntries.forEach((entry, index) => {
          entry.group.getWorldPosition(worldPosition);
          const frontAmount = smoothStep(-0.05 * globeScale, 0.54 * globeScale, worldPosition.z);
          const isInFrame =
            worldPosition.y > -1.04 &&
            worldPosition.y < 0.5 &&
            Math.abs(worldPosition.x) < visibleHalfWidth + 0.22;
          const isVisible = frontAmount > 0.01 && isInFrame;
          const pulseWave = (Math.sin(elapsed * entry.marker.speed + entry.marker.phase) + 1) / 2;
          const randomGreenWave = (Math.sin(elapsed * 0.92 + entry.marker.phase * 1.9 + index) + 1) / 2;
          const pop = isVisible ? smoothStep(0.38, 0.66, pulseWave) * (1 - smoothStep(0.8, 1, pulseWave)) * frontAmount : 0;
          const green = Math.max(pop * 0.96, isVisible ? smoothStep(0.72, 1, randomGreenWave) * frontAmount * 0.68 : 0);
          const reveal = isVisible ? Math.max(0.24, frontAmount) : 0;

          entry.group.visible = isVisible;
          entry.group.position.copy(entry.normal).multiplyScalar(radius + 0.004);
          entry.pin.scale.set(markerHeight * (0.48 + reveal * 0.28 + pop * 0.34), markerHeight * (0.68 + reveal * 0.36 + pop * 0.52), 1);
          entry.pinMaterial.color.copy(inactiveColor).lerp(activeColor, green);
          entry.pinMaterial.opacity = reveal * (0.3 + pop * 0.28 + green * 0.52);
        });

        renderer.render(scene, camera);
        if (!reducedMotion) {
          animationFrame = window.requestAnimationFrame(renderFrame);
        }
      };

      resizeObserver = new ResizeObserver(resize);
      resizeObserver.observe(hostElement);
      resize();
      renderFrame();

      disposeScene = () => {
        markerTexture.dispose();
        landTexture.dispose();
        scene.traverse((object) => {
          const mesh = object as import("three").Mesh;
          mesh.geometry?.dispose();
          const material = mesh.material;
          if (Array.isArray(material)) {
            material.forEach((item) => item.dispose());
          } else {
            material?.dispose();
          }
        });
      };
    }

    return () => {
      disposed = true;
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
      resizeObserver?.disconnect();
      disposeScene();
      renderer?.dispose();
    };
  }, [active, ref]);

  return (
    <div
      className="globe-section"
      aria-label="Businesses lighting up green as ScoutLead finds a fit"
      ref={ref}
    >
      <div className={`globe-frame${active ? " is-active" : ""}`}>
        <canvas className="globe-canvas" ref={canvasRef} />
      </div>
    </div>
  );
}

function createLocationMarker(
  THREE: typeof import("three"),
  texture: import("three").CanvasTexture,
  inactiveColor: import("three").Color,
) {
  const pinMaterial = new THREE.SpriteMaterial({
    map: texture,
    color: inactiveColor.clone(),
    depthTest: true,
    depthWrite: false,
    transparent: true,
    opacity: 0,
  });
  const pin = new THREE.Sprite(pinMaterial);
  pin.center.set(0.5, 0.1);

  return { pin, pinMaterial };
}

function createLocationPinTexture(THREE: typeof import("three")) {
  const textureCanvas = document.createElement("canvas");
  textureCanvas.width = 96;
  textureCanvas.height = 120;
  const context = textureCanvas.getContext("2d");
  if (!context) return new THREE.CanvasTexture(textureCanvas);

  context.clearRect(0, 0, textureCanvas.width, textureCanvas.height);
  context.strokeStyle = "#ffffff";
  context.lineCap = "round";
  context.lineJoin = "round";
  context.lineWidth = 8;

  context.beginPath();
  context.moveTo(48, 108);
  context.bezierCurveTo(28, 78, 20, 60, 20, 42);
  context.bezierCurveTo(20, 25, 32, 14, 48, 14);
  context.bezierCurveTo(64, 14, 76, 25, 76, 42);
  context.bezierCurveTo(76, 60, 68, 78, 48, 108);
  context.stroke();

  context.beginPath();
  context.arc(48, 42, 11, 0, Math.PI * 2);
  context.stroke();

  const texture = new THREE.CanvasTexture(textureCanvas);
  texture.needsUpdate = true;
  return texture;
}

function latLngVector(THREE: typeof import("three"), lat: number, lng: number, radius = 1) {
  const phi = THREE.MathUtils.degToRad(90 - lat);
  const theta = THREE.MathUtils.degToRad(lng);
  return new THREE.Vector3(
    Math.sin(phi) * Math.cos(theta) * radius,
    Math.cos(phi) * radius,
    Math.sin(phi) * Math.sin(theta) * radius,
  );
}

function smoothStep(edge0: number, edge1: number, value: number) {
  const amount = Math.max(0, Math.min(1, (value - edge0) / (edge1 - edge0)));
  return amount * amount * (3 - 2 * amount);
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
