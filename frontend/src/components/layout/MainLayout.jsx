import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";
import { useMediaQuery } from "../../hooks";
import { realtime } from "../../services/realtime";
import { setTitleBadge } from "../../services/notify";
import { consumeLaunchRoom } from "../../services/pwa";
import { acknowledgeMissedCalls, loadCalls, loadMessages, loadStatus, markRoomRead, setActiveRoom } from "../../store/actions";
import { getState, useStore } from "../../store/store";
import NavRail from "../navigation/NavRail";
import ChatListPanel from "../chat-list/ChatListPanel";
import ArchivedPanel from "../chat-list/ArchivedPanel";
import NewChatPanel from "../chat-list/NewChatPanel";
import NewContactPanel from "../chat-list/NewContactPanel";
import NewGroupPanel from "../chat-list/NewGroupPanel";
import Conversation from "../conversation/Conversation";
import SearchMessages from "../info/SearchMessages";
import { CallProvider } from "../calls/CallManager";
import { AppContext } from "./AppContext";
import IntroPane from "./IntroPane";
import { Spinner } from "../common/ui";

// Less-used screens load on demand to keep the first download small.
const StatusPanel = lazy(() => import("../status/StatusPanel"));
const StatusMain = lazy(() => import("../status/StatusMain"));
const CallsPanel = lazy(() => import("../calls/CallsPanel"));
const CallsMain = lazy(() => import("../calls/CallsMain"));
const AssistantPanel = lazy(() => import("../assistant/AssistantPanel"));
const AssistantChat = lazy(() => import("../assistant/AssistantChat"));
const AllMediaDialog = lazy(() => import("../media/AllMediaDialog"));
const ContactsPanel = lazy(() => import("../contacts/ContactsPanel"));
const ProfilePanel = lazy(() => import("../profile/ProfilePanel"));
const SettingsPanel = lazy(() => import("../profile/SettingsPanel"));
const ContactInfo = lazy(() => import("../info/ContactInfo"));
const GroupInfo = lazy(() => import("../info/GroupInfo"));
const MessageInfo = lazy(() => import("../info/MessageInfo"));
const SharedMedia = lazy(() => import("../info/SharedMedia"));
const StarredPanel = lazy(() => import("../chat-list/StarredPanel"));

const fallback = <div className="panel panel--loading"><Spinner /></div>;

const PANELS = {
  archived: ArchivedPanel,
  newChat: NewChatPanel,
  newContact: NewContactPanel,
  newGroup: NewGroupPanel,
  starred: StarredPanel,
};

const SECTION_PANELS = {
  chats: ChatListPanel,
  status: StatusPanel,
  calls: CallsPanel,
  contacts: ContactsPanel,
  profile: ProfilePanel,
  settings: SettingsPanel,
  ai: AssistantPanel,
};

const DRAWERS = {
  contact: ContactInfo,
  group: GroupInfo,
  messageInfo: MessageInfo,
  search: SearchMessages,
  media: SharedMedia,
};

