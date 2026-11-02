import { useCallback } from "react";
import { Archive } from "lucide-react";
import { useStore } from "../../store/store";
import { EmptyState, PanelHeader } from "../common/ui";
import { useApp } from "../layout/AppContext";
import ChatListItem from "./ChatListItem";
import { useChatList } from "./useChatList";

/**
 * Archived chats. Opening this view does NOT mark anything read; each chat
 * keeps its own unread badge until it is opened.
 */
export default function ArchivedPanel() {
  const app = useApp();
  const rows = useChatList({ archived: true });
  const me = useStore((state) => state.me);
  const activeRoomId = useStore((state) => state.activeRoomId);
  const noop = useCallback(() => {}, []);

  return (
    <section className="panel">
      <PanelHeader title="Archived" onBack={app.popPanel} variant="sub" />
      <div className="panel__scroll">
        <p className="archived-note">These chats stay archived when new messages are received.</p>
        <div className="list-pad">
          {rows.map(({ room, title, senderName, preview, reacted, typingText }) => (
            <ChatListItem
              key={room.id}
              room={room}
              title={title}
              me={me}
              senderName={senderName}
              preview={preview}
              reacted={reacted}
              typingText={typingText}
              active={room.id === activeRoomId}
              selectMode={false}
              selected={false}
              onOpen={app.openRoom}
              onToggleSelect={noop}
            />
          ))}
        </div>
        {!rows.length ? <EmptyState icon={Archive} title="No archived chats" text="Archive a chat from its menu to keep your list tidy." /> : null}
      </div>
    </section>
  );
}
