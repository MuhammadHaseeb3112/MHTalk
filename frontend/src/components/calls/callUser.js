import { errorMessage } from "../../api/client";
import { openChatWith } from "../../store/actions";
import { getState } from "../../store/store";
import { toast } from "../../services/toast";

/** Start a call with a user (opens/creates the 1:1 chat first). */
export async function callUser(user, type, startCall) {
  try {
    const roomId = await openChatWith(user);
    const room = getState().rooms[roomId];
    if (room) startCall(room, type);
  } catch (error) {
    toast.error(errorMessage(error));
  }
}
