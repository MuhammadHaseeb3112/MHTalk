import { Component } from "react";

const CHUNK_ERROR = /dynamically imported module|Loading chunk|Importing a module script failed|error loading dynamically/i;
const RELOAD_KEY = "mhtalk_chunk_reload_at";

/** Remove the offline copy of the app (service worker + its caches). */
async function resetAppCache() {
  try {
    const registrations = (await navigator.serviceWorker?.getRegistrations?.()) || [];
    await Promise.all(registrations.map((registration) => registration.unregister()));
    const keys = (await window.caches?.keys?.()) || [];
    await Promise.all(keys.map((key) => window.caches.delete(key)));
  } catch {
    /* nothing cached */
  }
}

/**
 * Instead of a blank (black) screen when something breaks while the app
 * starts, show what went wrong with "Reload" and "Reset app".
 * After a new deploy an old cached page may ask for files that no longer
 * exist — that case reloads itself once with fresh files.
 */
export default class AppErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null, busy: false };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error) {
    const message = String(error?.message || error);
    let last = 0;
    try {
      last = Number(sessionStorage.getItem(RELOAD_KEY) || 0);
    } catch {
      /* ignore */
    }
    if (CHUNK_ERROR.test(message) && Date.now() - last > 30000) {
      try {
        sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
      } catch {
        /* ignore */
      }
      resetAppCache().then(() => window.location.reload());
    }
  }

  render() {
    const { error, busy } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="app-crash">
        <img src="/pwa-192.png" alt="" width="64" height="64" />
        <h1>MHTalk couldn't start</h1>
        <p>Something went wrong while opening the app. Reloading usually fixes it.</p>
        <code>{String(error?.message || error).slice(0, 300)}</code>
        <div className="app-crash__actions">
          <button type="button" onClick={() => window.location.reload()}>Reload</button>
          <button
            type="button"
            className="is-secondary"
            disabled={busy}
            onClick={async () => {
              this.setState({ busy: true });
              await resetAppCache();
              window.location.reload();
            }}
          >
            {busy ? "Resetting…" : "Reset app"}
          </button>
        </div>
      </div>
    );
  }
}
