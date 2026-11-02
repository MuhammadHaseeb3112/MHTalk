import { useEffect, useState } from "react";
import { Copy, MessageSquareText, Pencil, RotateCcw, Share2, UserPlus } from "lucide-react";
import { errorMessage } from "../../api/client";
import { chatApi } from "../../api/endpoints";
import { refreshRoom } from "../../store/actions";
import { toast } from "../../services/toast";
import { Avatar, PanelHeader, Spinner, Toggle } from "../common/ui";
import { confirmAction } from "../common/dialogs";
import { InfoRow } from "./shared";

/** Absolute invite URL for this site (https://<host>/join/<code>). */
function inviteUrl(code) {
  return `${window.location.origin}/join/${code}`;
}

const PERMISSIONS = [
  {
    field: "edit_info_admins_only",
    roomKey: "editInfoAdminsOnly",
    icon: Pencil,
    title: "Edit group settings",
    subtitle: "This includes the name, icon, description and the disappearing message timer.",
  },
  { field: "send_messages_admins_only", roomKey: "sendAdminsOnly", icon: MessageSquareText, title: "Send messages" },
  { field: "add_members_admins_only", roomKey: "addMembersAdminsOnly", icon: UserPlus, title: "Add other members" },
];

/** Group info > Group permissions (admins only), WhatsApp "Members can:" toggles. */
export function GroupPermissionsView({ room, onBack }) {
  const [busy, setBusy] = useState("");

  async function change(field, membersAllowed) {
    setBusy(field);
    try {
      await chatApi.setGroupPermissions(room.id, { [field]: !membersAllowed });
      await refreshRoom(room.id);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="panel info-panel">
      <PanelHeader title="Group permissions" onBack={onBack} variant="sub" />
      <div className="panel__scroll">
        <div className="info-section info-section--list">
          <span className="info-label">Members can:</span>
          {PERMISSIONS.map((item) => {
            const membersAllowed = !room[item.roomKey];
            return (
              <InfoRow
                key={item.field}
                icon={item.icon}
                title={item.title}
                subtitle={item.subtitle}
                trailing={
                  busy === item.field ? (
                    <Spinner size={18} />
                  ) : (
                    <Toggle checked={membersAllowed} label={item.title} onChange={(value) => change(item.field, value)} />
                  )
                }
              />
            );
          })}
        </div>
        <p className="info-muted info-pad">Admins can always do all of these.</p>
      </div>
    </section>
  );
}

/** Group info > Invite via link: copy, share and reset the group's invite link. */
export function InviteLinkView({ room, onBack }) {
  const [link, setLink] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    chatApi
      .inviteLink(room.id)
      .then((data) => !cancelled && setLink(inviteUrl(data.code)))
      .catch((err) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [room.id]);

  const copy = () =>
    navigator.clipboard?.writeText(link).then(
      () => toast("Link copied"),
      () => toast.error("Couldn't copy the link."),
    );

  const share = async () => {
    if (!navigator.share) {
      copy();
      return;
    }
    try {
      await navigator.share({ title: room.groupName, text: `Follow this link to join my MHTalk group: ${room.groupName}`, url: link });
    } catch {
      /* share sheet dismissed */
    }
  };

  const reset = () =>
    confirmAction({
      title: "Reset link?",
      message: "If you reset the link, no one will be able to use it to join this group.",
      confirmLabel: "Reset link",
      danger: true,
      onConfirm: async () => {
        try {
          const data = await chatApi.resetInviteLink(room.id);
          setLink(inviteUrl(data.code));
          toast("Invite link was reset");
        } catch (err) {
          toast.error(errorMessage(err));
        }
      },
    });

  return (
    <section className="panel info-panel">
      <PanelHeader title="Invite via link" onBack={onBack} variant="sub" />
      <div className="panel__scroll">
        <div className="invite-link">
          <Avatar src={room.groupPhoto} name={room.groupName} group size={56} />
          <div className="invite-link__body">
            <span className="invite-link__name">{room.groupName}</span>
            {link ? (
              <a className="invite-link__url" href={link} onClick={(event) => event.preventDefault()}>{link}</a>
            ) : error ? (
              <span className="info-muted">{error}</span>
            ) : (
              <Spinner size={18} />
            )}
          </div>
        </div>
        <p className="info-muted info-pad">
          Anyone with MHTalk can follow this link to join this group. Only share it with people you trust.
        </p>
        <div className="info-section info-section--list">
          <InfoRow icon={Copy} title="Copy link" onClick={link ? copy : undefined} />
          <InfoRow icon={Share2} title="Share link" onClick={link ? share : undefined} />
          <InfoRow icon={RotateCcw} title="Reset link" danger onClick={link ? reset : undefined} />
        </div>
      </div>
    </section>
  );
}
