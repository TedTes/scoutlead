import {
  ArrowRight,
  Ban,
  CheckCircle2,
  ListChecks,
  Mail,
  Search,
  ShieldCheck,
  Target,
  UserCheck,
} from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";

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

function LandingPage() {
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
              Build a verified, reviewable shortlist for a specific niche, score each business against your
              product, and keep outreach human-approved.
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
          </div>

          <AnimatedPreview />
        </section>

        <section className="landing-section landing-recap-section" aria-label="How it works">
          <p className="landing-eyebrow">How it works</p>
          <div className="landing-recap">
            <span className="landing-recap-item">
              <Search size={15} /> Describe who you're looking for
            </span>
            <ArrowRight className="landing-recap-arrow" size={14} />
            <span className="landing-recap-item">
              <Target size={15} /> Get a fit score, with evidence
            </span>
            <ArrowRight className="landing-recap-arrow" size={14} />
            <span className="landing-recap-item">
              <Mail size={15} /> Verify, then approve every send
            </span>
          </div>
        </section>

        <section className="landing-section landing-trust-section" aria-label="Compliance and safeguards">
          <p className="landing-eyebrow">Built to keep outreach clean</p>
          <h2>Compliance is enforced in code, not left to good intentions</h2>
          <div className="landing-trust-row">
            <span className="landing-trust-pill" title="A lead can't move to outreach until its email or phone has been verified as valid.">
              <ShieldCheck size={14} /> Verification before outreach
            </span>
            <span
              className="landing-trust-pill"
              title="Bounced, unsubscribed, or suppressed contacts are blocked from further outreach automatically."
            >
              <Ban size={14} /> Automatic suppression
            </span>
            <span className="landing-trust-pill" title="Approval is a required step, not a setting. Every draft waits for you before it's sent.">
              <UserCheck size={14} /> Human approval required
            </span>
            <span
              className="landing-trust-pill"
              title="A campaign won't start if a required provider — search, verification, or email — isn't configured."
            >
              <ListChecks size={14} /> Preflight checks
            </span>
          </div>
        </section>

        <section className="landing-section" aria-label="Use cases">
          <p className="landing-eyebrow">Use it either way</p>
          <h2>Validate an idea, or build a pipeline — same workflow</h2>
          <div className="landing-goals-grid">
            <GoalCard
              tag="Learn"
              title="Validate before you build"
              body="Run real discovery interviews with verified, reachable operators in your target niche before you commit engineering time."
            />
            <GoalCard
              tag="Sell"
              title="Build a qualified pipeline"
              body="Turn the same scored, verified shortlist into an outbound pipeline once you know who to target."
            />
          </div>
        </section>

        <section className="landing-section" aria-label="Example verticals">
          <p className="landing-eyebrow">Built for local service software</p>
          <h2>Painting, HVAC, auto services, home services — wherever your customers are small and local</h2>
          <p className="landing-lede">
            ScoutLead ships with search templates tuned for owner-operated, local service businesses — the kind of
            company that's hard to find in a generic B2B list.
          </p>
          <div className="landing-niche-row">
            <span
              className="landing-niche-pill"
              title="independent painting businesses in Toronto with a website, strong reviews, and owner contact details"
            >
              Painting
            </span>
            <span
              className="landing-niche-pill"
              title="HVAC operators in Denver with emergency service pages, direct phone numbers, and clear service areas"
            >
              HVAC
            </span>
            <span
              className="landing-niche-pill"
              title="commercial auto service providers in Austin with business service pages, reachable contacts, and clear customer proof"
            >
              Auto Services
            </span>
            <span
              className="landing-niche-pill"
              title="small owner-operated home service providers in Seattle with reachable contact details and active service pages"
            >
              Home Services
            </span>
          </div>
        </section>

        <section className="landing-cta" aria-label="Get started">
          <h2>Build your first shortlist</h2>
          <p className="landing-lede">
            Describe your target customer and see what ScoutLead finds — verified, scored, and ready for you to
            review.
          </p>
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

const PREVIEW_QUERY =
  "independent residential painters in Toronto with a website, quote form, and owner contact";

const PREVIEW_LEADS = [
  { name: "Top Shelf Painting & Staining Inc.", location: "Toronto, ON", score: 95 },
  { name: "Home Painters Toronto", location: "Toronto, ON", score: 90 },
  { name: "CAM Painters", location: "Toronto, ON", score: 88 },
];

type DrawerStage = "hidden" | "detail" | "draft" | "sent";

type PreviewPhase = {
  drawerStage: DrawerStage;
  scores: number[];
  typed: number;
  verified: boolean[];
  visibleRows: number;
};

const PREVIEW_PHASE_INITIAL: PreviewPhase = {
  drawerStage: "hidden",
  scores: [0, 0, 0],
  typed: 0,
  verified: [false, false, false],
  visibleRows: 0,
};

const PREVIEW_PHASE_RESOLVED: PreviewPhase = {
  drawerStage: "sent",
  scores: PREVIEW_LEADS.map((lead) => lead.score),
  typed: PREVIEW_QUERY.length,
  verified: PREVIEW_LEADS.map(() => true),
  visibleRows: PREVIEW_LEADS.length,
};

function AnimatedPreview() {
  const [phase, setPhase] = useState<PreviewPhase>(PREVIEW_PHASE_INITIAL);
  const [cycle, setCycle] = useState(0);

  useEffect(() => {
    const reduceMotion =
      typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduceMotion) {
      setPhase(PREVIEW_PHASE_RESOLVED);
      return;
    }

    const timers: number[] = [];
    const at = (ms: number, run: () => void) => timers.push(window.setTimeout(run, ms));

    setPhase(PREVIEW_PHASE_INITIAL);

    const CHAR_MS = 22;
    for (let i = 1; i <= PREVIEW_QUERY.length; i++) {
      at(i * CHAR_MS, () => setPhase((p) => ({ ...p, typed: i })));
    }
    const typingDone = PREVIEW_QUERY.length * CHAR_MS;

    const REVEAL_GAP = 220;
    PREVIEW_LEADS.forEach((_, idx) => {
      at(typingDone + 350 + idx * REVEAL_GAP, () => setPhase((p) => ({ ...p, visibleRows: idx + 1 })));
    });
    const revealDone = typingDone + 350 + PREVIEW_LEADS.length * REVEAL_GAP;

    const COUNT_MS = 450;
    const STEPS = 10;
    PREVIEW_LEADS.forEach((lead, idx) => {
      const start = revealDone + 200 + idx * 200;
      for (let step = 1; step <= STEPS; step++) {
        at(start + (COUNT_MS / STEPS) * step, () =>
          setPhase((p) => {
            const scores = [...p.scores];
            scores[idx] = Math.round((lead.score * step) / STEPS);
            return { ...p, scores };
          }),
        );
      }
      at(start + COUNT_MS + 100, () =>
        setPhase((p) => {
          const verified = [...p.verified];
          verified[idx] = true;
          return { ...p, verified };
        }),
      );
    });
    const scoringDone = revealDone + 200 + (PREVIEW_LEADS.length - 1) * 200 + COUNT_MS + 100;

    at(scoringDone + 250, () => setPhase((p) => ({ ...p, drawerStage: "detail" })));
    at(scoringDone + 250 + 1500, () => setPhase((p) => ({ ...p, drawerStage: "draft" })));
    at(scoringDone + 250 + 1500 + 1700, () => setPhase((p) => ({ ...p, drawerStage: "sent" })));
    at(scoringDone + 250 + 1500 + 1700 + 1500, () => setCycle((c) => c + 1));

    return () => timers.forEach(clearTimeout);
  }, [cycle]);

  const topLead = PREVIEW_LEADS[0];
  const drawerVisible = phase.drawerStage !== "hidden";

  return (
    <div className="landing-preview" aria-label="ScoutLead shortlist preview">
      <div className="preview-topbar">
        <div>
          <span>Product</span>
          <strong>quotevan</strong>
        </div>
        <button type="button" aria-label="Preview account" />
      </div>
      <div className="terminal-query">
        {PREVIEW_QUERY.slice(0, phase.typed)}
        <span className="terminal-cursor" aria-hidden="true" />
      </div>
      <div className={`preview-stats${phase.visibleRows > 0 ? "" : " is-hidden"}`}>
        16 found · 9 verified · 10 good fit · 1 shortlisted
      </div>
      <div className="preview-grid">
        <div className="preview-list">
          {PREVIEW_LEADS.map((lead, idx) => {
            const visible = idx < phase.visibleRows;
            return (
              <div
                aria-hidden={!visible}
                className={`preview-lead${visible ? "" : " is-hidden"}`}
                key={lead.name}
              >
                <span className="preview-score">{phase.scores[idx]}</span>
                <div>
                  <strong>{lead.name}</strong>
                  <span>Residential painting contractor · {lead.location}</span>
                </div>
                {phase.verified[idx] ? <em className="terminal-verified-enter">Verified</em> : <em>&nbsp;</em>}
              </div>
            );
          })}
        </div>
        <div aria-hidden={!drawerVisible} className={`preview-drawer${drawerVisible ? "" : " is-hidden"}`}>
          {phase.drawerStage === "draft" || phase.drawerStage === "sent" ? (
            <>
              <div className="preview-drawer-header">
                <span className="preview-score large">
                  {phase.drawerStage === "sent" ? <CheckCircle2 size={20} /> : <Mail size={20} />}
                </span>
                <div>
                  <strong>Adam Johns</strong>
                  <span>adam@topshelfhomes.ca</span>
                </div>
              </div>
              <p>
                Subject: Quick question about your quoting process — a short note asking how you currently handle
                quotes for new jobs.
              </p>
              <div className="preview-evidence">
                <span>Draft</span>
                <span>Personalized</span>
                <span>{phase.drawerStage === "sent" ? "Sent" : "Awaiting approval"}</span>
              </div>
              <div className="preview-actions">
                <button type="button">Edit draft</button>
                <button type="button">{phase.drawerStage === "sent" ? "Sent ✓" : "Approve & send"}</button>
              </div>
            </>
          ) : (
            <>
              <div className="preview-drawer-header">
                <span className="preview-score large">{topLead.score}</span>
                <div>
                  <strong>Top Shelf Painting</strong>
                  <span>Owner/operator · {topLead.location}</span>
                </div>
              </div>
              <p>
                Independent painting contractor with on-site estimating, a verified email, and direct phone
                contact.
              </p>
              <div className="preview-evidence">
                <span>Website found</span>
                <span>Email deliverable</span>
                <span>Owner identified</span>
              </div>
              <div className="preview-actions">
                <button type="button">Shortlist</button>
                <button type="button">Review outreach</button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function GoalCard({ body, tag, title }: { body: string; tag: string; title: string }) {
  return (
    <div className="landing-goal-card">
      <span className="landing-goal-tag">{tag}</span>
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}
