/** Ask the CallProvider to join the room's ongoing group call (works from any component). */
export function requestJoinCall(roomId) {
  window.dispatchEvent(new CustomEvent("mhtalk:join-call", { detail: { roomId: Number(roomId) } }));
}

/** People currently in an active call (serialized by the calls API). */
export function joinedIn(activeCall) {
  return (activeCall?.participants || []).filter((p) => p.state === "JOINED" && !p.left_at);
}
