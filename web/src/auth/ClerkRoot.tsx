import { ClerkProvider, SignInButton, SignUpButton, UserButton, useAuth } from "@clerk/react";
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
import type { ReactNode } from "react";
import { App } from "../app/App";
import { getClerkPublishableKey } from "../config/env";

export function RootApp() {
  const publishableKey = getClerkPublishableKey();

  if (!publishableKey) {
    return <App />;
  }

  return (
    <ClerkProvider publishableKey={publishableKey}>
      <ClerkEnabledApp />
    </ClerkProvider>
  );
}

function ClerkEnabledApp() {
  const { getToken, isLoaded, isSignedIn } = useAuth();

  if (!isLoaded) {
    return <AuthScreen eyebrow="ScoutLead" title="Loading account" />;
  }

  if (!isSignedIn) {
    return <LandingPage />;
  }

  return (
    <App
      getAuthToken={() => getToken()}
      accountSlot={<UserButton appearance={{ elements: { avatarBox: "clerk-avatar-box" } }} />}
    />
  );
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
            <SignInButton mode="modal">
              <button className="landing-nav-button" type="button">
                Sign in
              </button>
            </SignInButton>
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
              <SignInButton mode="modal">
                <button className="landing-primary" type="button">
                  Sign in <ArrowRight size={16} />
                </button>
              </SignInButton>
              <SignUpButton mode="modal">
                <button className="landing-secondary" type="button">
                  Create account
                </button>
              </SignUpButton>
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

          <div className="landing-preview" aria-label="ScoutLead shortlist preview">
            <div className="preview-topbar">
              <div>
                <span>Product</span>
                <strong>quotevan</strong>
              </div>
              <button type="button" aria-label="Preview account" />
            </div>
            <div className="preview-query">
              Independent residential painters in Toronto with a website, quote form, and owner contact
            </div>
            <div className="preview-stats">16 found · 9 verified · 10 good fit · 1 shortlisted</div>
            <div className="preview-grid">
              <div className="preview-list">
                <PreviewLead score="95" name="Top Shelf Painting & Staining Inc." status="Good fit" verified />
                <PreviewLead score="90" name="Home Painters Toronto" status="Good fit" verified />
                <PreviewLead score="88" name="CAM Painters" status="Good fit" verified />
              </div>
              <div className="preview-drawer">
                <div className="preview-drawer-header">
                  <span className="preview-score large">95</span>
                  <div>
                    <strong>Top Shelf Painting</strong>
                    <span>Owner/operator · Toronto, ON</span>
                  </div>
                </div>
                <p>
                  Independent painting contractor with on-site estimating, a verified email, and direct phone contact.
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
              </div>
            </div>
          </div>
        </section>

        <section className="landing-section" aria-label="How it works">
          <p className="landing-eyebrow">How it works</p>
          <h2>From a plain-language prompt to an approved send</h2>
          <div className="landing-steps-grid">
            <StepCard
              index={1}
              icon={<Search size={18} />}
              title="Describe who you're looking for"
              body="Tell ScoutLead the niche, the location, and the signals that matter — a website, a quote form, an owner you can actually reach."
            />
            <StepCard
              index={2}
              icon={<ListChecks size={18} />}
              title="It finds and dedupes matches"
              body="Businesses are pulled from real sources and checked against what you've already found, so repeat searches don't waste a run."
            />
            <StepCard
              index={3}
              icon={<Target size={18} />}
              title="Every lead gets a fit score, with evidence"
              body="Each business is scored against your product with the positive signals, missing evidence, and risks behind that score — not just a number."
            />
            <StepCard
              index={4}
              icon={<Mail size={18} />}
              title="You approve every message before it sends"
              body="Contacts are verified before a draft is written, and outreach waits for your approval before anything goes out."
            />
          </div>
        </section>

        <section className="landing-section" aria-label="Compliance and safeguards">
          <p className="landing-eyebrow">Built to keep outreach clean</p>
          <h2>Compliance is enforced in code, not left to good intentions</h2>
          <div className="landing-trust-grid">
            <TrustItem
              icon={<ShieldCheck size={17} />}
              title="Verification before outreach"
              body="A lead can't move to outreach until its email or phone has been verified as valid."
            />
            <TrustItem
              icon={<Ban size={17} />}
              title="Suppression is automatic"
              body="Bounced, unsubscribed, or suppressed contacts are blocked from further outreach — the workflow won't send to them again."
            />
            <TrustItem
              icon={<UserCheck size={17} />}
              title="Nothing sends without a human"
              body="Approval is a required step, not a setting. Every draft waits for you before it's sent."
            />
            <TrustItem
              icon={<ListChecks size={17} />}
              title="Preflight checks catch gaps early"
              body="A campaign won't start if a required provider — search, verification, or email — isn't configured."
            />
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
          <div className="landing-example-grid">
            <ExampleCard
              niche="Painting"
              query="independent painting businesses in Toronto with a website, strong reviews, and owner contact details"
            />
            <ExampleCard
              niche="HVAC"
              query="HVAC operators in Denver with emergency service pages, direct phone numbers, and clear service areas"
            />
            <ExampleCard
              niche="Auto Services"
              query="commercial auto service providers in Austin with business service pages, reachable contacts, and clear customer proof"
            />
            <ExampleCard
              niche="Home Services"
              query="small owner-operated home service providers in Seattle with reachable contact details and active service pages"
            />
          </div>
        </section>

        <section className="landing-cta" aria-label="Get started">
          <h2>Build your first shortlist</h2>
          <p className="landing-lede">
            Describe your target customer and see what ScoutLead finds — verified, scored, and ready for you to
            review.
          </p>
          <div className="landing-actions">
            <SignInButton mode="modal">
              <button className="landing-primary" type="button">
                Sign in <ArrowRight size={16} />
              </button>
            </SignInButton>
            <SignUpButton mode="modal">
              <button className="landing-secondary" type="button">
                Create account
              </button>
            </SignUpButton>
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

function StepCard({
  body,
  icon,
  index,
  title,
}: {
  body: string;
  icon: ReactNode;
  index: number;
  title: string;
}) {
  return (
    <div className="landing-step">
      <span className="landing-step-index">{index}</span>
      <span className="landing-step-icon">{icon}</span>
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}

function TrustItem({ body, icon, title }: { body: string; icon: ReactNode; title: string }) {
  return (
    <div className="landing-trust-item">
      <span className="landing-trust-icon">{icon}</span>
      <div>
        <h3>{title}</h3>
        <p>{body}</p>
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

function ExampleCard({ niche, query }: { niche: string; query: string }) {
  return (
    <div className="landing-example-card">
      <span className="landing-example-label">{niche}</span>
      <p className="landing-example-query">{query}</p>
    </div>
  );
}

function PreviewLead({
  name,
  score,
  status,
  verified,
}: {
  name: string;
  score: string;
  status: string;
  verified?: boolean;
}) {
  return (
    <div className="preview-lead">
      <span className="preview-score">{score}</span>
      <div>
        <strong>{name}</strong>
        <span>Residential painting contractor · Toronto, ON</span>
      </div>
      <em>{verified ? "Verified" : status}</em>
    </div>
  );
}

function AuthScreen({
  actions,
  body,
  eyebrow,
  title,
}: {
  actions?: ReactNode;
  body?: string;
  eyebrow: string;
  title: string;
}) {
  return (
    <main className="auth-screen">
      <section className="auth-panel">
        <span className="auth-mark">S</span>
        <p>{eyebrow}</p>
        <h1>{title}</h1>
        {body ? <span className="auth-body">{body}</span> : null}
        {actions ? <div className="auth-actions">{actions}</div> : null}
      </section>
    </main>
  );
}
