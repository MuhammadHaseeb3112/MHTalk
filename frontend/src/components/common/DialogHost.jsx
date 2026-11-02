import { useEffect, useState } from "react";
import { subscribeDialogs } from "../../services/dialogs";

export default function DialogHost() {
  const [dialog, setDialog] = useState(null);
  useEffect(() => subscribeDialogs(setDialog), []);
  if (!dialog) return null;
  return <div key={dialog.key}>{dialog.render(dialog.close)}</div>;
}
