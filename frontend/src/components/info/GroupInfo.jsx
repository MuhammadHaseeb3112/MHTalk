import { useMemo, useRef, useState } from "react";
import { Bell, BellOff, Camera, Check, Eraser, Heart, HeartOff, Link2, LogOut, MessageSquare, Pencil, Settings2, ShieldCheck, ShieldOff, Star, Timer, Trash2, UserMinus, UserPlus, X } from "lucide-react";
import { errorMessage } from "../../api/client";
import { chatApi } from "../../api/endpoints";
import { favoriteRoom, muteRoom, openChatWith, refreshRoom } from "../../store/actions";
import { useStore } from "../../store/store";
import { toast } from "../../services/toast";
import { normalizeFiles } from "../../utils/files";
import { detailTime } from "../../utils/format";
import { contactsByUser, disappearingLabel, displayUserName, groupAbilities, profileName } from "../../utils/messages";
import { formatPhone } from "../../utils/phone";
import { Avatar, Menu, Modal, PanelHeader, SearchInput, Spinner, Toggle } from "../common/ui";
import { confirmAction } from "../common/dialogs";
import { useApp } from "../layout/AppContext";
import { askClearChat, askDeleteChat, askExitGroup, askMute } from "../chat-list/roomMenu";
import { MemberPicker } from "../chat-list/NewGroupPanel";
import { InfoRow, MediaSummary } from "./shared";
import { DisappearingDialog } from "../conversation/FeatureDialogs";
import { GroupPermissionsView, InviteLinkView } from "./GroupSettings";

function InlineEdit({ value, onSave, multiline, maxLength, placeholder, canEdit, className = "" }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [busy, setBusy] = useState(false);
  if (!editing) {
    return (
      <div className={`inline-edit ${className}`}>
        <span className={value ? "" : "info-muted"}>{value || placeholder}</span>
        {canEdit ? (
          <button type="button" className="icon-btn" aria-label="Edit" onClick={() => { setDraft(value); setEditing(true); }}>
            <Pencil size={17} />
          </button>
        ) : null}
      </div>
    );
  }
  const Field = multiline ? "textarea" : "input";
  return (
    <div className={`inline-edit is-editing ${className}`}>
      <Field value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={maxLength} autoFocus rows={multiline ? 3 : undefined} onKeyDown={(event) => { if (event.key === "Escape") setEditing(false); if (event.key === "Enter" && !multiline) event.currentTarget.form?.requestSubmit?.(); }} />
      <span className="inline-edit__count">{maxLength - draft.length}</span>
      <button
        type="button"
        className="icon-btn"
        aria-label="Save"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          const ok = await onSave(draft.trim());
          setBusy(false);
          if (ok !== false) setEditing(false);
        }}
      >
        {busy ? <Spinner size={16} /> : <Check size={19} />}
      </button>
    </div>
  );
}

