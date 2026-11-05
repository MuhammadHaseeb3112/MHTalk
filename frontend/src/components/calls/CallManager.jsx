import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CallContext } from "./callContext";
import { errorMessage } from "../../api/client";
import { callApi } from "../../api/endpoints";
import { ManagedSocket } from "../../services/realtime";
import { showDesktopNotification } from "../../services/notify";
import { loopSound, preloadSounds } from "../../services/sounds";
import { toast } from "../../services/toast";
import { loadCalls } from "../../store/actions";
import { dispatch, getState } from "../../store/store";
import { contactsByUser, displayUserName } from "../../utils/messages";
import CallOverlay from "./CallOverlay";

/**
 * WebRTC calls (audio/video): one-to-one and group (mesh).
 *
 * Signaling flow (matches apps/calls/consumers.py):
 *   caller: open ws/calls/<room>/ → POST calls/start/ → callee gets
 *   `incoming_call` on ws/calls/inbox/ → callee opens ws/calls/<room>/,
 *   POST accept + `accept_call` → caller sends `offer` → callee `answer` →
 *   both exchange `ice_candidate` → media flows peer-to-peer.
 * Ending: `end_call` + POST calls/<id>/end/ (server writes the call card).
 *
 * Group calls (apps/calls/group.py) are a mesh: one RTCPeerConnection per
 * other participant. Joining is POST calls/<id>/accept/, which returns who is
 * already in the call; the joiner sends an offer to each of them (the person
 * who joined later always offers, so two peers never offer to each other).
 * The server stamps every relayed offer/answer/ICE with `from`, so each one
 * is routed to the right peer connection. Join/leave/decline/missed arrive
 * as `member_*` events on the call socket; leaving is POST calls/<id>/end/.
 *
 * ICE servers come from the backend (/api/calls/ice-servers/), which adds a
 * TURN relay with short-lived credentials when the server has one
 * configured. VITE_TURN_URL/USER/PASS still work as a local fallback.
 */

const FALLBACK_ICE = [{ urls: ["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"] }];
let iceCache = { servers: null, expiresAt: 0 };

function fallbackIceServers() {
  const servers = [...FALLBACK_ICE];
  const turn = import.meta.env.VITE_TURN_URL;
  if (turn) servers.push({ urls: turn, username: import.meta.env.VITE_TURN_USER, credential: import.meta.env.VITE_TURN_PASS });
  return servers;
}

/** Fetch (and cache until shortly before expiry) the ICE server list. */
async function refreshIceServers() {
  if (iceCache.servers && Date.now() < iceCache.expiresAt) return iceCache.servers;
  try {
    const data = await callApi.iceServers();
    const servers = Array.isArray(data?.ice_servers) && data.ice_servers.length ? data.ice_servers : fallbackIceServers();
    const ttl = Math.max(60, Number(data?.ttl) || 3600);
    iceCache = { servers, expiresAt: Date.now() + (ttl - 60) * 1000 };
  } catch {
    iceCache = { servers: fallbackIceServers(), expiresAt: Date.now() + 60 * 1000 };
  }
  return iceCache.servers;
}

function iceServers() {
  if (!iceCache.servers || Date.now() >= iceCache.expiresAt) refreshIceServers();
  return iceCache.servers || fallbackIceServers();
}

// Incoming call: ringtone. Outgoing call: "ring-ring" until they answer.
function createTone(kind) {
  return loopSound(kind === "incoming" ? "ringtone" : "ringback");
}

const IDLE = { phase: "idle" };

const MEMBER_STATE = { JOINED: "joined", RINGING: "ringing", DECLINED: "declined", MISSED: "missed", LEFT: "left" };

/** `{ userId: { state, muted, cameraOff } }` for everyone but me, from a serialized call. */
function membersFrom(participants, meId, type) {
  const members = {};
  (participants || []).forEach((row) => {
    const id = Number(row.user?.id ?? row.user);
    if (!id || id === Number(meId)) return;
    const state = row.left_at && row.state === "JOINED" ? "left" : MEMBER_STATE[row.state] || "ringing";
    members[id] = { state, muted: Boolean(row.is_muted), cameraOff: type !== "video", connected: false };
  });
  return members;
}

const typeOf = (callType) => (String(callType).toUpperCase() === "VIDEO" ? "video" : "audio");

