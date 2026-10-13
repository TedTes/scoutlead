import {
  ClerkProvider,
  SignInButton,
  SignUpButton,
} from "@clerk/react";
import {
  ArrowRight,
  Ban,
  Building2,
  ChevronDown,
  CheckCircle2,
  CircleX,
  Download,
  ExternalLink,
  Globe,
  ListChecks,
  LoaderCircle,
  Mail,
  MapPin,
  Menu,
  MoreVertical,
  Package,
  Phone,
  Plug,
  Plus,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Star,
  Target,
  UserCheck,
  UsersRound,
} from "lucide-react";
import { lazy, type ReactNode, Suspense, useEffect, useRef, useState } from "react";
import worldMapTextureUrl from "../assets/world-map-equirectangular.svg";
import { getClerkPublishableKey } from "../config/env";
import { AuthLoadingScreen } from "./AuthLoadingScreen";

const AuthenticatedApp = lazy(() => import("./AuthenticatedApp"));
const APP_ROUTE = "/app";

export function RootApp() {
  const publishableKey = getClerkPublishableKey();
  const app = <RootAppContent authEnabled={Boolean(publishableKey)} />;

  if (!publishableKey) return app;

  return <ClerkProvider publishableKey={publishableKey}>{app}</ClerkProvider>;
}

function RootAppContent({ authEnabled }: { authEnabled: boolean }) {
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const handlePopState = () => setPath(window.location.pathname);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  if (path === "/app/admin") return <LegacyAdminRedirect />;
  if (!isProtectedRoute(path)) return <LandingPage authEnabled={authEnabled} />;

  return (
    <Suspense fallback={<AuthLoadingScreen />}>
      <AuthenticatedApp />
    </Suspense>
  );
}

function isProtectedRoute(path: string) {
  return path === "/app" || path.startsWith("/app/") || path === "/admin" || path.startsWith("/admin/") || path === "/trace" || path === "/debug/trace";
}