export default function MainLayout({ onLogout }) {
  const [section, setSectionState] = useState("chats");
  const [stack, setStack] = useState([]);
  const [drawer, setDrawer] = useState(null);
  const [mediaOpen, setMediaOpen] = useState(false);
  const activeRoomId = useStore((state) => state.activeRoomId);
  const activeExists = useStore((state) => Boolean(state.activeRoomId && state.rooms[state.activeRoomId]));
  const totalUnread = useStore((state) => Object.values(state.rooms).filter((room) => !room.isArchived && room.unread > 0).length);
  const compact = useMediaQuery("(max-width: 900px)");

  useEffect(() => setTitleBadge(totalUnread), [totalUnread]);

  const pushPanel = useCallback((name, props = {}) => setStack((current) => [...current, { name, props }]), []);
  const popPanel = useCallback(() => setStack((current) => current.slice(0, -1)), []);
  const resetPanels = useCallback(() => setStack([]), []);
  const openDrawer = useCallback((type, payload = {}) => setDrawer({ type, payload }), []);
  const closeDrawer = useCallback(() => setDrawer(null), []);

  const setSection = useCallback((next) => {
    setSectionState(next);
    setStack([]);
    if (next === "calls") {
      loadCalls().then(acknowledgeMissedCalls);
    }
    if (next === "status") loadStatus();
  }, []);

  const openRoom = useCallback(
    (roomId) => {
      if (!roomId) return;
      const state = getState();
      setActiveRoom(roomId);
      realtime.openRoom(roomId);
      if (!state.messages[roomId]?.loaded) loadMessages(roomId);
      markRoomRead(roomId, { immediate: true });
      setDrawer((current) => (current && current.payload?.roomId === roomId ? current : null));
      if (!["chats"].includes(section)) setSectionState("chats");
      setStack((current) => current.filter((panel) => panel.name === "archived"));
    },
    [section],
  );

  const closeRoom = useCallback(() => {
    setActiveRoom(null);
    realtime.openRoom(null);
    setDrawer(null);
  }, []);

  // Desktop notifications deep-link into a chat.
  useEffect(() => {
    const handler = (event) => openRoom(Number(event.detail));
    window.addEventListener("whatsup:open-room", handler);
    return () => window.removeEventListener("whatsup:open-room", handler);
  }, [openRoom]);

  // Opened from a push notification (/?room=12): jump straight into that chat.
  useEffect(() => {
    const roomId = consumeLaunchRoom();
    // Deferred so the listener above is attached (and survives StrictMode re-runs).
    if (roomId) window.setTimeout(() => window.dispatchEvent(new CustomEvent("whatsup:open-room", { detail: roomId })), 0);
  }, []);

  // Mark the open chat read again when the tab becomes visible.
  useEffect(() => {
    const onVisible = () => {
      const roomId = getState().activeRoomId;
      if (document.visibilityState === "visible" && roomId && getState().rooms[roomId]?.unread) markRoomRead(roomId);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  // Ctrl+Alt+N new chat, Escape closes the drawer / chat.
  useEffect(() => {
    const onKey = (event) => {
      if (event.ctrlKey && event.altKey && event.key.toLowerCase() === "n") {
        event.preventDefault();
        setSectionState("chats");
        setStack([{ name: "newChat", props: {} }]);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const openMedia = useCallback(() => setMediaOpen(true), []);

  const app = useMemo(
    () => ({ openRoom, closeRoom, setSection, pushPanel, popPanel, resetPanels, openDrawer, closeDrawer, openMedia, onLogout, section, compact }),
    [openRoom, closeRoom, setSection, pushPanel, popPanel, resetPanels, openDrawer, closeDrawer, openMedia, onLogout, section, compact],
  );

  const SectionPanel = SECTION_PANELS[section] || ChatListPanel;
  const top = stack[stack.length - 1];
  const OverlayPanel = top ? PANELS[top.name] : null;
  const Drawer = drawer ? DRAWERS[drawer.type] : null;

  const showChat = section === "chats" && activeRoomId && activeExists;
  let main;
  if (section === "status") main = <StatusMain />;
  else if (section === "calls") main = <CallsMain />;
  else if (section === "ai") main = <AssistantChat />;
  else if (showChat) main = <Conversation key={activeRoomId} roomId={activeRoomId} />;
  else
    main = (
      <IntroPane
        onNewChat={() => { setSectionState("chats"); setStack([{ name: "newChat", props: {} }]); }}
        onNewContact={() => { setSectionState("chats"); setStack([{ name: "newContact", props: {} }]); }}
        onCalls={() => setSection("calls")}
      />
    );

  const mobileShowsMain = compact && (showChat || section === "ai");

  return (
    <AppContext.Provider value={app}>
      <CallProvider>
        <div className={`app ${drawer ? "has-drawer" : ""} ${mobileShowsMain ? "is-mobile-main" : ""}`}>
          <NavRail section={section} onChange={setSection} onOpenMedia={openMedia} />
          <aside className="sidebar">
            <div className="sidebar__stack">
              <Suspense fallback={fallback}><SectionPanel key={section} /></Suspense>
              {OverlayPanel ? (
                <div className="sidebar__overlay" key={`${top.name}-${stack.length}`}>
                  <Suspense fallback={fallback}><OverlayPanel {...top.props} /></Suspense>
                </div>
              ) : null}
            </div>
          </aside>
          <main className="main"><Suspense fallback={fallback}>{main}</Suspense></main>
          {Drawer && showChat ? (
            <aside className="drawer" key={drawer.type}>
              <Suspense fallback={fallback}><Drawer {...drawer.payload} /></Suspense>
            </aside>
          ) : null}
        </div>
        {mediaOpen ? (
          <Suspense fallback={null}>
            <AllMediaDialog onClose={() => setMediaOpen(false)} onOpenRoom={openRoom} />
          </Suspense>
        ) : null}
      </CallProvider>
    </AppContext.Provider>
  );
}