export function CallProvider({ children }) {
  const [call, setCall] = useState(IDLE);
  const [localStream, setLocalStream] = useState(null);
  const [remoteStreams, setRemoteStreams] = useState({}); // userId -> MediaStream
  const [shareStream, setShareStream] = useState(null);
  const [reactions, setReactions] = useState([]);
  const shareRef = useRef(null);
  const sessionRef = useRef(null); // { callId, roomId, targetId, initiator, type, group }
  const roomSocketRef = useRef(null);
  const peersRef = useRef(new Map()); // userId -> RTCPeerConnection
  const remoteRef = useRef(new Map()); // userId -> MediaStream (tracks received so far)
  const pendingIce = useRef(new Map()); // userId -> ICE candidates that arrived before the offer/answer
  const localRef = useRef(null);
  const toneRef = useRef(null);
  const handleSignalRef = useRef(null);
  const acceptRef = useRef(null); // latest accept(), for joinCall() from a banner

  useEffect(() => preloadSounds(), []);

  const stopTone = useCallback(() => {
    toneRef.current?.stop();
    toneRef.current = null;
  }, []);
  const playTone = useCallback(
    (kind) => {
      stopTone();
      toneRef.current = createTone(kind);
      toneRef.current.start();
    },
    [stopTone],
  );

  const setMember = useCallback((userId, patch) => {
    setCall((current) => {
      if (!current.group) return current;
      const id = Number(userId);
      const previous = current.members?.[id] || { state: "joined", muted: false, cameraOff: current.type !== "video", connected: false };
      return { ...current, members: { ...current.members, [id]: { ...previous, ...patch } } };
    });
  }, []);

  const removePeer = useCallback((userId) => {
    const id = Number(userId);
    try {
      peersRef.current.get(id)?.close();
    } catch {
      /* already closed */
    }
    peersRef.current.delete(id);
    remoteRef.current.delete(id);
    pendingIce.current.delete(id);
    setRemoteStreams((current) => {
      if (!current[id]) return current;
      const next = { ...current };
      delete next[id];
      return next;
    });
  }, []);

  const cleanup = useCallback((finalPhase = "idle", message = "") => {
    stopTone();
    peersRef.current.forEach((peer) => {
      try {
        peer.close();
      } catch {
        /* already closed */
      }
    });
    peersRef.current.clear();
    remoteRef.current.clear();
    pendingIce.current.clear();
    localRef.current?.getTracks().forEach((track) => track.stop());
    localRef.current = null;
    shareRef.current?.getTracks().forEach((track) => track.stop());
    shareRef.current = null;
    setLocalStream(null);
    setRemoteStreams({});
    setShareStream(null);
    setReactions([]);
    roomSocketRef.current?.close();
    roomSocketRef.current = null;
    sessionRef.current = null;
    if (finalPhase === "ended") {
      // A dismissed incoming call disappears quietly.
      setCall((current) => (current.dismissed ? IDLE : { ...current, phase: "ended", message, minimized: false }));
      window.setTimeout(() => setCall((current) => (current.phase === "ended" ? IDLE : current)), 1600);
    } else {
      setCall(IDLE);
    }
    loadCalls();
  }, [stopTone]);

  /** Send a signaling frame (queued until the call socket is open). */
  const signal = useCallback((payload) => {
    roomSocketRef.current?.send(payload, { queue: true });
  }, []);

  const openRoomSocket = useCallback((roomId) => {
    roomSocketRef.current?.close();
    const socket = new ManagedSocket({
      path: `/ws/calls/${roomId}/`,
      ping: false,
      onMessage: (data) => handleSignalRef.current?.(data),
    });
    roomSocketRef.current = socket;
    socket.connect();
    return socket;
  }, []);

  const getMedia = useCallback(async (type) => {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("Calls need a supported browser over HTTPS (or localhost).");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: type === "video" ? { width: { ideal: 1280 }, height: { ideal: 720 } } : false });
      localRef.current = stream;
      setLocalStream(stream);
      return stream;
    } catch (error) {
      if (error?.name === "NotAllowedError") {
        throw new Error(type === "video" ? "Allow camera and microphone access to make video calls." : "Allow microphone access to make calls.", { cause: error });
      }
      throw new Error(type === "video" ? "No camera or microphone was found." : "No microphone was found.", { cause: error });
    }
  }, []);

  const videoSenderOf = (peer) => {
    const transceiver = peer.getTransceivers().find((item) => item.receiver?.track?.kind === "video" || item.sender?.track?.kind === "video");
    return transceiver?.sender || null;
  };

  /** One peer connection per remote participant (exactly one in a 1:1 call). */
  const createPeer = useCallback((userId, isOfferer) => {
    const id = Number(userId);
    if (peersRef.current.has(id)) return peersRef.current.get(id);
    const peer = new RTCPeerConnection({ iceServers: iceServers() });
    peersRef.current.set(id, peer);
    localRef.current?.getTracks().forEach((track) => peer.addTrack(track, localRef.current));
    // Always negotiate a video slot, so a voice call can later turn the camera
    // on or share the screen without renegotiating (replaceTrack only).
    if (isOfferer && !localRef.current?.getVideoTracks().length) {
      peer.addTransceiver("video", { direction: "sendrecv" });
    }
    peer.onicecandidate = (event) => {
      const session = sessionRef.current;
      if (!event.candidate || !session) return;
      const candidate = event.candidate.toJSON();
      signal({
        event: "ice_candidate",
        call_id: session.callId,
        target: id,
        candidate: candidate.candidate,
        sdpMid: candidate.sdpMid ?? "0",
        sdpMLineIndex: candidate.sdpMLineIndex ?? 0,
        usernameFragment: candidate.usernameFragment,
      });
    };
    peer.ontrack = (event) => {
      if (peersRef.current.get(id) !== peer) return;
      const stream = remoteRef.current.get(id) || new MediaStream();
      remoteRef.current.set(id, stream);
      if (!stream.getTracks().includes(event.track)) stream.addTrack(event.track);
      setRemoteStreams((current) => ({ ...current, [id]: new MediaStream(stream.getTracks()) }));
    };
    peer.onconnectionstatechange = () => {
      if (peersRef.current.get(id) !== peer) return;
      const state = peer.connectionState;
      if (sessionRef.current?.group) {
        if (state === "connected") {
          setCall((current) => ({ ...current, connectedAt: current.connectedAt || Date.now() }));
          setMember(id, { connected: true, failed: false });
        } else if (state === "failed") setMember(id, { connected: false, failed: true });
        else if (state === "disconnected") setMember(id, { connected: false });
        return;
      }
      if (state === "connected") {
        setCall((current) => ({ ...current, phase: "ongoing", connectedAt: current.connectedAt || Date.now(), warning: "" }));
      }
      if (state === "failed") {
        setCall((current) => ({ ...current, warning: "Connection failed. A TURN server may be required on this network." }));
      }
      if (state === "disconnected") {
        setCall((current) => ({ ...current, warning: "Reconnecting…" }));
      }
    };
    return peer;
  }, [setMember, signal]);

  const flushIce = async (userId, peer) => {
    const queued = pendingIce.current.get(Number(userId)) || [];
    pendingIce.current.delete(Number(userId));
    for (const candidate of queued) {
      try {
        await peer.addIceCandidate(new RTCIceCandidate(candidate));
      } catch {
        /* ignore stale candidates */
      }
    }
  };

  /** Create a peer for `userId` and send them an offer. */
  const offerTo = useCallback(
    async (userId) => {
      const session = sessionRef.current;
      if (!session) return;
      const peer = createPeer(userId, true);
      // Already sharing the screen: new peers get the screen, not the camera.
      if (shareRef.current) await videoSenderOf(peer)?.replaceTrack(shareRef.current.getVideoTracks()[0] || null);
      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      signal({ event: "offer", call_id: session.callId, target: Number(userId), sdp: offer.sdp, type: offer.type });
    },
    [createPeer, signal],
  );

  /** Answer an offer from `userId` (the callee in 1:1, the earlier member in a group). */
  const answerOffer = async (userId, sdp) => {
    const session = sessionRef.current;
    if (session.group && peersRef.current.has(Number(userId))) removePeer(userId); // they rejoined
    const peer = createPeer(userId, false);
    await peer.setRemoteDescription(new RTCSessionDescription({ type: "offer", sdp }));
    // Let this side send video later too (camera on / screen share in a voice call).
    peer.getTransceivers().forEach((transceiver) => {
      if (transceiver.receiver?.track?.kind === "video" && transceiver.direction === "recvonly") transceiver.direction = "sendrecv";
    });
    if (shareRef.current) await videoSenderOf(peer)?.replaceTrack(shareRef.current.getVideoTracks()[0] || null);
    await flushIce(userId, peer);
    const answer = await peer.createAnswer();
    await peer.setLocalDescription(answer);
    signal({ event: "answer", call_id: session.callId, target: Number(userId), sdp: answer.sdp, type: answer.type });
  };

  const addIce = async (userId, payload) => {
    const candidate = { candidate: payload.candidate, sdpMid: payload.sdpMid, sdpMLineIndex: payload.sdpMLineIndex, usernameFragment: payload.usernameFragment };
    const peer = peersRef.current.get(Number(userId));
    if (peer?.remoteDescription) await peer.addIceCandidate(new RTCIceCandidate(candidate));
    else pendingIce.current.set(Number(userId), [...(pendingIce.current.get(Number(userId)) || []), candidate]);
  };

  /** Floating emoji reactions (sent to the others too). */
  const addReaction = useCallback((emoji, mine, userId = null) => {
    if (!emoji) return;
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    setReactions((list) => [...list.slice(-12), { id, emoji, mine, userId, left: 30 + Math.random() * 40 }]);
    window.setTimeout(() => setReactions((list) => list.filter((item) => item.id !== id)), 3200);
  }, []);

  // Group call events (ws/calls/<room>/), for a call I'm ringing for or in.
  const handleGroupSignal = async (event, payload, session) => {
    const myId = Number(getState().me?.id);
    const from = Number(payload.from ?? payload.user);
    const mine = from === myId;
    if (event === "call_ended") {
      cleanup("ended", "Call ended");
      return;
    }
    if (event === "missed_call") {
      cleanup("ended", session.initiator ? "No answer" : "Missed call");
      return;
    }
    if (event === "member_missed" && mine) {
      // The ring timed out for me; the call goes on (I can still join from the chat).
      cleanup();
      return;
    }
    if (!session.joined) return; // still ringing: nothing else concerns me
    if (event === "offer") await answerOffer(from, payload.sdp);
    else if (event === "answer") {
      const peer = peersRef.current.get(from);
      if (peer && !peer.currentRemoteDescription) {
        await peer.setRemoteDescription(new RTCSessionDescription({ type: "answer", sdp: payload.sdp }));
        await flushIce(from, peer);
      }
    } else if (event === "ice_candidate") await addIce(from, payload);
    else if (mine) {
      // Our own member/camera/mute/share/reaction events echoed back.
    } else if (event === "member_joined") {
      // They will send us an offer. Tell them how our camera / screen is.
      setMember(from, { state: "joined", connected: false, failed: false });
      stopTone();
      setCall((current) => ({ ...current, phase: "ongoing", connectedAt: current.connectedAt || Date.now() }));
      if (call.cameraOff || !localRef.current?.getVideoTracks().length) signal({ event: "camera_off", call_id: session.callId });
      else signal({ event: "camera_on", call_id: session.callId });
      if (shareRef.current) signal({ event: "screen_share_started", call_id: session.callId });
    } else if (event === "member_left") {
      removePeer(from);
      setMember(from, { state: "left", connected: false, sharing: false });
    } else if (event === "member_declined") setMember(from, { state: "declined" });
    else if (event === "member_missed") setMember(from, { state: "missed" });
    else if (event === "camera_off" || event === "camera_on") setMember(from, { cameraOff: event === "camera_off" });
    else if (event === "mute" || event === "unmute") setMember(from, { muted: event === "mute" });
    else if (event === "screen_share_started" || event === "screen_share_stopped") setMember(from, { sharing: event === "screen_share_started" });
    else if (event === "reaction") addReaction(payload.emoji, false, from);
  };

  // Signaling messages from ws/calls/<room>/.
  const handleSignal = async (packet) => {
    const event = packet?.event;
    const payload = packet?.payload || {};
    const session = sessionRef.current;
    if (event === "error") {
      if (session && !session.group) setCall((current) => ({ ...current, warning: payload.message || "Call signaling error." }));
      return;
    }
    if (!session || Number(payload.call_id) !== Number(session.callId)) return;
    try {
      if (session.group) {
        await handleGroupSignal(event, payload, session);
        return;
      }
      if (event === "accept_call" && session.initiator) {
        stopTone();
        setCall((current) => ({ ...current, phase: "connecting" }));
        await offerTo(session.targetId);
      } else if (event === "offer" && !session.initiator) {
        await answerOffer(session.targetId, payload.sdp);
      } else if (event === "answer" && session.initiator) {
        const peer = peersRef.current.get(Number(session.targetId));
        if (peer && !peer.currentRemoteDescription) {
          await peer.setRemoteDescription(new RTCSessionDescription({ type: "answer", sdp: payload.sdp }));
          await flushIce(session.targetId, peer);
        }
      } else if (event === "ice_candidate") {
        await addIce(session.targetId, payload);
      } else if (event === "reject_call") {
        cleanup("ended", "Call declined");
      } else if (event === "busy") {
        cleanup("ended", "User is on another call");
      } else if (event === "cancel_call" || event === "call_ended" || event === "missed_call") {
        cleanup("ended", event === "missed_call" ? "No answer" : "Call ended");
      } else if (Number(payload.user) === Number(getState().me?.id)) {
        // The server echoes our own camera/mute/share/reaction events back.
      } else if (event === "camera_off" || event === "camera_on") {
        setCall((current) => ({ ...current, remoteCameraOff: event === "camera_off" }));
      } else if (event === "mute" || event === "unmute") {
        setCall((current) => ({ ...current, remoteMuted: event === "mute" }));
      } else if (event === "screen_share_started" || event === "screen_share_stopped") {
        setCall((current) => ({ ...current, remoteSharing: event === "screen_share_started" }));
      } else if (event === "reaction") {
        addReaction(payload.emoji, false);
      }
    } catch (error) {
      if (session.group) setMember(payload.from, { failed: true });
      else setCall((current) => ({ ...current, warning: error?.message || "Couldn't connect the call." }));
    }
  };

  useEffect(() => {
    handleSignalRef.current = handleSignal;
  });

  /**
   * Join a group call (accepting it, joining late from the chat banner, or
   * rejoining). The server answers with who is already in: offer to each.
   */
  const joinGroupCall = useCallback(
    async (roomId, callId, type, { fromIncoming = false } = {}) => {
      if (!fromIncoming) {
        if (sessionRef.current) {
          toast("You're already in a call.");
          return;
        }
        sessionRef.current = { callId, roomId, initiator: false, type, group: true };
        openRoomSocket(roomId);
      }
      stopTone();
      setCall((current) => ({
        ...(fromIncoming ? current : {}),
        phase: "connecting",
        group: true,
        type,
        roomId,
        callId,
        status: "Connecting…",
        muted: false,
        cameraOff: type !== "video",
        members: fromIncoming ? current.members || {} : {},
        dismissed: false,
      }));
      try {
        await getMedia(type);
        await roomSocketRef.current?.whenOpen();
        const { data } = await callApi.accept(callId);
        const session = sessionRef.current;
        if (!session || Number(session.callId) !== Number(callId)) return;
        session.joined = true;
        const meId = getState().me?.id;
        setCall((current) => ({
          ...current,
          phase: "ongoing",
          connectedAt: Date.now(),
          callerId: data.call?.caller?.id,
          members: membersFrom(data.call?.participants, meId, type),
        }));
        for (const userId of data.present || []) {
          setMember(userId, { state: "joined", connected: false });
          await offerTo(userId);
        }
        loadCalls();
      } catch (error) {
        toast.error(error?.response ? errorMessage(error) : error.message || "Couldn't join the call.");
        // Couldn't join an incoming call (e.g. it is full): stop it ringing for me.
        if (fromIncoming) callApi.reject(callId).catch(() => {});
        cleanup();
      }
    },
    [cleanup, getMedia, offerTo, openRoomSocket, setMember, stopTone],
  );

  const startGroupCall = useCallback(
    async (room, type) => {
      const active = getState().activeCalls?.[room.id];
      if (active) {
        joinGroupCall(room.id, active.id, typeOf(active.call_type));
        return;
      }
      const meId = getState().me?.id;
      const members = {};
      (room.participants || []).forEach((p) => {
        const id = Number(p.user?.id);
        if (id && id !== Number(meId)) members[id] = { state: "ringing", muted: false, cameraOff: type !== "video", connected: false };
      });
      setCall({ phase: "outgoing", group: true, type, roomId: room.id, callerId: meId, status: "Ringing…", muted: false, cameraOff: type !== "video", members });
      try {
        await getMedia(type);
        const socket = openRoomSocket(room.id);
        await socket.whenOpen();
        const created = await callApi.start(room.id, type === "video" ? "VIDEO" : "AUDIO");
        sessionRef.current = { callId: created.id, roomId: room.id, initiator: true, type, group: true, joined: true };
        setCall((current) => ({ ...current, callId: created.id, members: membersFrom(created.participants, meId, type) }));
        playTone("outgoing");
        loadCalls();
      } catch (error) {
        cleanup();
        const existing = error?.response?.status === 409 ? error.response.data?.call_id : null;
        if (existing) {
          // Someone started a call in this group meanwhile: join it.
          joinGroupCall(room.id, existing, type);
          return;
        }
        toast.error(error?.response ? errorMessage(error) : error.message || "Couldn't start the call.");
      }
    },
    [cleanup, getMedia, joinGroupCall, openRoomSocket, playTone],
  );

  const startCall = useCallback(
    async (room, type = "audio") => {
      if (!room) return;
      if (sessionRef.current || call.phase !== "idle") {
        toast("You're already in a call.");
        return;
      }
      if (room.isGroup) {
        startGroupCall(room, type);
        return;
      }
      const peerUser = room.otherUser;
      setCall({ phase: "outgoing", type, roomId: room.id, peerUser, status: "Calling…", muted: false, cameraOff: type !== "video", remoteCameraOff: type !== "video" });
      try {
        await getMedia(type);
        const socket = openRoomSocket(room.id);
        await socket.whenOpen();
        const created = await callApi.start(room.id, type === "video" ? "VIDEO" : "AUDIO");
        sessionRef.current = { callId: created.id, roomId: room.id, targetId: peerUser.id, initiator: true, type };
        // "Ringing" only when the other person's device can actually ring.
        const presence = getState().presence[peerUser.id];
        const online = presence ? presence.is_online : peerUser.profile?.is_online;
        const reachable = (created.participants || []).some((p) => Number(p.user?.id ?? p.user_id ?? p.user) === Number(peerUser.id));
        setCall((current) => ({ ...current, callId: created.id, status: reachable && online ? "Ringing…" : "Calling…" }));
        playTone("outgoing");
      } catch (error) {
        cleanup();
        toast.error(error?.response ? errorMessage(error) : error.message || "Couldn't start the call.");
      }
    },
    [call.phase, cleanup, getMedia, openRoomSocket, playTone, startGroupCall],
  );

  /** Join the ongoing group call of a room (the green "Join" banner). */
  const joinCall = useCallback(
    (roomId) => {
      const active = getState().activeCalls?.[roomId];
      if (!active) {
        toast("This call has ended.");
        return;
      }
      const session = sessionRef.current;
      if (session && Number(session.callId) === Number(active.id)) {
        if (!session.joined) acceptRef.current?.();
        else setCall((current) => ({ ...current, minimized: false, dismissed: false }));
        return;
      }
      joinGroupCall(roomId, active.id, typeOf(active.call_type));
    },
    [joinGroupCall],
  );

  const accept = useCallback(async () => {
    const session = sessionRef.current;
    if (!session) return;
    if (session.group) {
      joinGroupCall(session.roomId, session.callId, session.type, { fromIncoming: true });
      return;
    }
    stopTone();
    setCall((current) => ({ ...current, phase: "connecting", status: "Connecting…" }));
    try {
      await getMedia(session.type);
      await roomSocketRef.current?.whenOpen();
      await callApi.accept(session.callId);
      signal({ event: "accept_call", call_id: session.callId });
    } catch (error) {
      toast.error(error?.response ? errorMessage(error) : error.message);
      try {
        await callApi.reject(session.callId);
      } catch {
        /* already finished */
      }
      cleanup();
    }
  }, [cleanup, getMedia, joinGroupCall, signal, stopTone]);
  useEffect(() => {
    acceptRef.current = accept;
  });

  const decline = useCallback(async () => {
    const session = sessionRef.current;
    if (session) {
      // Declining a group call only stops it ringing for me.
      if (!session.group) signal({ event: "reject_call", call_id: session.callId });
      try {
        await callApi.reject(session.callId);
      } catch {
        /* already finished */
      }
    }
    cleanup();
  }, [cleanup, signal]);

  const hangUp = useCallback(async () => {
    const session = sessionRef.current;
    if (session?.callId) {
      // Group: POST end = leave (the call goes on while 2+ people remain).
      if (!session.group) signal({ event: "end_call", call_id: session.callId });
      try {
        await callApi.end(session.callId);
      } catch {
        /* the other side may have ended it */
      }
    }
    cleanup("ended", session?.group ? "You left the call" : "Call ended");
  }, [cleanup, signal]);

  const toggleMute = useCallback(() => {
    setCall((current) => {
      const muted = !current.muted;
      localRef.current?.getAudioTracks().forEach((track) => {
        track.enabled = !muted;
      });
      if (sessionRef.current) signal({ event: muted ? "mute" : "unmute", call_id: sessionRef.current.callId });
      return { ...current, muted };
    });
  }, [signal]);

  /** The video sender of every peer connection (one in a 1:1 call). */
  const videoSenders = useCallback(() => [...peersRef.current.values()].map(videoSenderOf).filter(Boolean), []);

  /** Camera on/off — also works in a voice call (turns it into a video call). */
  const toggleCamera = useCallback(async () => {
    const session = sessionRef.current;
    const existing = localRef.current?.getVideoTracks()[0];
    if (existing) {
      const cameraOff = existing.enabled;
      existing.enabled = !cameraOff;
      setCall((current) => ({ ...current, cameraOff }));
      if (session) signal({ event: cameraOff ? "camera_off" : "camera_on", call_id: session.callId });
      return;
    }
    try {
      const camera = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } } });
      const track = camera.getVideoTracks()[0];
      if (!localRef.current) localRef.current = new MediaStream();
      localRef.current.addTrack(track);
      setLocalStream(new MediaStream(localRef.current.getTracks()));
      if (!shareRef.current) await Promise.all(videoSenders().map((sender) => sender.replaceTrack(track)));
      setCall((current) => ({ ...current, cameraOff: false }));
      if (session) signal({ event: "camera_on", call_id: session.callId });
    } catch (error) {
      toast.error(error?.name === "NotAllowedError" ? "Allow camera access to turn on video." : "No camera was found.");
    }
  }, [signal, videoSenders]);

  const stopScreenShare = useCallback(async () => {
    const share = shareRef.current;
    if (!share) return;
    share.getTracks().forEach((track) => track.stop());
    shareRef.current = null;
    setShareStream(null);
    const camera = localRef.current?.getVideoTracks()[0] || null;
    try {
      await Promise.all(videoSenders().map((sender) => sender.replaceTrack(camera)));
    } catch {
      /* peer closed */
    }
    setCall((current) => ({ ...current, sharing: false }));
    if (sessionRef.current) signal({ event: "screen_share_stopped", call_id: sessionRef.current.callId });
  }, [signal, videoSenders]);

  /** Share a screen/window/tab instead of the camera (to everyone in the call). */
  const toggleScreenShare = useCallback(async () => {
    if (shareRef.current) {
      stopScreenShare();
      return;
    }
    if (!navigator.mediaDevices?.getDisplayMedia) {
      toast.error("Screen sharing isn't supported in this browser.");
      return;
    }
    const senders = videoSenders();
    if (!senders.length) {
      toast("Screen sharing starts once the call is connected.");
      return;
    }
    try {
      const display = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
      const track = display.getVideoTracks()[0];
      shareRef.current = display;
      setShareStream(display);
      track.onended = () => stopScreenShare();
      await Promise.all(videoSenders().map((sender) => sender.replaceTrack(track)));
      setCall((current) => ({ ...current, sharing: true }));
      if (sessionRef.current) signal({ event: "screen_share_started", call_id: sessionRef.current.callId });
    } catch (error) {
      if (error?.name !== "NotAllowedError") toast.error("Couldn't share the screen.");
    }
  }, [signal, stopScreenShare, videoSenders]);

  const sendReaction = useCallback(
    (emoji) => {
      addReaction(emoji, true, getState().me?.id);
      if (sessionRef.current) signal({ event: "reaction", call_id: sessionRef.current.callId, emoji });
    },
    [addReaction, signal],
  );

  const toggleMinimized = useCallback(() => setCall((current) => ({ ...current, minimized: !current.minimized })), []);

  /** Close the incoming-call card without declining (it keeps ringing for the caller). */
  const dismissIncoming = useCallback(() => {
    stopTone();
    setCall((current) => ({ ...current, dismissed: true }));
  }, [stopTone]);

  // Incoming calls arrive on the per-user call inbox.
  useEffect(() => {
    const inbox = new ManagedSocket({
      path: "/ws/calls/inbox/",
      ping: false,
      onMessage: async (packet) => {
        if (packet?.event !== "incoming_call") return;
        const payload = packet.payload || {};
        const state = getState();
        if (Number(payload.caller) === Number(state.me?.id)) return;
        if (sessionRef.current) {
          // Already in a call: decline the second one (only for me in a group call).
          callApi.reject(payload.call_id).catch(() => {});
          return;
        }
        const room = state.rooms[payload.room];
        const peerUser = room?.participants.find((p) => Number(p.user?.id) === Number(payload.caller))?.user || { id: payload.caller };
        const type = typeOf(payload.call_type);
        const group = Boolean(payload.is_group);
        sessionRef.current = group
          ? { callId: payload.call_id, roomId: payload.room, initiator: false, type, group: true }
          : { callId: payload.call_id, roomId: payload.room, targetId: payload.caller, initiator: false, type };
        openRoomSocket(payload.room);
        setCall({
          phase: "incoming",
          type,
          group,
          roomId: payload.room,
          callId: payload.call_id,
          peerUser,
          callerId: payload.caller,
          members: {},
          status: `Incoming ${group ? "group " : ""}${type === "video" ? "video" : "voice"} call`,
          muted: false,
          cameraOff: type !== "video",
          remoteCameraOff: type !== "video",
        });
        playTone("incoming");
        // Tab in the background: a desktop notification too (if enabled in Settings).
        const caller = group ? room?.name || "Group" : displayUserName(peerUser, contactsByUser(state.contacts));
        showDesktopNotification(caller, `Incoming ${group ? "group " : ""}${type === "video" ? "video" : "voice"} call`, () => {
          window.dispatchEvent(new CustomEvent("mhtalk:open-room", { detail: payload.room }));
        });
        if (group) loadCalls();
      },
    });
    inbox.connect();
    refreshIceServers(); // warm the cache so the first call starts instantly
    return () => inbox.close();
  }, [openRoomSocket, playTone]);

  // Server-side status changes (timeout → missed, caller cancelled).
  useEffect(() => {
    const handler = (event) => {
      const detail = event.detail || {};
      const session = sessionRef.current;
      if (!session || Number(detail.call_id) !== Number(session.callId)) return;
      const status = String(detail.status || "").toUpperCase();
      if (["ENDED", "MISSED", "REJECTED", "CANCELLED", "BUSY"].includes(status)) {
        cleanup("ended", status === "MISSED" ? (session.initiator ? "No answer" : "Missed call") : status === "REJECTED" ? (session.group ? "No one answered" : "Call declined") : "Call ended");
      }
    };
    window.addEventListener("mhtalk:call-changed", handler);
    return () => window.removeEventListener("mhtalk:call-changed", handler);
  }, [cleanup]);

  // "Join" buttons outside the call context (chat list rows).
  useEffect(() => {
    const handler = (event) => joinCall(event.detail?.roomId);
    window.addEventListener("mhtalk:join-call", handler);
    return () => window.removeEventListener("mhtalk:join-call", handler);
  }, [joinCall]);

  useEffect(() => () => cleanup(), [cleanup]);

  // Lets the chat list / header hide "Join" for the group call I'm already in.
  const currentGroupCallId = call.group && !["idle", "incoming", "ended"].includes(call.phase) ? call.callId || null : null;
  useEffect(() => {
    dispatch({ type: "calls/current", callId: currentGroupCallId });
  }, [currentGroupCallId]);

  const value = useMemo(() => ({ call, startCall, joinCall }), [call, startCall, joinCall]);
  const remoteStream = call.group ? null : remoteStreams[Number(call.peerUser?.id)] || null;

  return (
    <CallContext.Provider value={value}>
      {children}
      {call.phase !== "idle" && !call.dismissed ? (
        <CallOverlay
          call={call}
          localStream={localStream}
          remoteStream={remoteStream}
          remoteStreams={remoteStreams}
          shareStream={shareStream}
          reactions={reactions}
          onAccept={accept}
          onDecline={decline}
          onDismiss={dismissIncoming}
          onHangUp={hangUp}
          onToggleMute={toggleMute}
          onToggleCamera={toggleCamera}
          onToggleShare={toggleScreenShare}
          onReact={sendReaction}
          onToggleMinimized={toggleMinimized}
        />
      ) : null}
    </CallContext.Provider>
  );
}
