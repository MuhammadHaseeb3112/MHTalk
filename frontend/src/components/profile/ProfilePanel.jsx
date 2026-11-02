import { useRef, useState } from "react";
import { Camera, Check, Eye, Image as ImageIcon, Info, Pencil, Phone, Smile, Trash2, User } from "lucide-react";
import { errorMessage } from "../../api/client";
import { authApi } from "../../api/endpoints";
import { scheduleRoomsReload } from "../../store/actions";
import { dispatch, useStore } from "../../store/store";
import { toast } from "../../services/toast";
import { formatPhone } from "../../utils/phone";
import { normalizeFiles, openFilePicker } from "../../utils/files";
import { Avatar, Menu, PanelHeader, Spinner } from "../common/ui";
import { confirmAction } from "../common/dialogs";
import { useApp } from "../layout/AppContext";
import EmojiPicker from "../conversation/EmojiPicker";
import CameraCapture from "../media/CameraCapture";
import Lightbox from "../media/Lightbox";

const ABOUT_PRESETS = ["Available", "Busy", "At school", "At the movies", "At work", "Battery about to die", "Can't talk, MHTalk only", "In a meeting", "At the gym", "Sleeping", "Urgent calls only"];

function EditableField({ icon: Icon, label, value, maxLength, onSave, hint, presets }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [busy, setBusy] = useState(false);
  const [emoji, setEmoji] = useState(false);
  const inputRef = useRef(null);
  const emojiRef = useRef(null);

  async function save(next = draft) {
    const trimmed = next.trim();
    if (!trimmed) {
      toast.error(`${label} can't be empty.`);
      return;
    }
    if (trimmed === value) {
      setEditing(false);
      return;
    }
    setBusy(true);
    const ok = await onSave(trimmed);
    setBusy(false);
    if (ok) setEditing(false);
  }

  return (
    <div className="profile-field">
      <Icon size={20} className="profile-field__icon" />
      <div className="profile-field__body">
        <span className="profile-field__label">{label}</span>
        {editing ? (
          <div className="profile-field__edit">
            <input
              ref={inputRef}
              value={draft}
              maxLength={maxLength}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") save();
                if (event.key === "Escape") setEditing(false);
              }}
              autoFocus
            />
            <span className="profile-field__count">{maxLength - draft.length}</span>
            <span ref={emojiRef}>
              <button type="button" className="icon-btn" aria-label="Emoji" onClick={() => setEmoji((v) => !v)}>
                <Smile size={19} />
              </button>
            </span>
            <button type="button" className="icon-btn" aria-label="Save" onClick={() => save()} disabled={busy}>
              {busy ? <Spinner size={16} /> : <Check size={20} />}
            </button>
            {emoji ? (
              <EmojiPicker
                className="emoji-picker--field"
                ignoreRefs={[emojiRef]}
                onClose={() => setEmoji(false)}
                onPick={(item) => {
                  setDraft((current) => (current + item).slice(0, maxLength));
                  inputRef.current?.focus();
                }}
              />
            ) : null}
          </div>
        ) : (
          <div className="profile-field__value">
            <span>{value || "—"}</span>
            <button type="button" className="icon-btn" aria-label={`Edit ${label}`} onClick={() => { setDraft(value || ""); setEditing(true); }}>
              <Pencil size={18} />
            </button>
          </div>
        )}
        {hint ? <span className="profile-field__hint">{hint}</span> : null}
        {editing && presets ? (
          <div className="profile-presets">
            {presets.map((preset) => (
              <button key={preset} type="button" className="chip" onClick={() => save(preset)}>
                {preset}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** Your profile: photo, name, about, phone (WhatsApp Web "Profile"). */
export default function ProfilePanel() {
  const app = useApp();
  const me = useStore((state) => state.me);
  const [photoMenu, setPhotoMenu] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [camera, setCamera] = useState(false);
  const [viewing, setViewing] = useState(false);
  const photo = me.profile?.profile_picture;

  async function update(fields, success) {
    try {
      const data = await authApi.updateProfile(fields);
      dispatch({ type: "me", me: data.user || { ...me, profile: { ...me.profile, ...data.profile } } });
      scheduleRoomsReload();
      if (success) toast.success(success);
      return true;
    } catch (error) {
      toast.error(errorMessage(error));
      return false;
    }
  }

  async function uploadPhoto(picked) {
    if (!picked) return;
    const [file] = await normalizeFiles([picked]);
    if (!file.type.startsWith("image/")) {
      toast.error("Choose an image file.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      toast.error("Profile photos must be 5 MB or smaller.");
      return;
    }
    setUploading(true);
    await update({ profile_picture: file }, "Profile photo updated");
    setUploading(false);
  }

  const items = [
    photo ? { label: "View photo", icon: Eye, onClick: () => setViewing(true) } : null,
    { label: "Take photo", icon: Camera, onClick: () => setCamera(true) },
    { label: "Upload photo", icon: ImageIcon, onClick: () => openFilePicker("profile-photo-input") },
    photo
      ? {
          label: "Remove photo",
          icon: Trash2,
          danger: true,
          onClick: () => confirmAction({ title: "Remove profile photo?", confirmLabel: "Remove", danger: true, onConfirm: () => update({ remove_picture: "true" }, "Profile photo removed") }),
        }
      : null,
  ].filter(Boolean);

  return (
    <section className="panel profile-panel">
      <PanelHeader title="Profile" onBack={app.compact ? () => app.setSection("settings") : undefined} />
      <div className="panel__scroll">
        <div className="profile-photo">
          <button type="button" className="profile-photo__btn" onClick={(event) => setPhotoMenu(event.currentTarget)} aria-label="Change profile photo">
            <Avatar src={photo} name={me.profile?.display_name} size={200} />
            <span className="profile-photo__overlay">
              {uploading ? <Spinner size={28} /> : <Camera size={26} />}
              <span>{photo ? "Change profile photo" : "Add profile photo"}</span>
            </span>
          </button>
          <input id="profile-photo-input" type="file" accept="image/*" hidden onChange={(event) => { uploadPhoto(event.target.files?.[0]); event.target.value = ""; }} />
        </div>

        <EditableField
          icon={User}
          label="Name"
          value={me.profile?.display_name && me.profile.display_name !== me.phone_number ? me.profile.display_name : ""}
          maxLength={25}
          hint="This is not your username or PIN. This name will be visible to your MHTalk contacts."
          onSave={(display_name) => update({ display_name }, "Name updated")}
        />
        <EditableField
          icon={Info}
          label="About"
          value={me.profile?.about || ""}
          maxLength={139}
          presets={ABOUT_PRESETS}
          onSave={(about) => update({ about }, "About updated")}
        />
        <div className="profile-field">
          <Phone size={20} className="profile-field__icon" />
          <div className="profile-field__body">
            <span className="profile-field__label">Phone</span>
            <div className="profile-field__value"><span>{formatPhone(me.phone_number)}</span></div>
          </div>
        </div>
      </div>
      {photoMenu ? <Menu anchor={photoMenu} items={items} align="left" onClose={() => setPhotoMenu(null)} /> : null}
      {camera ? (
        <div className="camera-modal">
          <CameraCapture onClose={() => setCamera(false)} onCapture={(file) => { setCamera(false); if (file.type.startsWith("image/")) uploadPhoto(file); else toast.error("Take a photo, not a video."); }} />
        </div>
      ) : null}
      {viewing && photo ? (
        <Lightbox
          items={[{ message: { id: "me", sender: me, created_at: new Date().toISOString(), content: "" }, attachment: { id: "p", file: photo, mime_type: "image/jpeg", file_name: "profile.jpg" } }]}
          nameOf={() => "You"}
          onClose={() => setViewing(false)}
        />
      ) : null}
    </section>
  );
}