function LegacyAdminRedirect() {
  useEffect(() => {
    window.location.replace("/admin");
  }, []);
  return <AuthLoadingScreen />;
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function useRevealOnScroll<T extends HTMLElement>(rootMargin = "0px") {
  const ref = useRef<T | null>(null);
  const [active, setActive] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (prefersReducedMotion()) {
      setActive(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        setActive(Boolean(entries[0]?.isIntersecting));
      },
      { rootMargin, threshold: 0.12 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [rootMargin]);

  return [ref, active] as const;
}

const HERO_HIGHLIGHT_TEXT = "real evidence";

function TypewriterHighlight({ active }: { active: boolean }) {
  const [typed, setTyped] = useState(() => (prefersReducedMotion() ? HERO_HIGHLIGHT_TEXT.length : 0));
  const [caretDone, setCaretDone] = useState(() => prefersReducedMotion());

  useEffect(() => {
    if (!active) return;

    if (prefersReducedMotion()) {
      setTyped(HERO_HIGHLIGHT_TEXT.length);
      setCaretDone(true);
      return;
    }

    setTyped(0);
    setCaretDone(false);

    let index = 0;
    let timer: number;

    const step = () => {
      index += 1;
      setTyped(index);
      if (index >= HERO_HIGHLIGHT_TEXT.length) {
        timer = window.setTimeout(() => setCaretDone(true), 700);
        return;
      }
      timer = window.setTimeout(step, 100);
    };

    timer = window.setTimeout(step, 400);

    return () => window.clearTimeout(timer);
  }, [active]);

  const shown = HERO_HIGHLIGHT_TEXT.slice(0, typed);
  const reserve = HERO_HIGHLIGHT_TEXT.slice(typed);
  const done = typed >= HERO_HIGHLIGHT_TEXT.length;

  return (
    <span className="landing-hero-highlight-group">
      <span className="landing-hero-highlight">
        {shown}
        {!caretDone && <span className="landing-hero-caret" aria-hidden="true" />}
      </span>
      {reserve && (
        <span className="landing-hero-highlight-reserve" aria-hidden="true">
          {reserve}
        </span>
      )}
      {done ? "." : (
        <span className="landing-hero-highlight-reserve" aria-hidden="true">
          .
        </span>
      )}
    </span>
  );
}

function LandingPage({ authEnabled }: { authEnabled: boolean }) {
  const [heroRef, heroActive] = useRevealOnScroll<HTMLElement>();

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
            <LandingSignInAction authEnabled={authEnabled} className="landing-nav-button landing-nav-signin">
              Sign in
            </LandingSignInAction>
            <LandingSignUpAction authEnabled={authEnabled} className="landing-nav-button landing-nav-primary">
              Create account
            </LandingSignUpAction>
          </div>
        </nav>

        <section className="landing-hero" ref={heroRef}>
          <div className="landing-hero-band" aria-hidden="true" />
          <div className="landing-hero-inner">
            <div className="landing-hero-head">
              <div className="landing-copy">
                <p className="landing-eyebrow">Evidence-backed local business discovery</p>
                <h1>
                  Find the right local businesses, backed by <TypewriterHighlight active={heroActive} />
                </h1>
                <p className="landing-lede">
                  Define an audience once — trade, market, the signals that mean opportunity. ScoutLead returns
                  matching businesses with the evidence behind each.
                </p>
              </div>
            </div>

            <AnimatedPreview />
          </div>
          <GlobeActivityPreview />
        </section>

        <LeadReviewSection />

        <MarketSection />

        <HowItWorksSection />

        <DataProvenanceSection />

        <OutreachSection />

        <FaqSection />

        <section className="landing-cta" aria-label="Get started">
          <div className="landing-cta-band">
            <div className="landing-cta-band-grid" aria-hidden="true" />
            <div className="landing-cta-band-glow" aria-hidden="true" />
            <div className="landing-cta-band-inner">
              <p className="landing-cta-band-prompt">
                scout&gt; <b>create audience</b>
                <span className="landing-cta-band-cursor" aria-hidden="true" />
              </p>
              <h2>Build an audience you can inspect and reuse</h2>
              <p className="landing-cta-band-sub">
                Start with one trade, one market, and the signals that make a business worth contacting.
              </p>
              <LandingSignUpAction authEnabled={authEnabled} className="landing-cta-band-button">
                Create account <ArrowRight size={16} />
              </LandingSignUpAction>
              <div className="landing-cta-band-guarantees" aria-label="Included with every account">
                <span>
                  <CheckCircle2 size={15} /> Verified before outreach
                </span>
                <span>
                  <CheckCircle2 size={15} /> Human approval required
                </span>
                <span>
                  <CheckCircle2 size={15} /> Sends from your own Gmail
                </span>
              </div>
              <div className="landing-cta-band-horizon" aria-hidden="true">
                <svg viewBox="0 0 560 70" width="560" height="70">
                  <ellipse cx="280" cy="78" fill="none" rx="280" ry="48" stroke="#2a2f37" />
                  <ellipse cx="280" cy="78" fill="none" rx="180" ry="32" stroke="#23272e" />
                  <path className="landing-cta-band-pin" d="M140 40l-4 8 4 4 4-4z" style={{ animationDelay: "0s" }} />
                  <path className="landing-cta-band-pin" d="M240 32l-4 8 4 4 4-4z" style={{ animationDelay: "0.4s" }} />
                  <path className="landing-cta-band-pin" d="M330 34l-4 8 4 4 4-4z" style={{ animationDelay: "0.8s" }} />
                  <path className="landing-cta-band-pin" d="M420 42l-4 8 4 4 4-4z" style={{ animationDelay: "0.6s" }} />
                </svg>
              </div>
            </div>
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
          <p>Discovery and outreach, built to be reviewed — not automated blindly.</p>
        </footer>
      </div>
    </main>
  );
}

function LandingSignInAction({
  authEnabled,
  children,
  className,
}: {
  authEnabled: boolean;
  children: ReactNode;
  className: string;
}) {
  if (!authEnabled) {
    return (
      <a className={className} href={APP_ROUTE}>
        {children}
      </a>
    );
  }

  return (
    <SignInButton
      mode="modal"
      fallbackRedirectUrl={APP_ROUTE}
      forceRedirectUrl={APP_ROUTE}
      signUpFallbackRedirectUrl={APP_ROUTE}
      signUpForceRedirectUrl={APP_ROUTE}
    >
      <button className={className} type="button">
        {children}
      </button>
    </SignInButton>
  );
}

function LandingSignUpAction({
  authEnabled,
  children,
  className,
}: {
  authEnabled: boolean;
  children: ReactNode;
  className: string;
}) {
  if (!authEnabled) {
    return (
      <a className={className} href={`${APP_ROUTE}?signup=1`}>
        {children}
      </a>
    );
  }

  return (
    <SignUpButton
      mode="modal"
      fallbackRedirectUrl={APP_ROUTE}
      forceRedirectUrl={APP_ROUTE}
      signInFallbackRedirectUrl={APP_ROUTE}
      signInForceRedirectUrl={APP_ROUTE}
    >
      <button className={className} type="button">
        {children}
      </button>
    </SignUpButton>
  );
}

const PREVIEW_LEADS = [
  {
    name: "ONCALL Heating and Cooling",
    category: "local service provider",
    location: "Scarborough, ON, Canada",
    score: 96,
    status: "Verified",
    statusTone: "green",
    fit: "Strong fit",
    body: "The business has 4 public reviews.",
    missing: "",
    detail: {
      address: "54B Shorting Rd, Scarborough, ON",
      contact: "Public business profile",
      email: "No email found",
      emailStatus: "Email · unavailable",
      why: "The business has 4 public reviews, below this audience's threshold of 15.",
      opportunityLabel: "Confirmed",
      contactLabel: "Phone only",
      contactTone: "tone-amber",
      phone: "Public phone found",
      website: "Website listed",
    },
  },
  {
    name: "GTA HVAC Pros",
    category: "service contractor",
    location: "Scarborough, ON, Canada",
    score: 92,
    status: "Verified",
    statusTone: "green",
    fit: "Strong fit",
    body: "The business has 13 public reviews.",
    missing: "",
    detail: {
      address: "85 Ellesmere Rd, Scarborough, ON",
      contact: "Public business profile",
      email: "Public email found",
      emailStatus: "Email · available",
      why: "The business has 13 public reviews, below this audience's threshold of 15.",
      opportunityLabel: "Confirmed",
      contactLabel: "Reachable",
      contactTone: "",
      phone: "Public phone found",
      website: "Website listed",
    },
  },
  {
    name: "Highland HVAC Services",
    category: "service contractor",
    location: "Etobicoke, ON, Canada",
    score: 90,
    status: "Verified",
    statusTone: "green",
    fit: "Strong fit",
    body: "The business has 13 public reviews.",
    missing: "",
    detail: {
      address: "69 Lemonwood Dr, Etobicoke, ON",
      contact: "Public business profile",
      email: "No email found",
      emailStatus: "Email · unavailable",
      why: "The business has 13 public reviews, below this audience's threshold of 15.",
      opportunityLabel: "Confirmed",
      contactLabel: "Phone only",
      contactTone: "tone-amber",
      phone: "Public phone found",
      website: "Website listed",
    },
  },
  {
    name: "Expert GTA Furnace and Air Condition Inc.",
    category: "local service provider",
    location: "East York, ON, Canada",
    score: 88,
    status: "Verified",
    statusTone: "green",
    fit: "Strong fit",
    body: "The business has 8 public reviews.",
    missing: "",
    detail: {
      address: "39 Dunkirk Rd, East York, ON",
      contact: "Public business profile",
      email: "Public email found",
      emailStatus: "Email · available",
      why: "The business has 8 public reviews, below this audience's threshold of 15.",
      opportunityLabel: "Confirmed",
      contactLabel: "Reachable",
      contactTone: "",
      phone: "Public phone found",
      website: "Website listed",
    },
  },
  {
    name: "North York Comfort Systems",
    category: "local service provider",
    location: "North York, ON, Canada",
    score: 85,
    status: "Verified",
    statusTone: "green",
    fit: "Strong fit",
    body: "The business has 11 public reviews.",
    missing: "",
    detail: {
      address: "212 Finch Ave W, North York, ON",
      contact: "Public business profile",
      email: "No email found",
      emailStatus: "Email · unavailable",
      why: "The business has 11 public reviews, below this audience's threshold of 15.",
      opportunityLabel: "Confirmed",
      contactLabel: "Phone only",
      contactTone: "tone-amber",
      phone: "Public phone found",
      website: "Website listed",
    },
  },
];

const PREVIEW_LEAD_TOTAL = PREVIEW_LEADS.length;
const PREVIEW_VERIFIED_TOTAL = PREVIEW_LEADS.filter((lead) => lead.statusTone === "green").length;
const PREVIEW_QUERY = "Toronto Painters Missing Website";

const PREVIEW_RUNS = [
  { title: "Toronto Roofers - Low Reviews", meta: "12 · 9 verified", count: "", date: "Oct 2", tone: "green" },
  { title: "Toronto Electricians - Low Reviews", meta: "15 · 11 verified", count: "", date: "Sep 30", tone: "green" },
  { title: "Toronto Painters Missing Website", meta: "25 leads", count: "", date: "Oct 3", tone: "green" },
  { title: "Toronto HVAC No Quote Flow", meta: "9 found", count: "researching", date: "Oct 1", tone: "amber" },
  { title: "Toronto HVAC Low Reviews", meta: "5 leads", count: "", date: "Oct 1", tone: "green" },
];

function AnimatedPreview() {
  const [screen, setScreen] = useState<"results" | "builder" | "loading">("results");
  const [visibleLeads, setVisibleLeads] = useState(5);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [cursorIndex, setCursorIndex] = useState(-1);
  const [cursorPressed, setCursorPressed] = useState(false);
  const [newAudienceCursor, setNewAudienceCursor] = useState(false);
  const [newAudiencePressed, setNewAudiencePressed] = useState(false);
  const [createCursor, setCreateCursor] = useState(false);
  const [createPressed, setCreatePressed] = useState(false);
  const [criteriaStep, setCriteriaStep] = useState(0);
  const [criterionCursor, setCriterionCursor] = useState<"trade" | "customer" | "signal" | null>(null);
  const [criterionPressed, setCriterionPressed] = useState(false);
  const [reviewStage, setReviewStage] = useState(0);
  const [shortlisted, setShortlisted] = useState(false);
  const [cycle, setCycle] = useState(0);

  useEffect(() => {
    if (prefersReducedMotion()) {
      setScreen("results");
      setVisibleLeads(5);
      setSelectedIndex(0);
      setCriteriaStep(3);
      setReviewStage(3);
      setShortlisted(true);
      return;
    }

    const timers: number[] = [];
    const at = (ms: number, run: () => void) => timers.push(window.setTimeout(run, ms));
    const compactLayout = window.matchMedia("(max-width: 680px)").matches;

    setScreen("results");
    setVisibleLeads(compactLayout ? 0 : 5);
    setSelectedIndex(-1);
    setCursorIndex(-1);
    setCursorPressed(false);
    setNewAudienceCursor(false);
    setNewAudiencePressed(false);
    setCreateCursor(false);
    setCreatePressed(false);
    setCriteriaStep(0);
    setCriterionCursor(null);
    setCriterionPressed(false);
    setReviewStage(0);
    setShortlisted(false);

    if (compactLayout) {
      setVisibleLeads(5);
      at(450, () => setNewAudienceCursor(true));
      at(850, () => setNewAudiencePressed(true));
      at(1080, () => {
        setNewAudienceCursor(false);
        setNewAudiencePressed(false);
        setScreen("builder");
      });
      at(1450, () => setCriterionCursor("trade"));
      at(1750, () => setCriterionPressed(true));
      at(1970, () => {
        setCriteriaStep(1);
        setCriterionPressed(false);
        setCriterionCursor("signal");
      });
      at(2270, () => setCriterionPressed(true));
      at(2490, () => {
        setCriteriaStep(3);
        setCriterionPressed(false);
        setCriterionCursor(null);
      });
      at(2780, () => setCreateCursor(true));
      at(3100, () => setCreatePressed(true));
      at(3330, () => {
        setCreateCursor(false);
        setCreatePressed(false);
        setVisibleLeads(0);
        setScreen("loading");
      });
      at(4700, () => setScreen("results"));
      for (let index = 0; index < 5; index += 1) {
        at(4900 + index * 220, () => setVisibleLeads(index + 1));
      }
      at(6000, () => setCursorIndex(0));
      at(6350, () => setCursorPressed(true));
      at(6570, () => {
        setCursorPressed(false);
        setCursorIndex(-1);
        setSelectedIndex(0);
      });
      at(7100, () => setShortlisted(true));
      at(8500, () => setCycle((current) => current + 1));
      return () => timers.forEach(clearTimeout);
    }

    at(550, () => setNewAudienceCursor(true));
    at(1000, () => setNewAudiencePressed(true));
    at(1250, () => {
      setNewAudienceCursor(false);
      setNewAudiencePressed(false);
      setScreen("builder");
    });
    at(1650, () => setCriterionCursor("trade"));
    at(2000, () => setCriterionPressed(true));
    at(2220, () => {
      setCriteriaStep(1);
      setCriterionPressed(false);
      setCriterionCursor("customer");
    });
    at(2600, () => setCriterionPressed(true));
    at(2820, () => {
      setCriteriaStep(2);
      setCriterionPressed(false);
      setCriterionCursor("signal");
    });
    at(3200, () => setCriterionPressed(true));
    at(3420, () => {
      setCriteriaStep(3);
      setCriterionPressed(false);
      setCriterionCursor(null);
    });
    at(3750, () => setCreateCursor(true));
    at(4150, () => setCreatePressed(true));
    at(4400, () => {
      setCreateCursor(false);
      setCreatePressed(false);
      setScreen("loading");
    });
    at(6250, () => {
      setVisibleLeads(0);
      setScreen("results");
    });
    for (let index = 0; index < 5; index += 1) {
      at(6500 + index * 220, () => setVisibleLeads(index + 1));
    }
    at(7800, () => setCursorIndex(0));
    at(8200, () => setCursorPressed(true));
    at(8420, () => {
      setCursorPressed(false);
      setCursorIndex(-1);
      setSelectedIndex(0);
    });
    at(8850, () => setReviewStage(1));
    at(9400, () => setReviewStage(2));
    at(10050, () => setReviewStage(3));
    at(10850, () => setShortlisted(true));
    at(13400, () => setCycle((current) => current + 1));

    return () => timers.forEach(clearTimeout);
  }, [cycle]);

  const heroStep =
    screen === "loading" || (screen === "builder" && criteriaStep >= 3) || createCursor || createPressed
      ? 2
      : screen === "builder"
        ? (criteriaStep >= 1 ? 1 : 0)
        : criteriaStep >= 3
          ? 3
          : 0;

  return (
    <>
      <div className="landing-hero-chips" aria-label="Audience creation steps">
        <HeroStepChip active={heroStep === 0} number="01" label="New audience" />
        <span className="landing-hero-chip-arrow" aria-hidden="true">→</span>
        <HeroStepChip active={heroStep === 1} number="02" label="Set profile" />
        <span className="landing-hero-chip-arrow" aria-hidden="true">→</span>
        <HeroStepChip active={heroStep === 2} number="03" label="Create" />
        <span className="landing-hero-chip-arrow" aria-hidden="true">→</span>
        <HeroStepChip active={heroStep === 3} number="04" label="Leads" />
      </div>
      <div className={`landing-preview preview-app landing-workspace-preview is-${screen}`} aria-label="ScoutLead audience workspace preview">
      <PreviewRail activeManage="" activeRun="Toronto HVAC Low Reviews" shortlistedCount={shortlisted ? 1 : 0} />
      <div className="preview-main-panel">
        <div className="preview-audience-bar">
          <button className="preview-mobile-menu" type="button" tabIndex={-1} aria-label="Open preview navigation">
            <Menu size={14} />
          </button>
          <div>
            <span>Audiences</span>
            <em>/</em>
            <strong>{screen === "builder" ? "New audience" : "Toronto HVAC Low Reviews"}</strong>
          </div>
          <button className={newAudiencePressed ? "is-preview-pressed" : ""} type="button" tabIndex={-1}>
            <Plus size={13} /> New audience
            <PreviewCursor
              className="preview-cursor-actor--new-audience"
              pressed={newAudiencePressed}
              visible={screen === "results" && newAudienceCursor}
            />
          </button>
        </div>
        <div className="preview-stage">
          <div className="preview-scene-stack landing-workspace-scenes">
            {screen === "builder" ? (
              <div className="preview-scene">
                <AudienceBuilderPreview
                  compact
                  createCursor={createCursor}
                  createPressed={createPressed}
                  criteriaStep={criteriaStep}
                  criterionCursor={criterionCursor}
                  criterionPressed={criterionPressed}
                />
              </div>
            ) : screen === "loading" ? (
              <div className="preview-scene">
                <PreviewMatchLoading />
              </div>
            ) : (
              <div className="preview-scene">
              <PreviewResults
                clickedIndex={selectedIndex}
                compactDetail
                cursorIndex={cursorIndex}
                cursorPressed={cursorPressed}
                detailIndex={selectedIndex < 0 ? 0 : selectedIndex}
                drawerVisible={selectedIndex >= 0}
                leadLimit={5}
                reviewStage={reviewStage}
                shortlisted={shortlisted}
                showDrawer={selectedIndex >= 0}
                visibleCount={visibleLeads}
                workspaceMode
              />
              </div>
            )}
          </div>
        </div>
      </div>
      </div>
    </>
  );
}

function HeroStepChip({ active, label, number }: { active: boolean; label: string; number: string }) {
  return (
    <span className={`landing-hero-chip${active ? " is-active" : ""}`}>
      <b>{number}</b> {label}
    </span>
  );
}

function AudienceBuilderPreview({
  compact = false,
  createCursor = false,
  createPressed = false,
  criteriaStep = 3,
  criterionCursor = null,
  criterionPressed = false,
}: {
  compact?: boolean;
  createCursor?: boolean;
  createPressed?: boolean;
  criteriaStep?: number;
  criterionCursor?: "trade" | "customer" | "signal" | null;
  criterionPressed?: boolean;
}) {
  return (
    <div className={`audience-builder-preview${compact ? " is-compact" : ""}`} aria-label="Audience profile example">
      <div className="audience-builder-head">
        <div>
          <span>Local Service Conversion Growth</span>
          <strong>New audience</strong>
          <p>Create a separate lead stream under this product.</p>
        </div>
        <span className={`audience-builder-status${criteriaStep >= 3 ? "" : " is-incomplete"}`}>
          <i /> {criteriaStep >= 3 ? "Ready to create" : "Select required criteria"}
        </span>
      </div>

      <div className="audience-builder-row audience-builder-row-trade">
        <div className="audience-builder-label">
          <strong>Business type</strong>
          <span>Choose one or more.</span>
        </div>
        <div className="audience-builder-options audience-builder-trades">
          <button type="button" tabIndex={-1}>Electricians</button>
          <button type="button" tabIndex={-1}>Painters</button>
          <button className={criteriaStep >= 1 ? "is-selected" : ""} type="button" tabIndex={-1}>
            {criteriaStep >= 1 ? <CheckCircle2 size={13} /> : null} HVAC
            <PreviewCursor
              className="preview-cursor-actor--criterion"
              pressed={criterionCursor === "trade" && criterionPressed}
              visible={criterionCursor === "trade"}
            />
          </button>
          <button type="button" tabIndex={-1}>Roofers</button>
        </div>
      </div>

      <div className="audience-builder-row audience-builder-row-customer">
        <div className="audience-builder-label">
          <strong>Customer kind</strong>
          <span>Who these businesses serve.</span>
        </div>
        <div className="audience-builder-segmented" aria-label={criteriaStep >= 2 ? "Residential selected" : "Customer kind not selected"}>
          <span className={criteriaStep >= 2 ? "is-selected" : ""}>
            Residential
            <PreviewCursor
              className="preview-cursor-actor--criterion"
              pressed={criterionCursor === "customer" && criterionPressed}
              visible={criterionCursor === "customer"}
            />
          </span>
          <span>Commercial</span>
        </div>
      </div>

      <div className="audience-builder-row audience-builder-row-search">
        <div className="audience-builder-label">
          <strong>Search</strong>
          <span>Market and delivery size.</span>
        </div>
        <div className="audience-builder-market">
          <span><MapPin size={13} /> Toronto</span>
          <span>25 km <ChevronDown size={12} /></span>
          <span>10 leads <ChevronDown size={12} /></span>
        </div>
      </div>

      <div className="audience-builder-row audience-builder-row-signals">
        <div className="audience-builder-label">
          <strong>Opportunity signals</strong>
          <span>Stored facts that qualify a lead.</span>
        </div>
        <div className="audience-builder-checks">
          <span><i /> Missing or unavailable website</span>
          <span><i /> No quote or booking flow</span>
          <span><i /> No contact form</span>
          <span className={criteriaStep >= 3 ? "is-selected" : ""}>
            <i>{criteriaStep >= 3 ? <CheckCircle2 size={12} /> : null}</i> Reviews under 15
            <PreviewCursor
              className="preview-cursor-actor--criterion"
              pressed={criterionCursor === "signal" && criterionPressed}
              visible={criterionCursor === "signal"}
            />
          </span>
        </div>
      </div>

      <div className="audience-builder-footer">
        <span>Only businesses with a confirmed selected signal are delivered.</span>
        <button className={createPressed ? "is-preview-pressed" : ""} disabled={criteriaStep < 3} type="button" tabIndex={-1}>
          Create audience <ArrowRight size={13} />
          <PreviewCursor
            className="preview-cursor-actor--create-audience"
            pressed={createPressed}
            visible={createCursor}
          />
        </button>
      </div>
    </div>
  );
}

function PreviewMatchLoading() {
  return (
    <div className="preview-match-loading" aria-label="Matching businesses">
      <div className="preview-match-loading-head">
        <div><strong>Leads</strong><span>0</span></div>
        <label><Search size={13} /><span>Search leads</span></label>
      </div>
      <div className="preview-match-loading-body">
        <span className="preview-match-spinner"><LoaderCircle size={22} /></span>
        <strong>Matching businesses to this audience</strong>
        <p>Checking stored trade, location, review, and exclusion facts.</p>
        <div className="preview-match-progress" aria-hidden="true"><i /></div>
      </div>
    </div>
  );
}

type SignalObservation = {
  date: string;
  detail: string;
  source: string;
  state: "retired" | "retained" | "current";
  title: string;
};

const SIGNAL_OBSERVATIONS: SignalObservation[] = [
  {
    date: "Sep 08",
    detail: "The source profile did not include a business website.",
    source: "Business listing",
    state: "retired",
    title: "Website not listed",
  },
  {
    date: "Sep 27",
    detail: "An owned domain was discovered and attached to the profile.",
    source: "Website check",
    state: "retained",
    title: "Website found",
  },
  {
    date: "Oct 09",
    detail: "The live website has contact details, but no quote or booking path.",
    source: "Conversion check",
    state: "current",
    title: "No quote flow confirmed",
  },
];

function LeadReviewSection() {
  const [sectionRef, sectionActive] = useRevealOnScroll<HTMLElement>("0px");
  const [revealed, setRevealed] = useState(0);
  const rowCount = SIGNAL_OBSERVATIONS.length;

  useEffect(() => {
    if (!sectionActive) {
      setRevealed(0);
      return;
    }
    if (prefersReducedMotion()) {
      setRevealed(rowCount + 1);
      return;
    }

    setRevealed(0);
    const timers: number[] = [];
    const at = (ms: number, run: () => void) => timers.push(window.setTimeout(run, ms));
    SIGNAL_OBSERVATIONS.forEach((_, index) => {
      at(260 + index * 420, () => setRevealed(index + 1));
    });
    at(260 + rowCount * 420 + 180, () => setRevealed(rowCount + 1));

    return () => timers.forEach(clearTimeout);
  }, [sectionActive, rowCount]);

  return (
    <section
      className="landing-section landing-proof-section"
      id="lead-proof"
      aria-label="How ScoutLead keeps business opportunity signals current"
      ref={sectionRef}
    >
      <div className="landing-freshness-inner">
        <div className="landing-section-heading landing-freshness-heading">
          <p className="landing-eyebrow">Evidence that ages honestly</p>
          <h2>A lead should not outlive its evidence</h2>
          <p className="landing-lede">
            Static lists go stale as businesses change. ScoutLead timestamps each observation, retires superseded
            facts, and keeps the opportunity aligned with what is true now.
          </p>
        </div>

        <div className="landing-freshness-panel">
          <div className="landing-freshness-panel-head">
            <div>
              <span className="landing-freshness-live" aria-hidden="true"><i /></span>
              <span><b>Eastline Heating</b> · Toronto HVAC</span>
            </div>
            <span>Profile history</span>
          </div>

          <div className="landing-freshness-body">
            <div className="landing-observation-ledger">
              <div className="landing-observation-ledger-head">
                <span>Evidence timeline</span>
                <em>{Math.min(revealed, rowCount)} / {rowCount} reconciled</em>
              </div>
              <div className="landing-observation-list">
                {SIGNAL_OBSERVATIONS.map((observation, index) => (
                  <SignalObservationRow
                    index={index}
                    key={`${observation.date}-${observation.title}`}
                    observation={observation}
                    revealed={revealed > index}
                  />
                ))}
              </div>
            </div>

            <div className={`landing-current-profile${revealed > rowCount ? " is-ready" : ""}`}>
              <div className="landing-current-profile-top">
                <span>Current opportunity</span>
                <em>{revealed > rowCount ? "Ready" : "Reconciling"}</em>
              </div>
              <div className="landing-current-profile-signal">
                <span><Target size={16} /></span>
                <div>
                  <small>Confirmed signal</small>
                  <strong>No quote or booking flow</strong>
                </div>
              </div>
              <dl className="landing-current-profile-facts">
                <div><dt>Website</dt><dd>Present</dd></div>
                <div><dt>Contact details</dt><dd>Found</dd></div>
                <div><dt>Last checked</dt><dd>9 min ago</dd></div>
              </dl>
              <div className="landing-freshness-meter">
                <span><i /></span>
                <div><strong>Current evidence</strong><em>Recheck due in 30 days</em></div>
              </div>
            </div>
          </div>

          <div className={`landing-freshness-foot${revealed > rowCount ? " is-visible" : ""}`}>
            <ShieldCheck size={15} />
            The outreach angle changed with the evidence. The old missing-website claim was not reused.
          </div>
        </div>
      </div>
    </section>
  );
}

function SignalObservationRow({
  index,
  observation,
  revealed,
}: {
  index: number;
  observation: SignalObservation;
  revealed: boolean;
}) {
  const icon = index === 0 ? <MapPin size={15} /> : index === 1 ? <Globe size={15} /> : <Target size={15} />;
  const stateLabel = observation.state === "retired" ? "Superseded" : observation.state === "retained" ? "Retained" : "Current";

  return (
    <div className={`landing-observation-row is-${observation.state}${revealed ? " is-in" : ""}`}>
      <span className="landing-observation-date">{observation.date}</span>
      <span className="landing-observation-icon">{icon}</span>
      <span className="landing-observation-copy">
        <small>{observation.source}</small>
        <strong>{observation.title}</strong>
        <em>{observation.detail}</em>
      </span>
      <span className="landing-observation-state">
        {observation.state === "current" ? <CheckCircle2 size={13} /> : null}
        {stateLabel}
      </span>
    </div>
  );
}

function OutreachSection() {
  const [sectionRef, sectionActive] = useRevealOnScroll<HTMLElement>("0px");
  const [outreachStage, setOutreachStage] = useState(0);

  useEffect(() => {
    if (!sectionActive) {
      setOutreachStage(0);
      return;
    }
    if (prefersReducedMotion()) {
      setOutreachStage(3);
      return;
    }

    const interval = window.setInterval(() => {
      setOutreachStage((currentStage) => (currentStage + 1) % 4);
    }, 1550);

    return () => window.clearInterval(interval);
  }, [sectionActive]);

  return (
    <section
      className="landing-section landing-draft-section"
      id="outreach"
      aria-label="Outreach draft, approval, and send"
      ref={sectionRef}
    >
      <div className="landing-draft-inner">
        <div className="landing-workflow-layout landing-workflow-layout-reverse">
          <DraftSendPreview stage={outreachStage} />
          <div>
            <div className="landing-section-heading">
              <p className="landing-eyebrow">Prepare and send</p>
              <h2>Outreach stays tied to public evidence</h2>
              <p className="landing-lede">
                Drafts reference the public signal ScoutLead found, such as a missing booking link or a thin review
                profile. Nothing sends until you approve it, and replies return to your own Gmail.
              </p>
              <div className="landing-inline-checks">
                <span className={outreachStage >= 0 ? "is-active" : ""}><CheckCircle2 size={14} /> Signal-grounded personalization</span>
                <span className={outreachStage >= 2 ? "is-active" : ""}><CheckCircle2 size={14} /> Human approval before sending</span>
                <span className={outreachStage >= 3 ? "is-active" : ""}><CheckCircle2 size={14} /> Account-wide suppression</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function DraftSendPreview({ stage }: { stage: number }) {
  const stageLabels = ["Evidence", "Draft", "Approval", "Sent"];

  return (
    <div className="draft-preview" aria-label="Evidence-grounded outreach draft">
      <div className={`draft-card draft-stage-${stage}`}>
        <div className="draft-card-head">
          <Mail size={13} />
          <span>New message</span>
          <em className={`draft-badge${stage === 2 ? " is-approved" : ""}${stage === 3 ? " is-sent" : ""}`}>
            {stageLabels[stage]}
          </em>
        </div>
        <div className={`draft-sequence stage-${stage}`} aria-label="Evidence to approved outreach">
          <DraftSequenceStep active={stage === 0} completed={stage > 0} icon={<Target size={13} />} label="Evidence" />
          <DraftSequenceStep active={stage === 1} completed={stage > 1} icon={<Mail size={13} />} label="Draft" />
          <DraftSequenceStep active={stage === 2} completed={stage > 2} icon={<UserCheck size={13} />} label="Approve" />
          <DraftSequenceStep active={stage === 3} completed={false} icon={<Send size={13} />} label="Gmail" />
        </div>
        <div className={`draft-signal-context${stage === 0 ? " is-current" : ""}`}>
          <Target size={14} />
          <div><span>Personalized from</span><strong>4 public reviews · Google Places</strong></div>
        </div>
        <div className={`draft-compose${stage >= 1 ? " is-visible" : ""}`}>
        <div className="draft-field">
          <span>To</span>
          <strong>ONCALL Heating and Cooling</strong>
        </div>
        <div className="draft-field">
          <span>Subject</span>
          <strong>A quick idea for strengthening ONCALL's local presence</strong>
        </div>
        <div className="draft-body">
          Hi there,
          <br /><br />
          I came across ONCALL while reviewing Toronto HVAC providers and noticed the business has only four public
          reviews. We help local service teams improve the customer journey around reviews and quote requests.
        </div>
        </div>
        <div className={`draft-approval-note${stage >= 2 ? " is-visible" : ""}`}>
          <ShieldCheck size={13} /> {stage === 3 ? "Approved by you before sending." : "Nothing sends until you approve."}
        </div>
        <div className={`draft-actions${stage >= 2 ? " is-visible" : ""}`}>
          <button type="button" tabIndex={-1} className="draft-approve">Edit draft</button>
          <button type="button" tabIndex={-1} className={`draft-send${stage === 3 ? " is-done" : ""}`}>
            {stage === 3 ? <><CheckCircle2 size={13} /> Sent from Gmail</> : <>Approve and send <ArrowRight size={13} /></>}
          </button>
        </div>
      </div>
    </div>
  );
}

function DraftSequenceStep({
  active,
  completed,
  icon,
  label,
}: {
  active: boolean;
  completed: boolean;
  icon: ReactNode;
  label: string;
}) {
  return (
    <span className={`${active ? "is-active" : ""}${completed ? " is-complete" : ""}`.trim()}>
      <i>{completed ? <CheckCircle2 size={13} /> : icon}</i>
      <em>{label}</em>
    </span>
  );
}

type PreviewIntegrationTarget = "gmail" | "resend" | "sheets" | "webhook";

const INITIAL_PREVIEW_INTEGRATIONS: Record<PreviewIntegrationTarget, boolean> = {
  gmail: false,
  resend: false,
  sheets: false,
  webhook: false,
};

function PreviewRail({
  activeManage,
  activeRun,
  shortlistedCount = 0,
}: {
  activeManage: string;
  activeRun: string;
  shortlistedCount?: number;
}) {
  return (
    <aside className="preview-rail" aria-label="Preview audiences">
      <div className="preview-rail-brand">
        <span>S</span>
        <div>
          <strong>ScoutLead</strong>
          <em>Discovery Console</em>
        </div>
      </div>
      <div className="preview-product-summary">
        <Package size={13} />
        <div>
          <span>Product</span>
          <strong>Local Service Conversion Growth</strong>
        </div>
        <ChevronDown size={12} />
      </div>
      <div className="preview-workflow-nav">
        <PreviewWorkflowRow active icon={<ListChecks size={14} />} label="Leads" count={String(PREVIEW_LEAD_TOTAL)} />
        <PreviewWorkflowRow
          count={String(shortlistedCount)}
          countUpdated={shortlistedCount > 0}
          icon={<Star size={14} />}
          label="Shortlisted"
        />
        <PreviewWorkflowRow icon={<Send size={14} />} label="Contacted" count="0" />
        <PreviewWorkflowRow icon={<CircleX size={14} />} label="Dismissed" count="0" />
      </div>
      <div className="preview-rail-heading">
        <span>Audiences</span>
        <button type="button" tabIndex={-1} aria-label="Add preview audience">
          <Plus size={13} />
        </button>
      </div>
      <div className="preview-run-list">
        {PREVIEW_RUNS.map((run) => (
          <div
            aria-label={run.title}
            className={`preview-run${run.title === activeRun ? " is-active" : ""}`}
            key={run.title}
            title={run.title}
          >
            <UsersRound size={13} />
            <strong>{run.title}</strong>
          </div>
        ))}
      </div>
      <div className="preview-view-all">View all (6)</div>
      <div className="preview-manage">
        <span>Manage</span>
        <PreviewManageRow icon={<Settings size={13} />} active={activeManage === "Product settings"} label="Product settings" />
        <PreviewManageRow icon={<Plug size={13} />} active={activeManage === "Integrations"} label="Integrations" />
        <PreviewManageRow icon={<Download size={13} />} active={false} label="Export all contacts" />
      </div>
      <div className="preview-account-row">
        <span />
        <strong>Account</strong>
      </div>
    </aside>
  );
}

function PreviewWorkflowRow({
  active = false,
  count,
  countUpdated = false,
  icon,
  label,
}: {
  active?: boolean;
  count: string;
  countUpdated?: boolean;
  icon: ReactNode;
  label: string;
}) {
  return (
    <div className={`preview-workflow-row${active ? " is-active" : ""}`}>
      {icon}
      <strong>{label}</strong>
      <em className={countUpdated ? "is-updated" : ""}>{count}</em>
    </div>
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
      <h3>Define your next audience</h3>
      <p>Choose the business type, city, and signals. ScoutLead builds the batch and scores each business against your offer.</p>
      <div className="preview-composer">
        <span>
          {PREVIEW_QUERY.slice(0, typedLength)}
          <span className="preview-cursor" aria-hidden="true" />
        </span>
        <div className="preview-composer-send">
          <button type="button" tabIndex={-1} aria-label="Create preview audience">
            <ArrowRight size={14} />
          </button>
          <PreviewCursor className="preview-cursor-actor--composer" pressed={cursorPressed} visible={cursorVisible} />
        </div>
      </div>
      <span className="preview-section-label">Or start from a signal</span>
      <div className="preview-template-grid">
        <PreviewTemplate title="Missing website" tag="Signal">
          painting businesses in Toronto with no website listed and a public phone number
        </PreviewTemplate>
        <PreviewTemplate title="Low reviews" tag="Signal">
          HVAC businesses in Toronto with fewer than 15 public reviews
        </PreviewTemplate>
        <PreviewTemplate title="No quote flow" tag="Signal">
          roofers in Toronto with no quote or booking flow on their site
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
  detailIndex,
  compactDetail = false,
  leadStartIndex = 0,
  leadLimit,
  mobileDetailOnly = false,
  proofReview = false,
  showDrawer = false,
  visibleCount = PREVIEW_LEAD_TOTAL,
  drawerVisible = true,
  clickedIndex = -1,
  cursorIndex = -1,
  cursorPressed = false,
  reviewStage = 0,
  shortlisted = false,
  workspaceMode = false,
}: {
  detailIndex?: number;
  compactDetail?: boolean;
  leadStartIndex?: number;
  leadLimit?: number;
  mobileDetailOnly?: boolean;
  proofReview?: boolean;
  showDrawer?: boolean;
  visibleCount?: number;
  drawerVisible?: boolean;
  clickedIndex?: number;
  cursorIndex?: number;
  cursorPressed?: boolean;
  reviewStage?: number;
  shortlisted?: boolean;
  workspaceMode?: boolean;
}) {
  const selectedLead = PREVIEW_LEADS[Math.max(0, detailIndex ?? clickedIndex)] ?? PREVIEW_LEADS[0];
  const startIndex = Math.max(0, Math.min(leadStartIndex, PREVIEW_LEADS.length - 1));
  const renderedLeads =
    typeof leadLimit === "number"
      ? PREVIEW_LEADS.slice(startIndex, startIndex + leadLimit)
      : PREVIEW_LEADS.slice(startIndex);
  const reviewedCount = showDrawer && clickedIndex >= 0 && reviewStage >= 3 ? 1 : 0;
  const needsReviewCount = Math.max(0, PREVIEW_LEAD_TOTAL - reviewedCount);

  return (
    <section
      className={`preview-results-screen${showDrawer ? " has-detail" : ""}${showDrawer && drawerVisible ? " is-open" : ""}${proofReview ? " is-proof-review" : ""}${mobileDetailOnly ? " is-mobile-detail-only" : ""}`}
      aria-label="Preview results"
    >
      {workspaceMode ? (
        <div className="preview-workspace-controls">
          <div><strong>Leads</strong><span>{PREVIEW_LEAD_TOTAL}</span></div>
          <label><Search size={13} /><span>Search leads</span></label>
        </div>
      ) : (
        <>
          <div className="preview-results-meta">
            {PREVIEW_LEAD_TOTAL} leads · {PREVIEW_LEAD_TOTAL} reachable · {PREVIEW_VERIFIED_TOTAL} verified ·{" "}
            {PREVIEW_LEAD_TOTAL} strong fit
          </div>
          <div className="preview-results-controls">
            <div className="preview-tabs">
              <strong>All <span>{PREVIEW_LEAD_TOTAL}</span></strong>
              <span>Shortlisted <em>{reviewedCount}</em></span>
              <span>Needs review <em>{needsReviewCount}</em></span>
            </div>
            <div className="preview-sort-actions">
              <button type="button" tabIndex={-1}>Filter <strong>All</strong></button>
              <button type="button" tabIndex={-1}>Sort <strong>Contact</strong></button>
              <button type="button" tabIndex={-1} aria-label="More preview actions">
                <MoreVertical size={14} />
              </button>
            </div>
          </div>
        </>
      )}
      <div className="preview-results-body">
        <div className="preview-lead-list">
          {renderedLeads.map((lead, idx) => {
            const leadIndex = startIndex + idx;
            return (
              <PreviewLeadCard
                lead={lead}
                key={lead.name}
                visible={idx < visibleCount}
                clicked={leadIndex === clickedIndex}
                selected={leadIndex === clickedIndex}
                showCursor={leadIndex === cursorIndex}
                cursorPressed={leadIndex === cursorIndex && cursorPressed}
                shortlisted={shortlisted && leadIndex === clickedIndex}
              />
            );
          })}
        </div>
        {showDrawer ? (
          <PreviewDetailDrawer
            compactEvidence={compactDetail}
            lead={selectedLead}
            reviewStage={reviewStage}
            shortlisted={shortlisted}
            visible={drawerVisible}
          />
        ) : null}
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
  shortlisted = false,
  visible = true,
}: {
  clicked?: boolean;
  cursorPressed?: boolean;
  lead: (typeof PREVIEW_LEADS)[number];
  selected?: boolean;
  showCursor?: boolean;
  shortlisted?: boolean;
  visible?: boolean;
}) {
  return (
    <article
      aria-hidden={!visible}
      className={`preview-lead-card${visible ? "" : " is-hidden"}${clicked ? " is-clicked" : ""}${selected ? " is-selected" : ""}${shortlisted ? " is-shortlisted" : ""}`}
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
      <div className="preview-lead-actions" aria-hidden="true">
        <time>6h</time>
        <Star fill={shortlisted ? "currentColor" : "none"} size={13} />
      </div>
    </article>
  );
}

function PreviewDetailDrawer({
  compactEvidence = false,
  lead,
  reviewStage = 0,
  shortlisted = false,
  visible = true,
}: {
  compactEvidence?: boolean;
  lead: (typeof PREVIEW_LEADS)[number];
  reviewStage?: number;
  shortlisted?: boolean;
  visible?: boolean;
}) {
  return (
    <aside
      aria-hidden={!visible}
      aria-label="Preview lead drawer"
      className={`preview-detail-drawer${visible ? "" : " is-hidden"}`}
    >
      <div className={`preview-detail-empty${visible ? " is-hidden" : ""}`} aria-hidden={visible}>
        <PreviewDetailSkeleton />
      </div>
      <div className={`preview-detail-drawer-content${visible ? "" : " is-hidden"}`} key={lead.name}>
        <PreviewDetailBody
          compactEvidence={compactEvidence}
          lead={lead}
          reviewStage={reviewStage}
          shortlisted={shortlisted}
        />
      </div>
    </aside>
  );
}

function PreviewDetailSkeleton() {
  return (
    <div className="preview-skeleton" aria-hidden="true">
      <div className="preview-skeleton-head">
        <span className="preview-skeleton-badge" />
        <div className="preview-skeleton-head-lines">
          <span className="preview-skeleton-line" style={{ width: "68%" }} />
          <span className="preview-skeleton-line" style={{ width: "42%" }} />
        </div>
      </div>
      <div className="preview-skeleton-chips">
        <span className="preview-skeleton-chip" />
        <span className="preview-skeleton-chip" />
        <span className="preview-skeleton-chip" />
      </div>
      <div className="preview-skeleton-lines">
        <span className="preview-skeleton-line" style={{ width: "100%" }} />
        <span className="preview-skeleton-line" style={{ width: "80%" }} />
      </div>
      <div className="preview-skeleton-grid">
        <span className="preview-skeleton-block" />
        <span className="preview-skeleton-block" />
        <span className="preview-skeleton-block" />
        <span className="preview-skeleton-block" />
      </div>
      <div className="preview-skeleton-footer">
        <span className="preview-skeleton-btn" />
        <span className="preview-skeleton-btn" />
        <span className="preview-skeleton-btn" />
      </div>
    </div>
  );
}

function PreviewDetailBody({
  compactEvidence = false,
  lead,
  reviewStage = 0,
  shortlisted = false,
  showHeader = true,
}: {
  compactEvidence?: boolean;
  lead: (typeof PREVIEW_LEADS)[number];
  reviewStage?: number;
  shortlisted?: boolean;
  showHeader?: boolean;
}) {
  const fitActive = reviewStage >= 1;
  const evidenceActive = reviewStage >= 2;
  const actionReady = reviewStage >= 3;
  const chipClass = (active: boolean, extra = "") => `${extra}${active ? " is-reviewed" : " is-pending"}`.trim();

  return (
    <>
      {showHeader ? (
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
      ) : null}
      <div className="preview-detail-chips">
        <span className={chipClass(fitActive)}>
          <CheckCircle2 size={12} /> Fit · {lead.fit}
        </span>
        <span className={chipClass(evidenceActive)}>
          <Target size={12} /> Opportunity · {lead.detail.opportunityLabel}
        </span>
        <span className={chipClass(evidenceActive, lead.detail.contactTone)}>
          <Mail size={12} /> Contact · {lead.detail.contactLabel}
        </span>
      </div>
      <div className="preview-detail-why">
        <span className="preview-detail-why-label">Why this lead?</span>
        <p className={`preview-detail-summary${fitActive ? " is-reviewed" : " is-pending"}`}>{lead.detail.why}</p>
      </div>
      <dl className="preview-detail-list">
        {compactEvidence ? (
          <>
            <PreviewDetailRow active={fitActive} icon={<MapPin size={14} />} label="Address" value={lead.detail.address} />
            <PreviewDetailRow active={fitActive} icon={<Globe size={14} />} label="Website" value={lead.detail.website} />
            <PreviewDetailRow active={evidenceActive} icon={<Mail size={14} />} label="Email" value={lead.detail.email} />
            <PreviewDetailRow active={evidenceActive} icon={<Phone size={14} />} label="Phone" value={lead.detail.phone} />
          </>
        ) : (
          <>
            <PreviewDetailRow active={fitActive} icon={<MapPin size={14} />} label="Address" value={lead.detail.address} />
            <PreviewDetailRow active={fitActive} icon={<Globe size={14} />} label="Website" value={lead.detail.website} />
            <PreviewDetailRow active={evidenceActive} icon={<UserCheck size={14} />} label="Contact" value={lead.detail.contact} />
            <PreviewDetailRow active={evidenceActive} icon={<Mail size={14} />} label="Email" value={lead.detail.email} />
            <PreviewDetailRow active={evidenceActive} icon={<Phone size={14} />} label="Phone" value={lead.detail.phone} />
          </>
        )}
      </dl>
      <div className={`preview-detail-footer${actionReady ? " is-action-ready" : ""}${shortlisted ? " is-shortlisted" : ""}`}>
        <button type="button" tabIndex={-1}>Dismiss</button>
        <button className={actionReady ? "is-reviewed is-action-ready" : ""} type="button" tabIndex={-1}>
          <Star fill={shortlisted ? "currentColor" : "none"} size={12} />
          {shortlisted ? "Shortlisted" : "Shortlist"}
          <PreviewCursor
            className="preview-cursor-actor--review-action"
            pressed={actionReady && !shortlisted}
            visible={actionReady && !shortlisted}
          />
        </button>
      </div>
    </>
  );
}

function PreviewDetailRow({
  active = true,
  icon,
  label,
  value,
}: {
  active?: boolean;
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className={active ? "is-reviewed" : "is-pending"}>
      {icon}
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function PreviewIntegrations({
  connected = INITIAL_PREVIEW_INTEGRATIONS,
  cursorPressed = false,
  cursorTarget = "",
  revealStep = 3,
}: {
  connected?: Record<PreviewIntegrationTarget, boolean>;
  cursorPressed?: boolean;
  cursorTarget?: PreviewIntegrationTarget | "";
  revealStep?: number;
}) {
  return (
    <section className="preview-integrations-screen" aria-label="Preview integrations">
      <p>
        Connect where approved contacts and outreach go. Nothing sends or exports until you approve a lead.
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
            actionClicked={cursorTarget === "gmail" && cursorPressed}
            actionConnected={connected.gmail}
            connected={connected.gmail}
            showCursor={cursorTarget === "gmail"}
            badge="G"
            gmail
            title="Gmail"
            status={connected.gmail ? "Connected" : "Off"}
            body={
              connected.gmail
                ? "Approved outreach now sends from your connected Gmail account."
                : "Send approved outreach from your connected Gmail account."
            }
            action={connected.gmail ? "Connected" : "Connect"}
          />
          <PreviewIntegrationRow
            actionClicked={cursorTarget === "resend" && cursorPressed}
            actionConnected={connected.resend}
            connected={connected.resend}
            showCursor={cursorTarget === "resend"}
            badge="R"
            dark
            title="Resend"
            status={connected.resend ? "Enabled" : "Disabled"}
            body={
              connected.resend
                ? "Transactional sending is enabled as a verified-domain alternative."
                : "Transactional sending from a verified domain - alternative to Gmail"
            }
            action={connected.resend ? "Enabled" : "Enable"}
          />
        </PreviewIntegrationGroup>
      </div>
      <div aria-hidden={revealStep < 3} className={`preview-reveal${revealStep >= 3 ? "" : " is-hidden"}`}>
        <PreviewIntegrationGroup label="Workflow outputs">
          <PreviewIntegrationRow
            actionClicked={cursorTarget === "sheets" && cursorPressed}
            connected={connected.sheets}
            showCursor={cursorTarget === "sheets"}
            badge="S"
            green
            title="Google Sheets"
            status={connected.sheets ? "On" : undefined}
            body={
              connected.sheets
                ? "Approved contacts sync to the connected sheet after review."
                : "needs Google Sheets permission - connect separately"
            }
            toggle
            toggleOn={connected.sheets}
          />
          <PreviewIntegrationRow
            actionClicked={cursorTarget === "webhook" && cursorPressed}
            actionConnected={connected.webhook}
            connected={connected.webhook}
            showCursor={cursorTarget === "webhook"}
            badge="{}"
            purple
            title="Webhook"
            status={connected.webhook ? "Linked" : undefined}
            body={
              connected.webhook
                ? "Webhook link added for approved contacts and outreach events."
                : "POST approved contacts as JSON - Airtable, Notion, custom, Zapier"
            }
            action={connected.webhook ? "Linked" : "Add link"}
            toggle
            toggleOn={connected.webhook}
          />
          <PreviewIntegrationRow
            badge="H"
            coral
            title="HubSpot"
            status="Later"
            body="Create or update CRM contacts with fit verdict and evidence"
            action="Soon"
          />
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
  actionConnected = false,
  badge,
  body,
  connected = false,
  coral = false,
  dark = false,
  gmail = false,
  green = false,
  purple = false,
  showCursor = false,
  status,
  title,
  toggle = false,
  toggleOn = false,
}: {
  action?: string;
  actionClicked?: boolean;
  actionConnected?: boolean;
  badge: string;
  body: string;
  connected?: boolean;
  coral?: boolean;
  dark?: boolean;
  gmail?: boolean;
  green?: boolean;
  purple?: boolean;
  showCursor?: boolean;
  status?: string;
  title: string;
  toggle?: boolean;
  toggleOn?: boolean;
}) {
  const badgeTone = gmail ? " gmail" : dark ? " dark" : green ? " green" : purple ? " purple" : coral ? " coral" : "";
  return (
    <div className={`preview-integration-row${connected ? " is-connected" : ""}`}>
      <span className={`preview-integration-badge${badgeTone}`}>{badge}</span>
      <div>
        <strong>
          {title} {status ? <em>{status}</em> : null}
        </strong>
        <p>{body}</p>
      </div>
      <div className="preview-integration-actions">
        {action ? (
          <span className="preview-integration-action-wrap">
            <button
              className={`${actionClicked ? "is-clicked" : ""}${actionConnected ? " is-connected" : ""}`.trim()}
              tabIndex={-1}
              type="button"
            >
              {actionConnected ? <CheckCircle2 size={12} /> : null}
              {action}
            </button>
            <PreviewCursor className="preview-cursor-actor--connect" pressed={actionClicked} visible={showCursor} />
          </span>
        ) : null}
        {toggle ? <span className={`preview-toggle${toggleOn ? " is-on" : ""}`} /> : null}
        {!action ? (
          <PreviewCursor className="preview-cursor-actor--connect" pressed={actionClicked} visible={showCursor} />
        ) : null}
      </div>
    </div>
  );
}

const HOW_IT_WORKS_FUNNEL: Array<{ count: number; hit?: boolean; label: string; suffix: string; width: number }> = [
  { count: 1284, label: "business pool", suffix: "", width: 100 },
  { count: 412, label: "trade match", suffix: "HVAC", width: 34 },
  { count: 128, label: "within radius", suffix: "25 km", width: 12 },
  { count: 30, hit: true, label: "signal confirmed", suffix: "reviews under 15", width: 4 },
];

function HowItWorksSection() {
  const [sectionRef, sectionActive] = useRevealOnScroll<HTMLElement>("0px");
  const [stage, setStage] = useState(0);
  const rowCount = HOW_IT_WORKS_FUNNEL.length;

  useEffect(() => {
    if (!sectionActive) {
      setStage(0);
      return;
    }
    if (prefersReducedMotion()) {
      setStage(rowCount + 1);
      return;
    }

    const timers: number[] = [];
    const at = (ms: number, run: () => void) => timers.push(window.setTimeout(run, ms));

    setStage(0);
    HOW_IT_WORKS_FUNNEL.forEach((_, index) => {
      at(index * 500, () => setStage(index + 1));
    });
    at(rowCount * 500 + 200, () => setStage(rowCount + 1));

    return () => timers.forEach(clearTimeout);
  }, [sectionActive, rowCount]);

  return (
    <section className="landing-section landing-story-section" id="how-it-works" aria-label="How ScoutLead narrows a search" ref={sectionRef}>
      <div className="landing-story-inner">
        <div className="landing-section-heading landing-story-heading">
          <div className="landing-story-title">
            <p className="landing-eyebrow">How it works</p>
            <h2>Thousands of businesses in. A handful out — each with a reason.</h2>
          </div>
          <p className="landing-lede">
            ScoutLead keeps the business pool separate, matches your saved criteria against confirmed facts, and
            returns only the businesses with real evidence for the signals you chose.
          </p>
        </div>

        <div className="landing-how-console">
          <div className="landing-how-console-top">
            <i /><i /><i />
            <span className="landing-how-console-cmd">
              scoutlead run <b>--audience "HVAC · Toronto 25km · reviews&lt;15"</b>
            </span>
            <span className="landing-how-console-live">live</span>
          </div>
          <div className="landing-how-console-body">
            {HOW_IT_WORKS_FUNNEL.map((row, index) => (
              <HowItWorksRow key={row.label} {...row} revealed={stage > index} />
            ))}
            <div className="landing-how-console-divider" />
            <div className={`landing-how-console-out${stage > rowCount ? " is-visible" : ""}`}>
              <span className="landing-how-console-big">
                <FunnelCount active={stage > rowCount} to={HOW_IT_WORKS_FUNNEL[rowCount - 1].count} />
              </span>
              <span className="landing-how-console-outtext">leads returned · evidence attached to each</span>
            </div>
            <ul className="landing-how-console-foot">
              <li>Confirmed signals qualify a lead</li>
              <li>Duplicates are suppressed, not reused</li>
              <li>Criteria are never widened to fill a quota</li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function HowItWorksRow({
  count,
  hit = false,
  label,
  revealed,
  suffix,
  width,
}: {
  count: number;
  hit?: boolean;
  label: string;
  revealed: boolean;
  suffix: string;
  width: number;
}) {
  return (
    <div className={`landing-how-row${hit ? " is-hit" : ""}${revealed ? " is-in" : ""}`}>
      <span className="landing-how-row-label">
        {label} {suffix ? <em>· {suffix}</em> : null}
      </span>
      <span className="landing-how-row-bar">
        <b style={{ width: revealed ? `${width}%` : "0%" }} />
      </span>
      <span className="landing-how-row-count">
        <FunnelCount active={revealed} to={count} />
      </span>
    </div>
  );
}

function FunnelCount({ active, to }: { active: boolean; to: number }) {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (!active) {
      setValue(0);
      return;
    }
    if (prefersReducedMotion()) {
      setValue(to);
      return;
    }

    let frame = 0;
    const start = performance.now();
    const duration = 600;
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / duration);
      setValue(Math.round(to * progress));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);

    return () => cancelAnimationFrame(frame);
  }, [active, to]);

  return <>{value.toLocaleString()}</>;
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
  const [ref, active] = useRevealOnScroll<HTMLDivElement>("420px 0px");
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

type MarketRole = {
  count: number;
  findMarket: string;
  findTrade: string;
  icon: ReactNode;
  returnedWith: string;
  role: string;
  sampleEvidence: string;
  sampleName: string;
  sell: string;
  signal: string;
};

const MARKET_ROLES: MarketRole[] = [
  {
    count: 23,
    findMarket: "Toronto · 25 km",
    findTrade: "Painters",
    icon: <Globe size={18} />,
    returnedWith: "Website status + source",
    role: "Web & SEO agencies",
    sampleEvidence: "no website",
    sampleName: "Lakeside Painting",
    sell: "websites",
    signal: "No website listed",
  },
  {
    count: 17,
    findMarket: "Toronto · Residential",
    findTrade: "HVAC",
    icon: <Star size={18} />,
    returnedWith: "Review count + listing",
    role: "Reputation consultants",
    sampleEvidence: "4 reviews",
    sampleName: "ONCALL Heating",
    sell: "review growth",
    signal: "Fewer than 15 reviews",
  },
  {
    count: 11,
    findMarket: "one local market",
    findTrade: "Roofers",
    icon: <Target size={18} />,
    returnedWith: "Stored inspection fact",
    role: "Conversion specialists",
    sampleEvidence: "no booking flow",
    sampleName: "Lismore Roofing",
    sell: "booking flows",
    signal: "No quote or booking flow",
  },
  {
    count: 19,
    findMarket: "Toronto · 25 km",
    findTrade: "Plumbers",
    icon: <ListChecks size={18} />,
    returnedWith: "Form status + website source",
    role: "Lead-gen partners",
    sampleEvidence: "no contact form",
    sampleName: "Highland Plumbing",
    sell: "qualified leads",
    signal: "No contact form",
  },
];

// Keep in sync with the CSS --landing-market-dwell-equivalent animation duration (landing-market-fill, 4.2s).
const MARKET_DWELL_MS = 4200;
const MARKET_START_INDEX = 2;

function MarketSection() {
  const [sectionRef, sectionActive] = useRevealOnScroll<HTMLElement>("0px");
  const [active, setActive] = useState(MARKET_START_INDEX);
  const [revealStage, setRevealStage] = useState(0);

  useEffect(() => {
    if (!sectionActive) {
      setRevealStage(0);
      return;
    }
    if (prefersReducedMotion()) {
      setRevealStage(6);
      return;
    }

    setRevealStage(0);
    const timers: number[] = [];
    const at = (ms: number, run: () => void) => timers.push(window.setTimeout(run, ms));
    at(90, () => setRevealStage(1));
    at(200, () => setRevealStage(2));
    at(310, () => setRevealStage(3));
    at(420, () => setRevealStage(4));
    at(530, () => setRevealStage(5));
    at(750, () => setRevealStage(6));

    return () => timers.forEach(clearTimeout);
  }, [sectionActive, active]);

  useEffect(() => {
    if (!sectionActive || prefersReducedMotion()) return;
    const timer = window.setTimeout(() => {
      setActive((current) => (current + 1) % MARKET_ROLES.length);
    }, MARKET_DWELL_MS);
    return () => window.clearTimeout(timer);
  }, [sectionActive, active]);

  const role = MARKET_ROLES[active];

  return (
    <section className="landing-section landing-market-section" aria-label="Who ScoutLead is for" ref={sectionRef}>
      <div className="landing-market-inner">
        <div className="landing-section-heading landing-market-head">
          <div>
            <p className="landing-eyebrow">Who you can target</p>
            <h2>Turn the opportunity you solve into a monitored audience</h2>
          </div>
          <p className="landing-lede">
            Whatever you sell to local businesses, there's a public gap that flags a prospect. Pick your angle and
            watch the audience it builds.
          </p>
        </div>

        <div className="landing-market-grid">
          <div className="landing-market-rail">
            <span className="landing-market-rail-label">What you sell →</span>
            {MARKET_ROLES.map((item, index) => (
              <MarketPersonaButton
                active={index === active}
                filling={sectionActive && index === active}
                item={item}
                key={item.role}
                onSelect={() => setActive(index)}
              />
            ))}
          </div>

          <div className="landing-market-panel">
            <div className="landing-market-panel-bar">
              <span className="landing-market-panel-dot" aria-hidden="true" />
              <span className="landing-market-panel-label">Audience monitor</span>
              <span className="landing-market-panel-bridge">
                <b>{role.role}</b> → the {role.findTrade.toLowerCase()} they'd monitor
              </span>
              <span className="landing-market-panel-count">
                matched <b><FunnelCount active={revealStage >= 6} to={role.count} /></b>
              </span>
            </div>

            <div className="landing-market-flow">
              <MarketStage label="Who to find" main={role.findTrade} revealed={revealStage >= 1} sub={role.findMarket} />
              <MarketArrow revealed={revealStage >= 2} />
              <MarketStage label="Opportunity signal" main={role.signal} revealed={revealStage >= 3} signal sub="observable, public" />
              <MarketArrow revealed={revealStage >= 4} />
              <MarketStage label="Returned with" main={role.returnedWith} revealed={revealStage >= 5} sub="traceable evidence" />
            </div>

            <div className={`landing-market-sample${revealStage >= 6 ? " is-visible" : ""}`}>
              <span className="landing-market-sample-k">e.g.</span>
              <span className="landing-market-chip">
                <span className="landing-market-chip-dot" aria-hidden="true" />
                <span className="landing-market-chip-name">{role.sampleName}</span>
                <span className="landing-market-chip-evidence">{role.sampleEvidence}</span>
              </span>
              <span className="landing-market-sample-k landing-market-sample-more">+ {role.count - 1} more</span>
            </div>

            <div className="landing-market-foot">
              <CheckCircle2 aria-hidden="true" size={15} />
              <span>
                Only businesses with confirmed evidence for "{role.signal}" are returned — unknowns stay unknown.
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function MarketPersonaButton({
  active,
  filling,
  item,
  onSelect,
}: {
  active: boolean;
  filling: boolean;
  item: MarketRole;
  onSelect: () => void;
}) {
  return (
    <button className={`landing-market-persona${active ? " is-on" : ""}`} type="button" onClick={onSelect}>
      <span className="landing-market-persona-icon">{item.icon}</span>
      <span className="landing-market-persona-copy">
        <span className="landing-market-persona-title">{item.role}</span>
        <span className="landing-market-persona-sub">you sell {item.sell}</span>
      </span>
      <span className="landing-market-persona-nub" aria-hidden="true" />
      <span className={`landing-market-persona-prog${filling ? " is-filling" : ""}`} aria-hidden="true" />
    </button>
  );
}

function MarketStage({
  label,
  main,
  revealed,
  signal = false,
  sub,
}: {
  label: string;
  main: string;
  revealed: boolean;
  signal?: boolean;
  sub: string;
}) {
  return (
    <div className={`landing-market-stage${revealed ? " is-in" : ""}`}>
      <span className="landing-market-stage-cap">{label}</span>
      <div className={`landing-market-box${signal ? " is-signal" : ""}`}>
        <div className="landing-market-box-main">{main}</div>
        <div className="landing-market-box-sub">{sub}</div>
      </div>
    </div>
  );
}

function MarketArrow({ revealed }: { revealed: boolean }) {
  return (
    <div className="landing-market-arrow" aria-hidden="true">
      <span className={revealed ? "is-in" : ""}>→</span>
    </div>
  );
}

function DataProvenanceSection() {
  const [sectionRef, sectionActive] = useRevealOnScroll<HTMLElement>("0px");
  const [traceStage, setTraceStage] = useState(-1);
  const traceMessages = [
    "Business listing contributed identity, trade, and location",
    "Business website contributed contact and conversion signals",
    "Public records contributed status and classification",
    "Reviewed corrections resolved conflicting observations",
    "Identity and facts reconciled across every input",
    "One evidence-backed business profile assembled",
    "Audience criteria evaluated against the combined profile",
    "Qualified lead returned with evidence and no repeat delivery",
  ];

  useEffect(() => {
    if (!sectionActive) {
      setTraceStage(-1);
      return;
    }
    if (prefersReducedMotion()) {
      setTraceStage(7);
      return;
    }

    setTraceStage(0);
    const interval = window.setInterval(() => {
      setTraceStage((currentStage) => (Math.max(currentStage, 0) + 1) % traceMessages.length);
    }, 1050);

    return () => window.clearInterval(interval);
  }, [sectionActive, traceMessages.length]);

  return (
    <section className="landing-section landing-data-section" id="data-provenance" aria-label="Business data sourcing and evidence processing" ref={sectionRef}>
      <div className="landing-data-inner">
        <div className="landing-section-heading landing-data-heading">
          <div>
            <p className="landing-eyebrow">Data sourcing and evidence</p>
            <h2>Build a fuller business picture from multiple signals</h2>
          </div>
          <p className="landing-lede">
            ScoutLead combines complementary public observations into one business profile, reconciles conflicts, and
            keeps unknowns visible before evaluating your audience criteria.
          </p>
        </div>

        <div className="landing-infra-simulation" aria-label="Business evidence infrastructure simulation">
          <div className="landing-infra-toolbar">
            <span><i /> Profile assembly</span>
            <strong key={traceStage}>{traceStage >= 0 ? traceMessages[traceStage] : "Ready to assemble a business profile"}</strong>
            <em>business_0842</em>
          </div>

          <div className="landing-infra-canvas">
            <span className="landing-infra-plane is-inputs">Evidence inputs</span>
            <span className="landing-infra-plane is-profile">Unified profile</span>
            <span className="landing-infra-plane is-decision">Audience decision</span>
            <span className="landing-infra-plane is-output">Lead output</span>

            <svg className="landing-infra-links" viewBox="0 0 1160 440" preserveAspectRatio="none" aria-hidden="true">
              <InfraLink active={traceStage === 0} completed={traceStage > 0} d="M200 79 C245 79 245 139 300 139" />
              <InfraLink active={traceStage === 1} completed={traceStage > 1} d="M200 179 C245 179 245 309 300 309" />
              <InfraLink active={traceStage === 2} completed={traceStage > 2} d="M200 279 C245 279 245 139 300 139" />
              <InfraLink active={traceStage === 3} completed={traceStage > 3} d="M200 379 C245 379 245 309 300 309" />
              <InfraLink active={traceStage === 4} completed={traceStage > 4} d="M450 139 C485 139 485 224 520 224" />
              <InfraLink active={traceStage === 4} completed={traceStage > 4} d="M450 309 C485 309 485 224 520 224" />
              <InfraLink active={traceStage === 6} completed={traceStage > 6} d="M680 224 C710 224 705 284 735 284" />
              <InfraLink active={traceStage === 6} completed={traceStage > 6} d="M810 153 L810 250" />
              <InfraLink active={traceStage === 6} completed={traceStage > 6} d="M1005 153 C930 153 930 284 885 284" />
              <InfraLink active={traceStage === 7} completed={false} d="M885 284 L930 284" />
            </svg>

            <InfraNode active={traceStage === 0} className="is-listings" completed={traceStage > 0} detail="identity · trade · location" icon={<MapPin size={17} />} kind="Public signal" title="Business listings" />
            <InfraNode active={traceStage === 1} className="is-websites" completed={traceStage > 1} detail="contact · forms · booking" icon={<Globe size={17} />} kind="Public signal" title="Business websites" />
            <InfraNode active={traceStage === 2} className="is-records" completed={traceStage > 2} detail="status · classification" icon={<Building2 size={17} />} kind="Public signal" title="Public records" />
            <InfraNode active={traceStage === 3} className="is-corrections" completed={traceStage > 3} detail="reviewed conflict fixes" icon={<UserCheck size={17} />} kind="Reviewed input" title="Curated corrections" />
            <InfraNode active={traceStage === 4} className="is-identity" completed={traceStage > 4} detail="one business, one identity" icon={<UsersRound size={17} />} kind="Reconcile" title="Identity resolution" />
            <InfraNode active={traceStage === 4} className="is-verification" completed={traceStage > 4} detail="compare observations" icon={<ShieldCheck size={17} />} kind="Reconcile" title="Fact verification" />
            <InfraNode active={traceStage === 5} className="is-unified-profile" completed={traceStage > 5} detail="facts + evidence + freshness" icon={<Package size={17} />} kind="Combined record" title="Business profile" />
            <InfraNode active={traceStage === 6} className="is-audience-criteria" completed={traceStage > 6} detail="trade · market · signals" icon={<Settings size={17} />} kind="Your criteria" title="Saved audience" />
            <InfraNode active={traceStage === 6} className="is-audience-match" completed={traceStage > 6} detail="confirmed facts only" icon={<Target size={17} />} kind="Decision" title="Audience match" />
            <InfraNode active={traceStage === 6} className="is-delivery-memory" completed={traceStage > 6} detail="prevents repeat delivery" icon={<Ban size={17} />} kind="Memory" title="Previous deliveries" />
            <InfraNode active={traceStage === 7} className="is-lead-output" completed={false} detail="reason + evidence attached" icon={<CheckCircle2 size={17} />} kind="Result" title="Qualified lead" />
          </div>

          <div className="landing-infra-portrait" aria-label="Vertical business evidence flow">
            <span className="landing-infra-portrait-plane is-inputs">Evidence inputs</span>
            <span className="landing-infra-portrait-plane is-profile">Unified profile</span>
            <span className="landing-infra-portrait-plane is-decision">Audience decision</span>
            <span className="landing-infra-portrait-plane is-output">Lead output</span>

            <svg className="landing-infra-portrait-links" viewBox="0 0 440 930" preserveAspectRatio="none" aria-hidden="true">
              <InfraLink active={traceStage === 0} completed={traceStage > 0} d="M106 116 C106 220 106 235 106 294" />
              <InfraLink active={traceStage === 1} completed={traceStage > 1} d="M334 116 C334 220 334 235 334 294" />
              <InfraLink active={traceStage === 2} completed={traceStage > 2} d="M106 204 C106 230 106 245 106 294" />
              <InfraLink active={traceStage === 3} completed={traceStage > 3} d="M334 204 C334 230 334 245 334 294" />
              <InfraLink active={traceStage === 4} completed={traceStage > 4} d="M106 362 C106 406 170 406 220 438" />
              <InfraLink active={traceStage === 4} completed={traceStage > 4} d="M334 362 C334 406 270 406 220 438" />
              <InfraLink active={traceStage === 6} completed={traceStage > 6} d="M220 506 C220 570 220 630 220 700" />
              <InfraLink active={traceStage === 6} completed={traceStage > 6} d="M106 634 C106 672 165 672 220 700" />
              <InfraLink active={traceStage === 6} completed={traceStage > 6} d="M334 634 C334 672 275 672 220 700" />
              <InfraLink active={traceStage === 7} completed={false} d="M220 768 L220 842" />
            </svg>

            <InfraNode active={traceStage === 0} className="is-portrait-listings" completed={traceStage > 0} detail="identity · trade · location" icon={<MapPin size={16} />} kind="Public signal" title="Business listings" />
            <InfraNode active={traceStage === 1} className="is-portrait-websites" completed={traceStage > 1} detail="contact · forms · booking" icon={<Globe size={16} />} kind="Public signal" title="Business websites" />
            <InfraNode active={traceStage === 2} className="is-portrait-records" completed={traceStage > 2} detail="status · classification" icon={<Building2 size={16} />} kind="Public signal" title="Public records" />
            <InfraNode active={traceStage === 3} className="is-portrait-corrections" completed={traceStage > 3} detail="reviewed conflict fixes" icon={<UserCheck size={16} />} kind="Reviewed input" title="Curated corrections" />
            <InfraNode active={traceStage === 4} className="is-portrait-identity" completed={traceStage > 4} detail="one business, one identity" icon={<UsersRound size={16} />} kind="Reconcile" title="Identity resolution" />
            <InfraNode active={traceStage === 4} className="is-portrait-verification" completed={traceStage > 4} detail="compare observations" icon={<ShieldCheck size={16} />} kind="Reconcile" title="Fact verification" />
            <InfraNode active={traceStage === 5} className="is-portrait-profile" completed={traceStage > 5} detail="facts + evidence + freshness" icon={<Package size={16} />} kind="Combined record" title="Business profile" />
            <InfraNode active={traceStage === 6} className="is-portrait-criteria" completed={traceStage > 6} detail="trade · market · signals" icon={<Settings size={16} />} kind="Your criteria" title="Saved audience" />
            <InfraNode active={traceStage === 6} className="is-portrait-memory" completed={traceStage > 6} detail="prevents repeat delivery" icon={<Ban size={16} />} kind="Memory" title="Previous deliveries" />
            <InfraNode active={traceStage === 6} className="is-portrait-match" completed={traceStage > 6} detail="confirmed facts only" icon={<Target size={16} />} kind="Decision" title="Audience match" />
            <InfraNode active={traceStage === 7} className="is-portrait-lead" completed={false} detail="reason + evidence attached" icon={<CheckCircle2 size={16} />} kind="Result" title="Qualified lead" />
          </div>

        </div>
      </div>
    </section>
  );
}

function InfraNode({
  active,
  className = "",
  completed,
  detail,
  icon,
  kind,
  title,
}: {
  active: boolean;
  className?: string;
  completed: boolean;
  detail: string;
  icon: ReactNode;
  kind: string;
  title: string;
}) {
  return (
    <div className={`landing-infra-node ${className}${active ? " is-active" : ""}${completed ? " is-complete" : ""}`.trim()}>
      <span>{completed ? <CheckCircle2 size={17} /> : icon}</span>
      <div><em>{kind}</em><strong>{title}</strong><small>{detail}</small></div>
      <i />
    </div>
  );
}

function InfraLink({ active, completed, d }: { active: boolean; completed: boolean; d: string }) {
  return (
    <g className={`${active ? "is-active" : ""}${completed ? " is-complete" : ""}`.trim()}>
      <path d={d} />
      {active ? (
        <circle className="landing-infra-packet" r="4">
          <animateMotion dur="0.9s" path={d} repeatCount="indefinite" />
        </circle>
      ) : null}
    </g>
  );
}

const FAQ_ITEMS: Array<{ answer: ReactNode; question: string }> = [
  {
    answer: (
      <>
        Public sources only — business listings, public records, and the businesses' own websites. ScoutLead never
        uses private or purchased contact data.
      </>
    ),
    question: "Where does the business data come from?",
  },
  {
    answer: (
      <>
        A fact was <b>observed in a public source we can point to</b>. If it can't be observed, it's marked unknown
        — ScoutLead doesn't infer or estimate.
      </>
    ),
    question: "What does “confirmed” mean?",
  },
  {
    answer: (
      <>
        Each audience remembers what it has already delivered. New runs return{" "}
        <b>only businesses you haven't seen before</b>, deduped automatically.
      </>
    ),
    question: "How are duplicate deliveries prevented?",
  },
  {
    answer: (
      <>
        It stays blank. An unknown <b>never counts as a match</b>, and criteria are never widened to fill a quota.
      </>
    ),
    question: "What happens when a fact is unknown?",
  },
  {
    answer: (
      <>
        No. Drafts wait for your approval and send from <b>your own Gmail</b>. Nothing goes out until you click
        send.
      </>
    ),
    question: "Does ScoutLead send outreach automatically?",
  },
];

function FaqSection() {
  const [sectionRef, sectionActive] = useRevealOnScroll<HTMLElement>("0px");
  const [openIndexes, setOpenIndexes] = useState<number[]>([0]);

  const toggle = (index: number) => {
    setOpenIndexes((current) =>
      current.includes(index) ? current.filter((item) => item !== index) : [...current, index],
    );
  };

  return (
    <section className="landing-section landing-faq-section" aria-label="Frequently asked questions" ref={sectionRef}>
      <div className="landing-faq-inner">
        <div className="landing-section-heading landing-faq-head">
          <p className="landing-eyebrow">Questions before a first run</p>
          <h2>What the evidence means</h2>
          <p className="landing-lede">The short version of how sourcing, matching, and delivery behave.</p>
        </div>
        <div className={`landing-faq-list${sectionActive ? " is-active" : ""}`}>
          {FAQ_ITEMS.map((item, index) => (
            <FaqAccordionItem
              answer={item.answer}
              index={index}
              key={item.question}
              open={openIndexes.includes(index)}
              question={item.question}
              onToggle={() => toggle(index)}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

function FaqAccordionItem({
  answer,
  index,
  onToggle,
  open,
  question,
}: {
  answer: ReactNode;
  index: number;
  onToggle: () => void;
  open: boolean;
  question: string;
}) {
  return (
    <div className={`landing-faq-item${open ? " is-open" : ""}`}>
      <button aria-expanded={open} className="landing-faq-question" type="button" onClick={onToggle}>
        <span className="landing-faq-number">{String(index + 1).padStart(2, "0")}</span>
        <span className="landing-faq-question-text">{question}</span>
        <span className="landing-faq-toggle" aria-hidden="true" />
      </button>
      <div className="landing-faq-answer">
        <div className="landing-faq-answer-inner">
          <p>{answer}</p>
        </div>
      </div>
    </div>
  );
}
