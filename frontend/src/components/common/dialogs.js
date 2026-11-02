import { createElement } from "react";
import { openDialog } from "../../services/dialogs";
import { ChoiceRunner, ConfirmRunner } from "./DialogRunners";

/** Confirm, then run `onConfirm` (may be async) while showing a spinner. */
export function confirmAction({ title, message, confirmLabel = "OK", danger = false, onConfirm }) {
  openDialog((close) => createElement(ConfirmRunner, { title, message, confirmLabel, danger, onConfirm, close }));
}

/** Radio-style single choice dialog (mute duration, etc.). */
export function chooseOption({ title, text, options, initial, confirmLabel = "OK", onChoose }) {
  openDialog((close) =>
    createElement(ChoiceRunner, { title, text, options, initial: initial ?? options[0]?.value, confirmLabel, onChoose, close }),
  );
}
