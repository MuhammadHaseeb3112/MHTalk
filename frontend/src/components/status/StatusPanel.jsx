import { useEffect, useMemo, useRef, useState } from "react";
import { Image as ImageIcon, Lock, MoreVertical, Pencil, Plus } from "lucide-react";
import { useStore } from "../../store/store";
import { toast } from "../../services/toast";
import { detailTime } from "../../utils/format";
import { contactsByUser, displayUserName } from "../../utils/messages";
import { Avatar, EmptyState, IconButton, Menu, MenuButton, PanelHeader, Spinner } from "../common/ui";
import { normalizeFiles, validateFiles } from "../../utils/files";
import { useMediaQuery } from "../../hooks";
import StatusComposer from "./StatusComposer";
import StatusViewer from "./StatusViewer";
import { getStatusPrivacy, setStatusPrivacy } from "./statusPrefs";
import StatusPrivacyEditor from "./StatusPrivacyEditor";

function PrivacyView({ onBack }) {
  const me = useStore((state) => state.me);
  const [value, setValue] = useState(() => getStatusPrivacy(me.id));
  const update = (next) => {
    setValue(next);
    setStatusPrivacy(me.id, next);
  };

  return (
    <section className="panel">
      <PanelHeader title="Status privacy" onBack={onBack} variant="sub" />
      <div className="panel__scroll">
        <StatusPrivacyEditor value={value} onChange={update} />
        <p className="info-muted info-pad">
          <Lock size={12} /> Changes to your privacy settings won't affect status updates that you've sent already.
        </p>
      </div>
    </section>
  );
}

export default function StatusPanel() {
  const compact = useMediaQuery("(max-width: 900px)");
  const me = useStore((state) => state.me);
  const feed = useStore((state) => state.statusFeed);
  const mine = useStore((state) => state.myStatuses);
  const loaded = useStore((state) => state.statusLoaded);
  const contacts = useStore((state) => state.contacts);
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  const [view, setView] = useState("list");
  const [viewer, setViewer] = useState(null); // { groups, start }
  const [composer, setComposer] = useState(null); // { mode, file }
  const [addAnchor, setAddAnchor] = useState(null);
  const fileRef = useRef(null);

  useEffect(() => {
    const handler = (event) => {
      if (event.detail === "text") setComposer({ mode: "text" });
      else fileRef.current?.click();
    };
    window.addEventListener("mhtalk:new-status", handler);
    return () => window.removeEventListener("mhtalk:new-status", handler);
  }, []);

  const recent = feed.filter((group) => group.unseen_count > 0);
  const viewed = feed.filter((group) => !group.unseen_count);
  const sortByLatest = (a, b) => new Date(b.statuses[0]?.created_at || 0) - new Date(a.statuses[0]?.created_at || 0);
  recent.sort(sortByLatest);
  viewed.sort(sortByLatest);

  const myGroup = mine.length ? { user: me, statuses: [...mine].sort((a, b) => new Date(a.created_at) - new Date(b.created_at)).map((s) => ({ ...s, is_viewed: true })), unseen_count: 0 } : null;

  const openGroup = (list, index) => {
    const groups = list.map((group) => ({ ...group, statuses: [...group.statuses].sort((a, b) => new Date(a.created_at) - new Date(b.created_at)) }));
    setViewer({ groups, start: index });
  };

  if (view === "privacy") return <PrivacyView onBack={() => setView("list")} />;

  const addItems = [
    { label: "Photos & videos", icon: ImageIcon, onClick: () => fileRef.current?.click() },
    { label: "Text", icon: Pencil, onClick: () => setComposer({ mode: "text" }) },
  ];

  return (
    <section className="panel status-panel">
      <PanelHeader
        title={compact ? "Updates" : "Status"}
        actions={
          <>
            <IconButton icon={Plus} label="Add status" onClick={(event) => setAddAnchor(event.currentTarget)} />
            <MenuButton icon={MoreVertical} label="Menu" items={[{ label: "Status privacy", icon: Lock, onClick: () => setView("privacy") }]} />
          </>
        }
      />
      <div className="panel__scroll">
        <div className="list-pad">
          <div className="row status-row">
            <button type="button" className="status-row__avatar" onClick={() => (myGroup ? openGroup([myGroup], 0) : fileRef.current?.click())} aria-label="My status">
              <Avatar src={me.profile?.profile_picture} name={me.profile?.display_name} size={46} ring={myGroup ? "seen" : undefined} />
              {!myGroup ? <span className="status-row__plus"><Plus size={14} strokeWidth={3} /></span> : null}
            </button>
            <button type="button" className="row__body status-row__body" onClick={() => (myGroup ? openGroup([myGroup], 0) : fileRef.current?.click())}>
              <span className="row__title">My status</span>
              <span className="row__subtitle">{myGroup ? `${mine.length} update${mine.length > 1 ? "s" : ""} · ${detailTime(mine[0]?.created_at)}` : "Click to add status update"}</span>
            </button>
          </div>
        </div>

        {!loaded ? <div className="list-loading"><Spinner /></div> : null}

        {recent.length ? <div className="section-label section-label--plain">Recent</div> : null}
        <div className="list-pad">
          {recent.map((group, index) => (
            <button key={group.user.id} type="button" className="row status-row" onClick={() => openGroup(recent, index)}>
              <Avatar src={group.user.profile?.profile_picture} name={displayUserName(group.user, contactMap)} size={46} ring="new" />
              <span className="row__body">
                <span className="row__title">{displayUserName(group.user, contactMap)}</span>
                <span className="row__subtitle">{detailTime(group.statuses[0]?.created_at)}</span>
              </span>
            </button>
          ))}
        </div>

        {viewed.length ? <div className="section-label section-label--plain">Viewed</div> : null}
        <div className="list-pad">
          {viewed.map((group, index) => (
            <button key={group.user.id} type="button" className="row status-row" onClick={() => openGroup(viewed, index)}>
              <Avatar src={group.user.profile?.profile_picture} name={displayUserName(group.user, contactMap)} size={46} ring="seen" />
              <span className="row__body">
                <span className="row__title">{displayUserName(group.user, contactMap)}</span>
                <span className="row__subtitle">{detailTime(group.statuses[0]?.created_at)}</span>
              </span>
            </button>
          ))}
        </div>

        {loaded && !feed.length ? (
          <EmptyState text="No status updates from your contacts yet. Status updates disappear after 24 hours." />
        ) : null}
        <p className="info-muted info-pad status-foot"><Lock size={12} /> Status updates are only shown to the audience you choose.</p>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept="image/*,video/*"
        hidden
        onChange={async (event) => {
          const picked = [...(event.target.files || [])];
          event.target.value = "";
          const [file] = validateFiles(await normalizeFiles(picked), "media");
          if (!file) return;
          if (file.size > 50 * 1024 * 1024) {
            toast.error("Status media must be 50 MB or smaller.");
            return;
          }
          setComposer({ mode: "media", file });
        }}
      />
      {addAnchor ? <Menu anchor={addAnchor} items={addItems} onClose={() => setAddAnchor(null)} /> : null}
      {composer ? <StatusComposer mode={composer.mode} initialFile={composer.file} onClose={() => setComposer(null)} /> : null}
      {viewer ? <StatusViewer groups={viewer.groups} startGroup={viewer.start} onClose={() => setViewer(null)} /> : null}
    </section>
  );
}
