export function getApiBaseUrl() {
  return import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
}

export function getStaticApiToken() {
  return import.meta.env.VITE_API_TOKEN || "";
}

export function getClerkPublishableKey() {
  return import.meta.env.VITE_CLERK_PUBLISHABLE_KEY || "";
}

export function isAuthDisabled() {
  return import.meta.env.DEV && import.meta.env.VITE_DISABLE_AUTH === "true";
}