/** Group info drawer with admin management. */
export default function GroupInfo({ roomId }) {
  const app = useApp();
  const room = useStore((state) => state.rooms[roomId]);
  const me = useStore((state) => state.me);
  const contacts = useStore((state) => state.contacts);
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  const [memberQuery, setMemberQuery] = useState("");
  const [memberMenu, setMemberMenu] = useState(null);
  const [adding, setAdding] = useState(false);
  const [addIds, setAddIds] = useState([]);
  const [addBusy, setAddBusy] = useState(false);
  const [disappearingOpen, setDisappearingOpen] = useState(false);
  const [view, setView] = useState("main"); // main | permissions | invite
  const photoRef = useRef(null);

  if (!room) return null;
  const { isAdmin, isMember, canEditInfo, canAddMembers } = groupAbilities(room, me.id);
  if (view === "permissions" && isAdmin) return <GroupPermissionsView room={room} onBack={() => setView("main")} />;
  if (view === "invite" && canAddMembers) return <InviteLinkView room={room} onBack={() => setView("main")} />;
  const creator = room.participants.find((p) => Number(p.user?.id) === Number(room.createdById))?.user;

  const members = [...room.participants]
    .sort((a, b) => {
      if (Number(a.user?.id) === Number(me.id)) return -1;
      if (Number(b.user?.id) === Number(me.id)) return 1;
      if (a.is_admin !== b.is_admin) return a.is_admin ? -1 : 1;
      return displayUserName(a.user, contactMap).localeCompare(displayUserName(b.user, contactMap));
    })
    .filter((p) => {
      const term = memberQuery.trim().toLowerCase();
      if (!term) return true;
      return displayUserName(p.user, contactMap).toLowerCase().includes(term) || String(p.user?.phone_number).includes(term);
    });

  async function save(fields) {
    try {
      await chatApi.updateGroup(room.id, fields);
      await refreshRoom(room.id);
      toast.success("Group updated");
      return true;
    } catch (error) {
      toast.error(errorMessage(error));
      return false;
    }
  }

  async function memberAction(action, participant) {
    const user = participant.user;
    const name = displayUserName(user, contactMap);
    try {
      if (action === "message") {
        const id = await openChatWith(user);
        app.openRoom(id);
      } else if (action === "admin") {
        await chatApi.setAdmin(room.id, user.id, !participant.is_admin);
        await refreshRoom(room.id);
        toast(participant.is_admin ? `${name} is no longer an admin` : `${name} is now an admin`);
      } else if (action === "remove") {
        confirmAction({
          title: `Remove ${name}?`,
          message: `${name} will be removed from "${room.groupName}".`,
          confirmLabel: "Remove",
          danger: true,
          onConfirm: async () => {
            try {
              await chatApi.removeMember(room.id, user.id);
              await refreshRoom(room.id);
            } catch (error) {
              toast.error(errorMessage(error));
            }
          },
        });
      }
    } catch (error) {
      toast.error(errorMessage(error));
    }
  }

  async function addMembers() {
    setAddBusy(true);
    try {
      await chatApi.addMembers(room.id, addIds);
      await refreshRoom(room.id);
      toast.success(`${addIds.length} member${addIds.length > 1 ? "s" : ""} added`);
      setAdding(false);
      setAddIds([]);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setAddBusy(false);
    }
  }

  return (
    <section className="panel info-panel">
      <PanelHeader title="Group info" onBack={app.closeDrawer} variant="close" />
      <div className="panel__scroll">
        <div className="info-hero">
          <div className="info-hero__photo">
            <Avatar src={room.groupPhoto} name={room.groupName} group size={200} />
            {canEditInfo ? (
              <>
                <button type="button" className="info-hero__photo-edit" onClick={() => photoRef.current?.click()}>
                  <Camera size={22} />
                  <span>Change group icon</span>
                </button>
                <input
                  ref={photoRef}
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={async (event) => {
                    const picked = event.target.files?.[0];
                    event.target.value = "";
                    if (!picked) return;
                    const [file] = await normalizeFiles([picked]);
                    if (!file.type.startsWith("image/")) toast.error("Choose an image file.");
                    else if (file.size > 5 * 1024 * 1024) toast.error("Group photos must be 5 MB or smaller.");
                    else save({ photo: file });
                  }}
                />
              </>
            ) : null}
          </div>
          {canEditInfo && room.groupPhoto ? (
            <button type="button" className="btn btn--text" onClick={() => save({ remove_photo: "true" })}>Remove photo</button>
          ) : null}
          <InlineEdit className="info-hero__name" value={room.groupName} maxLength={100} canEdit={canEditInfo} onSave={(name) => (name ? save({ name }) : (toast.error("Group name can't be empty."), false))} />
          <p className="info-hero__sub">Group · {room.participants.length} member{room.participants.length === 1 ? "" : "s"}</p>
        </div>

        <div className="info-section">
          <span className="info-label">Description</span>
          <InlineEdit value={room.description} multiline maxLength={255} placeholder={canEditInfo ? "Add group description" : "No description"} canEdit={canEditInfo} onSave={(description) => save({ description })} />
          <p className="info-muted info-created">
            Created by {creator ? displayUserName(creator, contactMap, { me }) : "a former member"}
            {room.createdAt ? `, ${detailTime(room.createdAt)}` : ""}
          </p>
        </div>

        <MediaSummary roomId={room.id} onOpen={() => app.openDrawer("media", { roomId: room.id })} />

        <div className="info-section info-section--list">
          <InfoRow icon={Star} title="Starred messages" onClick={() => app.pushPanel("starred", { roomId: room.id })} />
          {isMember ? (
            <InfoRow
              icon={Timer}
              title="Disappearing messages"
              subtitle={disappearingLabel(room.disappearingSeconds)}
              onClick={() => setDisappearingOpen(true)}
            />
          ) : null}
          <InfoRow
            icon={room.isMuted ? BellOff : Bell}
            title="Mute notifications"
            trailing={<Toggle checked={room.isMuted} label="Mute notifications" onChange={(value) => (value ? askMute(room) : muteRoom(room.id, "off"))} />}
          />
          {isAdmin ? <InfoRow icon={Settings2} title="Group permissions" onClick={() => setView("permissions")} /> : null}
        </div>

        <div className="info-section info-section--list">
          <div className="members-head">
            <span className="info-label">{room.participants.length} members</span>
          </div>
          {room.participants.length > 6 ? (
            <div className="members-search">
              <SearchInput value={memberQuery} onChange={setMemberQuery} placeholder="Search members" />
            </div>
          ) : null}
          {canAddMembers ? (
            <>
              <button type="button" className="row row--action" onClick={() => setAdding(true)}>
                <span className="row__icon-circle"><UserPlus size={20} /></span>
                <span className="row__body"><span className="row__title">Add member</span></span>
              </button>
              <button type="button" className="row row--action" onClick={() => setView("invite")}>
                <span className="row__icon-circle"><Link2 size={20} /></span>
                <span className="row__body"><span className="row__title">Invite via link</span></span>
              </button>
            </>
          ) : null}
          {members.map((participant) => {
            const user = participant.user;
            const isMe = Number(user?.id) === Number(me.id);
            const name = isMe ? "You" : displayUserName(user, contactMap);
            const saved = contactMap.has(Number(user?.id));
            return (
              <button
                key={participant.id || user?.id}
                type="button"
                className="row member-row"
                onClick={(event) => (!isMe ? setMemberMenu({ anchor: event.currentTarget, participant }) : null)}
              >
                <Avatar src={user?.profile?.profile_picture} name={name} size={40} />
                <span className="row__body">
                  <span className="row__title">
                    {name}
                    {!saved && !isMe && profileName(user) ? <span className="member-row__alias">~ {profileName(user)}</span> : null}
                  </span>
                  <span className="row__subtitle">{user?.profile?.about || formatPhone(user?.phone_number)}</span>
                </span>
                {participant.is_admin ? <span className="admin-badge">Group admin</span> : null}
              </button>
            );
          })}
        </div>

        <div className="info-section info-section--list">
          <InfoRow icon={room.isFavorite ? HeartOff : Heart} title={room.isFavorite ? "Remove from favorites" : "Add to favorites"} onClick={() => favoriteRoom(room.id, !room.isFavorite)} />
          <InfoRow icon={Eraser} title="Clear chat" danger onClick={() => askClearChat(room)} />
          {isMember ? <InfoRow icon={LogOut} title="Exit group" danger onClick={() => askExitGroup(room)} /> : null}
          <InfoRow icon={Trash2} title="Delete group for me" danger onClick={() => askDeleteChat(room, room.groupName)} />
        </div>
      </div>

      {disappearingOpen ? <DisappearingDialog room={room} canEdit={canEditInfo} onClose={() => setDisappearingOpen(false)} /> : null}
      {memberMenu ? (
        <Menu
          anchor={memberMenu.anchor}
          align="left"
          onClose={() => setMemberMenu(null)}
          items={[
            { label: `Message ${displayUserName(memberMenu.participant.user, contactMap)}`, icon: MessageSquare, onClick: () => memberAction("message", memberMenu.participant) },
            isAdmin
              ? memberMenu.participant.is_admin
                ? { label: "Dismiss as admin", icon: ShieldOff, onClick: () => memberAction("admin", memberMenu.participant) }
                : { label: "Make group admin", icon: ShieldCheck, onClick: () => memberAction("admin", memberMenu.participant) }
              : null,
            isAdmin && Number(memberMenu.participant.user?.id) !== Number(room.createdById)
              ? { label: "Remove", icon: UserMinus, danger: true, onClick: () => memberAction("remove", memberMenu.participant) }
              : null,
          ].filter(Boolean)}
        />
      ) : null}

      {adding ? (
        <Modal
          title="Add member"
          onClose={() => setAdding(false)}
          width={460}
          className="add-members"
          footer={
            <>
              <button type="button" className="btn btn--ghost" onClick={() => setAdding(false)}><X size={16} /> Cancel</button>
              <button type="button" className="btn btn--primary" disabled={!addIds.length || addBusy} onClick={addMembers}>
                {addBusy ? <Spinner size={16} /> : `Add ${addIds.length || ""}`}
              </button>
            </>
          }
        >
          <MemberPicker selected={addIds} onChange={setAddIds} exclude={room.participants.map((p) => p.user?.id)} />
        </Modal>
      ) : null}
    </section>
  );
}
