import { useApp } from "../layout/AppContext";
import CallInfo from "./CallInfo";

/** Phones: Call info slides over the calls list. */
export default function CallInfoPanel({ roomId, peerId, day }) {
  const app = useApp();
  return (
    <div className="panel">
      <CallInfo roomId={roomId} peerId={peerId} day={day} onClose={app.popPanel} />
    </div>
  );
}
