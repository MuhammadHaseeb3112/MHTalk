import { useMemo } from "react";
import { Phone, Video } from "lucide-react";
import { useStore } from "../../store/store";
import { contactsByUser, displayUserName } from "../../utils/messages";
import { useCalls } from "./callContext";
import { joinedIn } from "./groupCall";

/**
 * Green bar at the top of a group chat while the group has a call going:
 * "Ongoing voice call · Alice, Bob" + Join (or Return when minimized).
 */
export default function GroupCallBanner({ room }) {
  const activeCall = useStore((state) => state.activeCalls?.[room.id]);
  const contacts = useStore((state) => state.contacts);
  const me = useStore((state) => state.me);
  const { call, joinCall } = useCalls();
  const contactMap = useMemo(() => contactsByUser(contacts), [contacts]);
  if (!room.isGroup || !activeCall) return null;
  if (!room.participants.some((p) => Number(p.user?.id) === Number(me.id))) return null;

  const mine = call.group && Number(call.callId) === Number(activeCall.id) && !["idle", "incoming", "ended"].includes(call.phase);
  if (mine && !call.minimized) return null;

  const video = activeCall.call_type === "VIDEO";
  const joined = joinedIn(activeCall);
  const names = joined.map((p) => displayUserName(p.user, contactMap, { me })).join(", ");
  const Icon = video ? Video : Phone;
  return (
    <div className="gcall-banner" role="region" aria-label="Ongoing group call">
      <span className="gcall-banner__icon">
        <Icon size={17} />
      </span>
      <span className="gcall-banner__text">
        <strong>Ongoing {video ? "video" : "voice"} call</strong>
        <span>
          {joined.length} in call{names ? ` · ${names}` : ""}
        </span>
      </span>
      <button type="button" className="gcall-join" onClick={() => joinCall(room.id)}>
        {mine ? "Return" : "Join"}
      </button>
    </div>
  );
}
