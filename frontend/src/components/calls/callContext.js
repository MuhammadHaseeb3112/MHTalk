import { createContext, useContext } from "react";

/** { call, startCall(room, "audio" | "video"), joinCall(roomId) } provided by CallProvider. */
export const CallContext = createContext(null);
export const useCalls = () => useContext(CallContext);
