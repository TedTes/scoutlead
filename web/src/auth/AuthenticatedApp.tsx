import { ClerkProvider, SignInButton, SignUpButton, UserButton, useAuth, useUser } from "@clerk/react";
import { ArrowRight } from "lucide-react";
import { App } from "../app/App";
import { getClerkPublishableKey } from "../config/env";

export default function AuthenticatedApp() {
  const publishableKey = getClerkPublishableKey();

  if (!publishableKey) {
    return <App />;
  }

  return (
    <ClerkProvider publishableKey={publishableKey}>
      <ClerkGate />
    </ClerkProvider>
  );
}

function ClerkGate() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const { user } = useUser();

  if (!isLoaded) {
    return <AuthAccessScreen mode="loading" title="Loading account" />;
  }

  if (!isSignedIn) {
    return <AuthAccessScreen mode={preferredAuthMode()} title="Sign in to ScoutLead" />;
  }

  const approverLabel =
    user?.fullName || user?.primaryEmailAddress?.emailAddress || user?.username || undefined;

  return (
    <App
      getAuthToken={() => getToken()}
      accountSlot={<UserButton appearance={{ elements: { avatarBox: "clerk-avatar-box" } }} />}
      approverLabel={approverLabel}
    />
  );
}

function AuthAccessScreen({ mode, title }: { mode: "loading" | "signin" | "signup"; title: string }) {
  return (
    <main className="landing-page">
      <div className="landing-shell">
        <nav className="landing-nav" aria-label="ScoutLead">
          <a className="landing-brand" href="/">
            <span className="landing-mark">S</span>
            <div>
              <strong>ScoutLead</strong>
              <span>Discovery Console</span>
            </div>
          </a>
        </nav>
        <section className="landing-hero">
          <div className="landing-copy">
            <p className="landing-eyebrow">Account access</p>
            <h1>{title}</h1>
            <p className="landing-lede">
              Sign in to load your products, saved discoveries, outreach drafts, and integrations.
            </p>
            {mode === "loading" ? null : (
              <div className="landing-actions">
                {mode === "signup" ? (
                  <>
                    <SignUpButton mode="modal">
                      <button className="landing-primary" type="button">
                        Create account <ArrowRight size={16} />
                      </button>
                    </SignUpButton>
                    <SignInButton mode="modal">
                      <button className="landing-secondary" type="button">
                        Sign in
                      </button>
                    </SignInButton>
                  </>
                ) : (
                  <>
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
                  </>
                )}
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function preferredAuthMode() {
  if (typeof window === "undefined") return "signin";
  return new URLSearchParams(window.location.search).get("signup") === "1" ? "signup" : "signin";
}
