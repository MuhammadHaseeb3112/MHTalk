import { useEffect, useState } from "react";
import { CheckCircle2, RefreshCw, Sparkles } from "lucide-react";
import { APP_VERSION, applyUpdate, checkForUpdate, RELEASES, useAppUpdate } from "../../services/appUpdate";
import { PanelHeader, Spinner } from "../common/ui";

function ReleaseCard({ release, highlight = false }) {
  return (
    <div className={`release ${highlight ? "is-new" : ""}`}>
      <div className="release__head">
        <strong>{release.title}</strong>
        <span>
          Version {release.version}
          {release.date ? ` · ${new Date(release.date).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}` : ""}
        </span>
      </div>
      <ul>
        {release.items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

/** Settings → App update: what's new, and update when *you* want. */
export default function AppUpdateView({ onBack }) {
  const update = useAppUpdate();
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    checkForUpdate();
  }, []);
  // Releases newer than this app = what changes after updating.
  const releases = update.releases?.length ? update.releases : RELEASES;
  const index = releases.findIndex((release) => release.version === APP_VERSION);
  const incoming = index > 0 ? releases.slice(0, index) : update.available && update.latest ? [update.latest] : [];
  const history = index >= 0 ? releases.slice(index) : RELEASES;

  return (
    <section className="panel">
      <PanelHeader title="App update" onBack={onBack} variant="sub" />
      <div className="panel__scroll app-update">
        {update.available ? (
          <div className="app-update__hero is-new">
            <span className="app-update__icon"><Sparkles size={26} /></span>
            <strong>A new version is ready</strong>
            <span>
              You have version {APP_VERSION}
              {incoming[0] ? ` · new: ${incoming[0].version}` : ""}
            </span>
            <button
              type="button"
              className="btn btn--primary app-update__btn"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                applyUpdate();
              }}
            >
              {busy ? <Spinner size={18} /> : <RefreshCw size={18} />} {busy ? "Updating…" : "Update now"}
            </button>
            <small>Takes a few seconds. Your chats, messages and login stay the same.</small>
          </div>
        ) : (
          <div className="app-update__hero">
            <span className="app-update__icon is-ok"><CheckCircle2 size={26} /></span>
            <strong>MHTalk is up to date</strong>
            <span>Version {APP_VERSION}</span>
            <button type="button" className="btn btn--outline app-update__btn" disabled={update.checking} onClick={() => checkForUpdate()}>
              {update.checking ? <Spinner size={18} /> : <RefreshCw size={18} />} Check for updates
            </button>
          </div>
        )}

        {incoming.length ? (
          <>
            <div className="section-label section-label--muted">What changes after you update</div>
            {incoming.map((release) => (
              <ReleaseCard key={release.version} release={release} highlight />
            ))}
          </>
        ) : null}

        <div className="section-label section-label--muted">{update.available ? "Your current version" : "What's new in this version"}</div>
        {history.slice(0, 1).map((release) => (
          <ReleaseCard key={release.version} release={release} />
        ))}
        {history.length > 1 ? (
          <>
            <div className="section-label section-label--muted">Earlier updates</div>
            {history.slice(1).map((release) => (
              <ReleaseCard key={release.version} release={release} />
            ))}
          </>
        ) : null}
      </div>
    </section>
  );
}
