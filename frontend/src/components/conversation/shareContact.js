import { messageApi } from "../../api/endpoints";
import { errorMessage } from "../../api/client";
import { toast } from "../../services/toast";
import { receiveMessage } from "../../store/actions";

/** Send a contact card ({name, phone}) to each chat in ``roomIds``. */
export async function sendContactCard(card, roomIds) {
  let sent = 0;
  for (const roomId of roomIds) {
    try {
      const saved = await messageApi.send({ room: roomId, message_type: "CONTACT", content: { name: card.name, phone: card.phone } });
      receiveMessage(roomId, saved);
      sent += 1;
    } catch (error) {
      toast.error(errorMessage(error));
    }
  }
  if (sent) toast(sent === 1 ? "Contact sent" : `Contact sent to ${sent} chats`);
}
