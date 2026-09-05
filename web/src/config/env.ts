export function getApiBaseUrl() {
  return localStorage.getItem("apiBaseUrl") || import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
}

export function getStaticApiToken() {
  return import.meta.env.VITE_API_TOKEN || "";
}

export function getClerkPublishableKey() {
  return import.meta.env.VITE_CLERK_PUBLISHABLE_KEY || "";
}
