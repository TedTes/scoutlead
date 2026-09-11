import { RedirectToSignIn, RedirectToSignUp, UserButton, useAuth, useUser } from "@clerk/react";
import { useCallback, useEffect, useRef } from "react";
import { App } from "../app/App";
import { getClerkPublishableKey } from "../config/env";
import { AuthLoadingScreen } from "./AuthLoadingScreen";

export default function AuthenticatedApp() {
  const publishableKey = getClerkPublishableKey();

  if (!publishableKey) {
    return <App />;
  }

  return <ClerkGate />;
}

function ClerkGate() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const { user } = useUser();
  const getTokenRef = useRef(getToken);
  useEffect(() => {
    getTokenRef.current = getToken;
  }, [getToken]);
  const getAuthToken = useCallback(() => getTokenRef.current(), []);

  if (!isLoaded) {
    return <AuthLoadingScreen />;
  }

  if (!isSignedIn) {
    const redirectProps = {
      fallbackRedirectUrl: "/app",
      forceRedirectUrl: "/app",
    };
    return preferredAuthMode() === "signup" ? (
      <RedirectToSignUp {...redirectProps} />
    ) : (
      <RedirectToSignIn {...redirectProps} />
    );
  }

  const approverLabel =
    user?.fullName || user?.primaryEmailAddress?.emailAddress || user?.username || undefined;

  return (
    <App
      getAuthToken={getAuthToken}
      accountSlot={<UserButton appearance={{ elements: { avatarBox: "clerk-avatar-box" } }} />}
      approverLabel={approverLabel}
    />
  );
}

function preferredAuthMode() {
  if (typeof window === "undefined") return "signin";
  return new URLSearchParams(window.location.search).get("signup") === "1" ? "signup" : "signin";
}
