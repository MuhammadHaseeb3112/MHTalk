import { useState } from "react";
import { ConfirmDialog, Modal, Spinner } from "./ui";

export function ConfirmRunner({ title, message, confirmLabel, danger, onConfirm, close }) {
  const [busy, setBusy] = useState(false);
  return (
    <ConfirmDialog
      title={title}
      message={message}
      confirmLabel={confirmLabel}
      danger={danger}
      busy={busy}
      onClose={close}
      onConfirm={async () => {
        setBusy(true);
        try {
          await onConfirm?.();
        } finally {
          close();
        }
      }}
    />
  );
}

export function ChoiceRunner({ title, text, options, initial, confirmLabel, onChoose, close }) {
  const [value, setValue] = useState(initial);
  const [busy, setBusy] = useState(false);
  return (
    <Modal
      title={title}
      onClose={busy ? undefined : close}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={close} disabled={busy}>Cancel</button>
          <button
            type="button"
            className="btn btn--primary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onChoose(value);
              } finally {
                close();
              }
            }}
          >
            {busy ? <Spinner size={16} /> : confirmLabel}
          </button>
        </>
      }
    >
      {text ? <p className="modal__text" style={{ marginBottom: 14 }}>{text}</p> : null}
      <div className="radio-list" role="radiogroup">
        {options.map((option) => (
          <label key={option.value} className={`radio ${value === option.value ? "is-checked" : ""}`}>
            <input type="radio" name="choice" value={option.value} checked={value === option.value} onChange={() => setValue(option.value)} />
            <span className="radio__dot" />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    </Modal>
  );
}
