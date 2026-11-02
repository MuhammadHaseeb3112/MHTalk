import { useEffect, useMemo, useState } from "react";
import { errorMessage } from "../../api/client";
import { messageApi } from "../../api/endpoints";
import { useDebouncedValue } from "../../hooks";
import { useStore } from "../../store/store";
import { listTime } from "../../utils/format";
import { contactsByUser, displayUserName } from "../../utils/messages";
import { EmptyState, PanelHeader, SearchInput } from "../common/ui";
import { useApp } from "../layout/AppContext";
import { RichText } from "../messages/MessageBubble";

/** Search within the open conversation; clicking a hit scrolls to it. */
export default function SearchMessages({ roomId }) {
  const app = useApp();
  const me = useStore((state) => state.me);
  const contacts = useStore((state) => state.contacts);
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  const [query, setQuery] = useState("");
  const debounced = useDebouncedValue(query, 300);
  const term = debounced.trim();
  const [result, setResult] = useState({ term: "", rows: [], error: "" });

  useEffect(() => {
    if (!term) return undefined;
    let cancelled = false;
    messageApi
      .search(roomId, term)
      .then((rows) => !cancelled && setResult({ term, rows: rows.filter((row) => !String(row.content || "").startsWith("__WHATSUP_")), error: "" }))
      .catch((err) => !cancelled && setResult({ term, rows: [], error: errorMessage(err) }));
    return () => {
      cancelled = true;
    };
  }, [term, roomId]);

  const ready = term && result.term === term;
  const results = ready ? result.rows : null;
  const error = ready ? result.error : "";
  const loading = Boolean(term) && !ready;

  return (
    <section className="panel info-panel">
      <PanelHeader title="Search messages" onBack={app.closeDrawer} variant="close" />
      <SearchInput value={query} onChange={setQuery} placeholder="Search..." autoFocus loading={loading} />
      <div className="panel__scroll">
        {!debounced.trim() ? <p className="info-muted info-pad search-hint">Search for messages in this chat.</p> : null}
        {error ? <EmptyState text={error} /> : null}
        {results && !results.length && !loading ? <EmptyState text="No messages found" /> : null}
        <div className="list-pad">
          {results?.map((row) => (
            <button
              key={row.id}
              type="button"
              className="row search-hit-row"
              onClick={() => window.dispatchEvent(new CustomEvent("whatsup:jump-to", { detail: row.id }))}
            >
              <span className="row__body">
                <span className="row__title row__title--small">
                  {displayUserName(row.sender, contactMap, { me })}
                  <span className="row__time">{listTime(row.created_at)}</span>
                </span>
                <span className="row__subtitle row__subtitle--wrap">
                  <RichText text={row.content || row.attachments?.[0]?.file_name || ""} query={debounced.trim()} />
                </span>
              </span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
