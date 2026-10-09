import {
  ClerkProvider,
  SignInButton,
  SignUpButton,
} from "@clerk/react";
import {
  ArrowRight,
  Ban,
  Building2,
  CalendarClock,
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

  if (!isAppRoute(path)) return <LandingPage authEnabled={authEnabled} />;

  return (
    <Suspense fallback={<AuthLoadingScreen />}>
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

function useRevealOnScroll<T extends HTMLElement>(rootMargin = "0px") {
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
      { rootMargin, threshold: 0.35 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [active, rootMargin]);

  return [ref, active] as const;
}

function LandingPage({ authEnabled }: { authEnabled: boolean }) {
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

        <section className="landing-hero">
          <div className="landing-hero-head">
            <div className="landing-copy">
              <p className="landing-eyebrow">Evidence-backed local business discovery</p>
              <h1>Find the right local businesses, backed by real evidence.</h1>
              <p className="landing-lede">
                Pick a trade, a market, and the signals that mean opportunity: a missing website, no booking flow,
                or thin reviews. ScoutLead returns matching businesses with the evidence behind each. Run it on
                demand or on your own cadence.
              </p>
            </div>
          </div>

          <AnimatedPreview />
          <GlobeActivityPreview />
        </section>

        <section className="landing-section landing-proof-section" id="lead-proof" aria-label="Lead review example">
          <div className="landing-proof-inner">
            <div className="landing-section-heading landing-proof-heading">
              <p className="landing-eyebrow">Lead review</p>
              <h2>See exactly why each business qualified</h2>
              <p className="landing-lede">
                Compare fit, the opportunity signal, contact readiness, and the underlying source without opening
                every result. Expand a lead when you need the full reasoning and a grounded opener.
              </p>
            </div>
            <WorkflowProofPreview />
          </div>
        </section>

        <AudienceUseCases />

        <HowItWorksSection />

        <DataProvenanceSection />

        <OutreachSection />

        <TrustSection />

        <FaqSection />

        <section className="landing-cta" aria-label="Get started">
          <h2>Build an audience you can inspect and reuse</h2>
          <p className="landing-lede">
            Start with one trade, one market, and the signals that make a business worth contacting.
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
            <LandingSignUpAction authEnabled={authEnabled} className="landing-primary">
              Create account <ArrowRight size={16} />
            </LandingSignUpAction>
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
];

const PREVIEW_LEAD_TOTAL = PREVIEW_LEADS.length;
const PREVIEW_VERIFIED_TOTAL = PREVIEW_LEADS.filter((lead) => lead.statusTone === "green").length;
const PREVIEW_QUERY = "Toronto Painters Missing Website";

const PREVIEW_RUNS = [
  { title: "Toronto Roofers - Low Reviews", meta: "12 · 9 verified", count: "", date: "Oct 2", tone: "green" },
  { title: "Toronto Electricians - Low Reviews", meta: "15 · 11 verified", count: "", date: "Sep 30", tone: "green" },
  { title: "Toronto Painters Missing Website", meta: "25 leads", count: "", date: "Oct 3", tone: "green" },
  { title: "Toronto HVAC No Quote Flow", meta: "9 found", count: "researching", date: "Oct 1", tone: "amber" },
  { title: "Toronto HVAC Low Reviews", meta: "4 leads", count: "", date: "Oct 1", tone: "green" },
];

function AnimatedPreview() {
  const [screen, setScreen] = useState<"results" | "builder" | "loading">("results");
  const [visibleLeads, setVisibleLeads] = useState(4);
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
      setVisibleLeads(4);
      setSelectedIndex(0);
      setReviewStage(3);
      setShortlisted(true);
      return;
    }

    const timers: number[] = [];
    const at = (ms: number, run: () => void) => timers.push(window.setTimeout(run, ms));
    const compactLayout = window.matchMedia("(max-width: 680px)").matches;

    setScreen("results");
    setVisibleLeads(compactLayout ? 0 : 4);
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
      setVisibleLeads(4);
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
      for (let index = 0; index < 4; index += 1) {
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
    for (let index = 0; index < 4; index += 1) {
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

  return (
    <div className="landing-preview preview-app landing-workspace-preview" aria-label="ScoutLead audience workspace preview">
      <PreviewRail activeManage="" activeRun="Toronto HVAC Low Reviews" shortlistedCount={shortlisted ? 1 : 0} />
      <div className="preview-main-panel">
        <div className="preview-audience-bar">
          <div>
            <span>Audiences</span>
            <em>/</em>
            <strong>{screen === "builder" ? "New audience" : "Toronto HVAC Low Reviews"}</strong>
          </div>
          {screen === "results" ? (
            <button className={newAudiencePressed ? "is-preview-pressed" : ""} type="button" tabIndex={-1}>
              <Plus size={13} /> New audience
              <PreviewCursor
                className="preview-cursor-actor--new-audience"
                pressed={newAudiencePressed}
                visible={newAudienceCursor}
              />
            </button>
          ) : null}
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
                leadLimit={4}
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

function WorkflowProofPreview() {
  return (
    <div className="lead-proof" aria-label="Evidence-rich lead list example">
      <div className="lead-proof-toolbar">
        <div>
          <strong>Toronto HVAC Low Reviews</strong>
          <span>4 matching businesses</span>
        </div>
        <div className="lead-proof-toolbar-meta">
          <span><Target size={13} /> Reviews under 15</span>
          <span><MapPin size={13} /> Toronto · 25 km</span>
        </div>
      </div>
      <div className="lead-proof-head" aria-hidden="true">
        <span>Business</span>
        <span>Fit</span>
        <span>Opportunity</span>
        <span>Contact</span>
        <span>Evidence</span>
      </div>
      <LeadProofRow
        business="ONCALL Heating and Cooling"
        contact="Phone only"
        evidence="Google Places"
        location="Scarborough"
        signal="4 public reviews"
        trade="HVAC"
        expanded
      />
      <LeadProofRow
        business="GTA HVAC Pros"
        contact="Email + phone"
        evidence="Google Places"
        location="Scarborough"
        signal="13 public reviews"
        trade="HVAC"
      />
      <LeadProofRow
        business="Highland HVAC Services"
        contact="Phone only"
        evidence="Google Places"
        location="Etobicoke"
        signal="13 public reviews"
        trade="HVAC"
      />
    </div>
  );
}

function LeadProofRow({
  business,
  contact,
  evidence,
  expanded = false,
  location,
  signal,
  trade,
}: {
  business: string;
  contact: string;
  evidence: string;
  expanded?: boolean;
  location: string;
  signal: string;
  trade: string;
}) {
  return (
    <div className={`lead-proof-entry${expanded ? " is-expanded" : ""}`}>
      <div className="lead-proof-row">
        <div className="lead-proof-business">
          <i />
          <span><strong>{business}</strong><em>{trade} · {location}</em></span>
        </div>
        <span className="lead-proof-fit"><CheckCircle2 size={13} /> Strong fit</span>
        <span className="lead-proof-signal"><Target size={13} /> {signal}</span>
        <span className="lead-proof-contact"><Phone size={13} /> {contact}</span>
        <span className="lead-proof-source">{evidence} <ExternalLink size={12} /></span>
      </div>
      {expanded ? (
        <div className="lead-proof-expanded">
          <div>
            <span>Why it qualified</span>
            <p>The business matches the selected HVAC trade and Toronto radius. Its 4-review count confirms the selected opportunity signal.</p>
          </div>
          <div>
            <span>Draft opener</span>
            <p>“I came across ONCALL while reviewing Toronto HVAC providers and noticed the business has only four public reviews...”</p>
          </div>
          <div className="lead-proof-actions">
            <button type="button" tabIndex={-1}>Dismiss</button>
            <button type="button" tabIndex={-1}><Star size={13} /> Shortlist</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function OutreachSection() {
  const [sectionRef, sectionActive] = useRevealOnScroll<HTMLElement>("0px");
  const [outreachStage, setOutreachStage] = useState(0);
  const outreachMessages = [
    "Evidence attached · 4 public reviews",
    "Draft grounded in the observed signal",
    "Waiting for human approval",
    "Approved · sent from your Gmail",
  ];

  useEffect(() => {
    if (!sectionActive) return;
    if (prefersReducedMotion()) {
      setOutreachStage(3);
      return;
    }

    const interval = window.setInterval(() => {
      setOutreachStage((currentStage) => (currentStage + 1) % outreachMessages.length);
    }, 1550);

    return () => window.clearInterval(interval);
  }, [sectionActive, outreachMessages.length]);

  return (
    <section
      className="landing-section landing-draft-section"
      id="outreach"
      aria-label="Outreach draft, approval, and send"
      ref={sectionRef}
    >
      <div className="landing-draft-inner">
        <div className="landing-outreach-stream" aria-live="polite">
          <span><i /> Approval workflow</span>
          <strong key={outreachStage}>{outreachMessages[outreachStage]}</strong>
          <em className={outreachStage === 3 ? "is-ready" : ""}>
            {outreachStage === 3 ? <><CheckCircle2 size={13} /> Sent</> : `0${outreachStage + 1} / 04`}
          </em>
        </div>
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
        <IntegrationStrip gmailActive={outreachStage === 3} />
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

function IntegrationStrip({ gmailActive = false }: { gmailActive?: boolean }) {
  return (
    <div className={`landing-integration-strip${gmailActive ? " is-sending" : ""}`} aria-label="Available outreach and export integrations">
      <p><strong>{gmailActive ? "Sent from your Gmail." : "Sends from your Gmail."}</strong> Exports approved leads to Sheets, webhooks, or HubSpot.</p>
      <div>
        <span className={gmailActive ? "is-active" : ""}><i className="is-gmail">G</i> Gmail</span>
        <span><i className="is-sheets">S</i> Sheets</span>
        <span><i className="is-webhook">&#123;&#125;</i> Webhooks</span>
        <span><i className="is-hubspot">H</i> HubSpot</span>
      </div>
    </div>
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
          <div className={`preview-run${run.title === activeRun ? " is-active" : ""}`} key={run.title}>
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

function HowItWorksSection() {
  const [sectionRef, sectionActive] = useRevealOnScroll<HTMLElement>("0px");
  const [activeStep, setActiveStep] = useState(0);
  const statusMessages = [
    "Audience saved · HVAC · Toronto · 25 km",
    "Opportunity selected · Reviews under 15",
    "Matching stored business facts",
    "4 new, deduped matches ready",
    "Evidence retained with every action",
  ];

  useEffect(() => {
    if (!sectionActive) return;
    if (prefersReducedMotion()) {
      setActiveStep(4);
      return;
    }

    const interval = window.setInterval(() => {
      setActiveStep((currentStep) => (currentStep + 1) % statusMessages.length);
    }, 1450);

    return () => window.clearInterval(interval);
  }, [sectionActive, statusMessages.length]);

  return (
    <section className="landing-section landing-story-section" id="how-it-works" aria-label="How ScoutLead works" ref={sectionRef}>
      <div className="landing-story-inner">
        <div className="landing-section-heading landing-story-heading">
          <div className="landing-story-title">
            <p className="landing-eyebrow">How it works</p>
            <h2>From audience criteria to a reviewable lead list</h2>
          </div>
          <p className="landing-lede">
            ScoutLead maintains the business pool separately, matches saved facts to the audience, and returns only
            the businesses with evidence for the selected signals.
          </p>
        </div>

        <div className="landing-story-stream" aria-live="polite">
          <span><i /> Matching workflow</span>
          <strong key={activeStep}>{statusMessages[activeStep]}</strong>
          <em className={activeStep === 4 ? "is-ready" : ""}>
            {activeStep === 4 ? <><CheckCircle2 size={13} /> Reviewable</> : `0${activeStep + 1} / 05`}
          </em>
        </div>

        <div className="landing-story-steps">
          <LandingStep active={activeStep === 0} completed={activeStep > 0} number="01" icon={<Search size={16} />} title="Define the audience">
            Choose the trade, customer kind, city, radius, and batch size once.
          </LandingStep>
          <LandingStep active={activeStep === 1} completed={activeStep > 1} number="02" icon={<Target size={16} />} title="Pick signals and exclusions">
            Select the opportunities to find and exclude chains, franchises, directories, or agencies.
          </LandingStep>
          <LandingStep active={activeStep === 2} completed={activeStep > 2} number="03" icon={<CalendarClock size={16} />} title="Run it your way">
            Start a batch on demand or set the cadence that fits your workflow.
          </LandingStep>
          <LandingStep active={activeStep === 3} completed={activeStep > 3} number="04" icon={<ListChecks size={16} />} title="Receive new matches">
            Each run returns new matches first and suppresses duplicate deliveries.
          </LandingStep>
          <LandingStep active={activeStep === 4} completed={false} number="05" icon={<UserCheck size={16} />} title="Act on the list">
            Shortlist, dismiss, or contact a lead. Keep the evidence attached to every decision.
          </LandingStep>
        </div>
        <div className={`landing-story-principles${activeStep === 4 ? " is-emphasized" : ""}`} aria-label="Matching behavior">
          <span><CheckCircle2 size={14} /> Confirmed signals qualify a lead</span>
          <span><CheckCircle2 size={14} /> Unknown facts remain unknown</span>
          <span><CheckCircle2 size={14} /> Criteria are never widened to fill a quota</span>
        </div>
      </div>
    </section>
  );
}

function LandingStep({
  active = false,
  children,
  completed = false,
  icon,
  number,
  title,
}: {
  active?: boolean;
  children: ReactNode;
  completed?: boolean;
  icon: ReactNode;
  number: string;
  title: string;
}) {
  return (
    <div className={`landing-step${active ? " is-active" : ""}${completed ? " is-complete" : ""}`}>
      <div className="landing-step-marker">
        <span className="landing-feature-icon">{completed ? <CheckCircle2 size={16} /> : icon}</span>
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

function AudienceUseCases() {
  const [sectionRef, sectionActive] = useRevealOnScroll<HTMLElement>("0px");
  const [activeRecipe, setActiveRecipe] = useState(0);
  const [recipeStage, setRecipeStage] = useState(0);
  const recipes = [
    {
      audience: "Painters · Toronto · 25 km",
      evidence: "Website status + source",
      icon: <Globe size={16} />,
      signal: "No website listed",
      title: "Web and SEO agencies",
    },
    {
      audience: "HVAC · Toronto · Residential",
      evidence: "Review count + listing",
      icon: <Star size={16} />,
      signal: "Fewer than 15 reviews",
      title: "Reputation consultants",
    },
    {
      audience: "Roofers · One local market",
      evidence: "Stored inspection fact",
      icon: <Target size={16} />,
      signal: "No quote or booking flow",
      title: "Conversion specialists",
    },
    {
      audience: "Plumbers · Toronto · 25 km",
      evidence: "Form status + website source",
      icon: <ListChecks size={16} />,
      signal: "No contact form",
      title: "Lead generation partners",
    },
  ];

  useEffect(() => {
    if (!sectionActive) return;
    if (prefersReducedMotion()) {
      setRecipeStage(3);
      return;
    }

    const interval = window.setInterval(() => {
      setRecipeStage((currentStage) => {
        if (currentStage < 3) return currentStage + 1;
        setActiveRecipe((currentRecipe) => (currentRecipe + 1) % recipes.length);
        return 0;
      });
    }, 1100);

    return () => window.clearInterval(interval);
  }, [sectionActive, recipes.length]);

  const currentRecipe = recipes[activeRecipe];
  const streamMessage = [
    `Scanning ${currentRecipe.audience}`,
    `Signal matched · ${currentRecipe.signal}`,
    `Evidence attached · ${currentRecipe.evidence}`,
    `Match ready for review · ${currentRecipe.title}`,
  ][recipeStage];

  return (
    <section className="landing-section landing-use-cases" aria-label="Who ScoutLead is for" ref={sectionRef}>
      <div className="landing-use-cases-inner">
        <div className="landing-section-heading">
          <p className="landing-eyebrow">Built around a commercial question</p>
          <h2>Turn the opportunity you solve into a monitored audience</h2>
          <p className="landing-lede">
            Choose who to find, where they operate, and the observable signal that makes outreach relevant.
          </p>
        </div>
        <div className="landing-use-case-list" aria-label="Example ScoutLead audience recipes">
          <div className="landing-recipe-stream" aria-label="Example audience matching activity">
            <span><i /> Audience monitor preview</span>
            <strong key={`${activeRecipe}-${recipeStage}`}>{streamMessage}</strong>
            <em className={recipeStage === 3 ? "is-ready" : ""}>
              {recipeStage === 3 ? <><CheckCircle2 size={13} /> Ready</> : `0${recipeStage + 1} / 04`}
            </em>
          </div>
          <div className="landing-recipe-head" aria-hidden="true">
            <span>Team</span><span>Who to find</span><span>Opportunity signal</span><span>Returned with</span>
          </div>
          {recipes.map((recipe, index) => (
            <LandingUseCase
              active={index === activeRecipe}
              audience={recipe.audience}
              evidence={recipe.evidence}
              icon={recipe.icon}
              key={recipe.title}
              signal={recipe.signal}
              stage={index === activeRecipe ? recipeStage : -1}
              title={recipe.title}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

function LandingUseCase({
  active,
  audience,
  evidence,
  icon,
  signal,
  stage,
  title,
}: {
  active: boolean;
  audience: string;
  evidence: string;
  icon: ReactNode;
  signal: string;
  stage: number;
  title: string;
}) {
  return (
    <div className={`landing-use-case${active ? " is-active" : ""}`}>
      <div className="landing-recipe-team">
        <span className="landing-use-case-icon">{icon}</span>
        <strong>{title}</strong>
      </div>
      <div className="landing-recipe-flow">
        <div className={`landing-recipe-node${stage >= 0 ? " is-current" : ""}`}>
          <span>Who to find</span>
          <strong>{audience}</strong>
        </div>
        <RecipeLink flowing={active && stage === 0} passed={stage >= 1} />
        <div className={`landing-recipe-node is-signal${stage >= 1 ? " is-current" : ""}`}>
          <span>Opportunity</span>
          <strong><Target size={13} /> {signal}</strong>
        </div>
        <RecipeLink flowing={active && stage === 1} passed={stage >= 2} />
        <div className={`landing-recipe-node is-evidence${stage >= 2 ? " is-current" : ""}${stage >= 3 ? " is-ready" : ""}`}>
          <span>Evidence</span>
          <strong><CheckCircle2 size={13} /> {evidence}</strong>
        </div>
      </div>
    </div>
  );
}

function RecipeLink({ flowing, passed }: { flowing: boolean; passed: boolean }) {
  return (
    <span className={`landing-recipe-link${flowing ? " is-flowing" : ""}${passed ? " is-passed" : ""}`} aria-hidden="true">
      <i />
      <ArrowRight size={15} />
    </span>
  );
}

function DataProvenanceSection() {
  const [sectionRef, sectionActive] = useRevealOnScroll<HTMLElement>("0px");
  const [traceStage, setTraceStage] = useState(0);
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
    if (!sectionActive) return;
    if (prefersReducedMotion()) {
      setTraceStage(7);
      return;
    }

    const interval = window.setInterval(() => {
      setTraceStage((currentStage) => (currentStage + 1) % traceMessages.length);
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
            <strong key={traceStage}>{traceMessages[traceStage]}</strong>
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

          <div className="landing-infra-mobile">
            <InfraMobilePlane label="Evidence inputs" active={traceStage <= 3}>
              <InfraNode active={traceStage === 0} completed={traceStage > 0} detail="identity · trade · location" icon={<MapPin size={16} />} kind="Public signal" title="Business listings" />
              <InfraNode active={traceStage === 1} completed={traceStage > 1} detail="contact · forms · booking" icon={<Globe size={16} />} kind="Public signal" title="Business websites" />
              <InfraNode active={traceStage === 2} completed={traceStage > 2} detail="status · classification" icon={<Building2 size={16} />} kind="Public signal" title="Public records" />
              <InfraNode active={traceStage === 3} completed={traceStage > 3} detail="reviewed conflict fixes" icon={<UserCheck size={16} />} kind="Reviewed input" title="Curated corrections" />
            </InfraMobilePlane>
            <InfraMobilePlane label="Unified profile" active={traceStage >= 4 && traceStage <= 5}>
              <InfraNode active={traceStage === 4} completed={traceStage > 4} detail="one business, one identity" icon={<UsersRound size={16} />} kind="Reconcile" title="Identity resolution" />
              <InfraNode active={traceStage === 4} completed={traceStage > 4} detail="compare observations" icon={<ShieldCheck size={16} />} kind="Reconcile" title="Fact verification" />
              <InfraNode active={traceStage === 5} completed={traceStage > 5} detail="facts + evidence + freshness" icon={<Package size={16} />} kind="Combined record" title="Business profile" />
            </InfraMobilePlane>
            <InfraMobilePlane label="Decision" active={traceStage === 6}>
              <InfraNode active={traceStage === 6} completed={traceStage > 6} detail="trade · market · signals" icon={<Settings size={16} />} kind="Your criteria" title="Saved audience" />
              <InfraNode active={traceStage === 6} completed={traceStage > 6} detail="confirmed facts only" icon={<Target size={16} />} kind="Decision" title="Audience match" />
              <InfraNode active={traceStage === 6} completed={traceStage > 6} detail="prevents repeat delivery" icon={<Ban size={16} />} kind="Memory" title="Previous deliveries" />
            </InfraMobilePlane>
            <InfraMobilePlane label="Lead output" active={traceStage === 7}>
              <InfraNode active={traceStage === 7} completed={false} detail="reason + evidence attached" icon={<CheckCircle2 size={16} />} kind="Result" title="Qualified lead" />
            </InfraMobilePlane>
          </div>

          <div className="landing-infra-payload">
            <span>Combined profile</span>
            <code>4 inputs reconciled</code>
            <code>unknowns preserved</code>
            <code>duplicate suppressed</code>
            <strong className={traceStage === 7 ? "is-ready" : ""}><CheckCircle2 size={13} /> Evidence retained end to end</strong>
          </div>
        </div>

        <div className="landing-fact-states" aria-label="Fact verification states">
          <FactState className="is-confirmed" title="Broader coverage">Complementary observations fill different parts of the profile.</FactState>
          <FactState className="is-source" title="One business">Duplicate records resolve to one reusable identity.</FactState>
          <FactState className="is-unknown" title="Honest gaps">Missing evidence remains unknown instead of becoming a match.</FactState>
          <FactState className="is-stale" title="Traceable result">The reason and evidence remain attached to every lead.</FactState>
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

function InfraMobilePlane({
  active,
  children,
  label,
}: {
  active: boolean;
  children: ReactNode;
  label: string;
}) {
  return (
    <div className={`landing-infra-mobile-plane${active ? " is-active" : ""}`}>
      <span>{label} plane</span>
      <div>{children}</div>
    </div>
  );
}

function FactState({ children, className, title }: { children: ReactNode; className: string; title: string }) {
  return (
    <div>
      <span className={`landing-fact-dot ${className}`} />
      <p><strong>{title}</strong>{children}</p>
    </div>
  );
}

function FaqSection() {
  return (
    <section className="landing-section landing-faq-section" aria-label="Frequently asked questions">
      <div className="landing-faq-inner">
        <div className="landing-section-heading">
          <p className="landing-eyebrow">Questions before a first run</p>
          <h2>What the evidence means</h2>
          <p className="landing-lede">The short version of how sourcing, matching, and delivery behave.</p>
        </div>
        <div className="landing-faq-list">
          <FaqItem question="Where does the business data come from?">
            Public business listings, linked business websites, structured website inspection, and curated corrections
            where a source needs review. Available fields vary by business, and the source stays attached to the fact.
          </FaqItem>
          <FaqItem question="What does confirmed mean?">
            A stored fact directly supports the selected signal. Source-listed evidence is labeled separately when a
            public profile reports something that has not been independently verified.
          </FaqItem>
          <FaqItem question="How are duplicate deliveries prevented?">
            Delivery history is stored per audience and business. A later run returns new eligible matches first
            instead of padding the batch with the same businesses again.
          </FaqItem>
          <FaqItem question="What happens when a fact is unknown?">
            Unknown stays unknown. It can remain eligible for basic trade and location filters, but it cannot satisfy a
            selected opportunity signal until evidence is stored.
          </FaqItem>
          <FaqItem question="Does ScoutLead send outreach automatically?">
            No. Drafts, exports, and sends require review and approval, and sending uses the connected account and its
            configured provider checks.
          </FaqItem>
        </div>
      </div>
    </section>
  );
}

function FaqItem({ children, question }: { children: ReactNode; question: string }) {
  return (
    <details className="landing-faq-item">
      <summary>{question}<Plus size={16} aria-hidden="true" /></summary>
      <p>{children}</p>
    </details>
  );
}

function TrustSection() {
  return (
    <section className="landing-section landing-trust-section" aria-label="Privacy and compliance">
      <div className="landing-section-heading">
        <p className="landing-eyebrow">Privacy and compliance</p>
        <h2>Outreach has guardrails before it reaches Gmail, exports, or webhooks</h2>
        <p className="landing-lede">
          Verification, suppression, human approval, and provider checks are handled once in the workflow.
        </p>
      </div>
      <div className="landing-trust-row is-active">
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
