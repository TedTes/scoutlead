import { RedirectToSignIn, RedirectToSignUp, UserButton, useAuth, useUser } from "@clerk/react";
import { useCallback, useEffect, useRef } from "react";
import { AdminApp } from "../admin/AdminApp";
import { App } from "../app/App";
import { getClerkPublishableKey } from "../config/env";
import { AuthLoadingScreen } from "./AuthLoadingScreen";

export default function AuthenticatedApp() {
  const publishableKey = getClerkPublishableKey();
  const adminRoute = isAdminRoute();

  if (!publishableKey) {
    return adminRoute ? <AdminApp /> : <App />;
  }

  return <ClerkGate adminRoute={adminRoute} />;
}

function ClerkGate({ adminRoute }: { adminRoute: boolean }) {
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
    const destination = adminRoute ? "/admin" : "/app";
    const redirectProps = {
      fallbackRedirectUrl: destination,
      forceRedirectUrl: destination,
    };
    return preferredAuthMode() === "signup" ? (
      <RedirectToSignUp {...redirectProps} />
    ) : (
      <RedirectToSignIn {...redirectProps} />
    );
  }

  const approverLabel =
    user?.fullName || user?.primaryEmailAddress?.emailAddress || user?.username || undefined;
  const accountSlot = <UserButton appearance={{ elements: { avatarBox: "clerk-avatar-box" } }} />;

  if (adminRoute) {
    return (
      <AdminApp
        getAuthToken={getAuthToken}
        accountSlot={accountSlot}
        adminEmail={user?.primaryEmailAddress?.emailAddress || undefined}
      />
    );
  }

  return (
    <App
      getAuthToken={getAuthToken}
      accountSlot={accountSlot}
      approverLabel={approverLabel}
    />
  );
}

function isAdminRoute() {
  return typeof window !== "undefined" && (
    window.location.pathname === "/admin" || window.location.pathname.startsWith("/admin/")
  );
}

function preferredAuthMode() {
  if (typeof window === "undefined") return "signin";
  return new URLSearchParams(window.location.search).get("signup") === "1" ? "signup" : "signin";
}
