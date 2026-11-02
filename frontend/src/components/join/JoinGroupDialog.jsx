import { useEffect, useState } from "react";
import { errorMessage } from "../../api/client";
import { chatApi } from "../../api/endpoints";
import { navigate } from "../../router";
import { loadRooms } from "../../store/actions";
import { toast } from "../../services/toast";
import { Avatar, Modal, Spinner } from "../common/ui";

/** "Alice, Bob, You and 3 others" style summary of the preview names. */
function memberSummary(names, total) {
  if (!names.length) return "";
  const rest = total - names.length;
  return rest > 0 ? `${names.join(", ")} and ${rest} other${rest === 1 ? "" : "s"}` : names.join(", ");
}

/**
 * /join/<code>: preview of a group invite link with "Join group" (or
 * "Open chat" when already a member). Shown over the app, like WhatsApp Web.
 */
export default function JoinGroupDialog({ code }) {
  const [state, setState] = useState({ loading: true, preview: null, error: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    chatApi
      .invitePreview(code)
      .then((preview) => !cancelled && setState({ loading: false, preview, error: "" }))
      .catch((error) => !cancelled && setState({ loading: false, preview: null, error: errorMessage(error, "This invite link is invalid or has been reset.") }));
    return () => {
      cancelled = true;
    };
  }, [code]);

  const close = () => navigate("/", { replace: true });

  const openRoom = async (roomId) => {
    await loadRooms().catch(() => {});
    navigate("/", { replace: true });
    window.dispatchEvent(new CustomEvent("mhtalk:open-room", { detail: Number(roomId) }));
  };

  const join = async () => {
    setBusy(true);
    try {
      const result = await chatApi.joinViaInvite(code);
      await openRoom(result.room_id);
    } catch (error) {
      toast.error(errorMessage(error));
      setBusy(false);
    }
  };

  const { loading, preview, error } = state;
  return (
    <Modal
      title={preview ? "" : "Group invite"}
      onClose={busy ? undefined : close}
      width={400}
      className="join-group"
      footer={
        preview ? (
          <>
            <button type="button" className="btn btn--ghost" onClick={close} disabled={busy}>Cancel</button>
            <button type="button" className="btn btn--primary" onClick={preview.is_member ? () => openRoom(preview.room_id) : join} disabled={busy}>
              {busy ? <Spinner size={16} /> : preview.is_member ? "Open chat" : "Join group"}
            </button>
          </>
        ) : !loading ? (
          <button type="button" className="btn btn--primary" onClick={close}>OK</button>
        ) : null
      }
    >
      {loading ? (
        <div className="join-group__loading"><Spinner /></div>
      ) : preview ? (
        <div className="join-group__preview">
          <Avatar src={preview.photo} name={preview.name} group size={96} />
          <h2 className="join-group__name">{preview.name}</h2>
          <p className="join-group__meta">Group · {preview.participants_count} member{preview.participants_count === 1 ? "" : "s"}</p>
          {preview.member_names?.length ? (
            <p className="join-group__members">{memberSummary(preview.member_names, preview.participants_count)}</p>
          ) : null}
          {preview.is_member ? <p className="join-group__members">You're already a member of this group.</p> : null}
        </div>
      ) : (
        <p className="modal__text">{error}</p>
      )}
    </Modal>
  );
}
