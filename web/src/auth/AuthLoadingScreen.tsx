export function AuthLoadingScreen({ label = "Loading" }: { label?: string }) {
  return (
    <main className="auth-loading-screen" aria-busy="true" aria-live="polite">
      <div className="loading-indicator">
        <span className="sl-spin" />
        {label}
      </div>
    </main>
  );
}
