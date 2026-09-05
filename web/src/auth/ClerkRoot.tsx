import { ClerkProvider, SignInButton, SignUpButton, UserButton, useAuth } from "@clerk/react";
import { ArrowRight, CheckCircle2, ShieldCheck } from "lucide-react";
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
      </div>
    </main>
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
