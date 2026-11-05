/** Where the AI row goes: after pinned chats, in order of its last message. */
export function assistantRowIndex(rows, lastAt) {
  const time = lastAt ? new Date(lastAt).getTime() : null;
  let index = 0;
  while (index < rows.length && rows[index].room.isPinned) index += 1;
  if (time === null) return index; // never used: near the top, so people find it
  while (index < rows.length && new Date(rows[index].room.activityAt || 0).getTime() > time) index += 1;
  return index;
}
