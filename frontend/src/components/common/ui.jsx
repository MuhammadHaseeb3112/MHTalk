import { memo, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Loader2, X } from "lucide-react";
import { mediaUrl } from "../../api/client";
import { useDismiss } from "../../hooks";
import { dismissToast, subscribeToasts } from "../../services/toast";
import { initials } from "../../utils/format";
import { DefaultAvatarIcon } from "./Icons";

/* ---------------------------------------------------------------- Avatar */
export const Avatar = memo(function Avatar({ src, name, size = 49, group = false, ring, onClick, className = "" }) {
  const [failed, setFailed] = useState(false);
  const url = !failed && src ? mediaUrl(src) : "";
  const style = { width: size, height: size, minWidth: size };
  const content = url ? (
    <img src={url} alt="" loading="lazy" onError={() => setFailed(true)} />
  ) : name && !group && /[a-z]/i.test(initials(name)) ? (
    <span className="avatar__initials" style={{ fontSize: Math.max(12, size * 0.38) }}>{initials(name)}</span>
  ) : (
    <DefaultAvatarIcon group={group} />
  );
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      type={onClick ? "button" : undefined}
      className={`avatar ${ring ? `avatar--ring avatar--ring-${ring}` : ""} ${className}`}
      style={style}
      onClick={onClick}
      aria-label={onClick ? `Open ${name || "profile"}` : undefined}
    >
      {content}
    </Tag>
  );
});

/* ---------------------------------------------------------------- Buttons */
export function IconButton({ icon: Icon, label, onClick, active, size = 20, className = "", badge, disabled, ...rest }) {
  return (
    <button
      type="button"
      className={`icon-btn ${active ? "is-active" : ""} ${className}`}
      onClick={onClick}
      aria-label={label}
      data-tooltip={label}
      disabled={disabled}
      {...rest}
    >
      <Icon size={size} strokeWidth={1.9} />
      {badge ? <span className="icon-btn__badge">{badge}</span> : null}
    </button>
  );
}

export function Spinner({ size = 22, className = "" }) {
  return <Loader2 className={`spinner ${className}`} size={size} />;
}

export function Checkbox({ checked, onChange, label, decorative = false }) {
  // Inside a clickable row the row itself toggles; render a non-interactive
  // mark so we never nest a <button> inside another <button>.
  if (decorative) {
    return (
      <span role="checkbox" aria-checked={checked} aria-label={label} className={`checkbox ${checked ? "is-checked" : ""}`}>
        {checked ? <Check size={14} strokeWidth={3} /> : null}
      </span>
    );
  }
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      aria-label={label}
      className={`checkbox ${checked ? "is-checked" : ""}`}
      onClick={(event) => {
        event.stopPropagation();
        onChange?.(!checked);
      }}
    >
      {checked ? <Check size={14} strokeWidth={3} /> : null}
    </button>
  );
}

export function Toggle({ checked, onChange, label }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} className={`toggle ${checked ? "is-on" : ""}`} onClick={() => onChange(!checked)}>
      <span />
    </button>
  );
}

/* ---------------------------------------------------------------- Menu */
/**
 * Dropdown menu rendered in a portal and clamped to the viewport so it is
 * never clipped by scroll containers. Closes on outside click, Escape and
 * after an item is chosen.
 */
export function Menu({ anchor, items, onClose, align = "right", minWidth = 210 }) {
  const ref = useRef(null);
  const [position, setPosition] = useState(null);
  useDismiss([ref], onClose);

  useLayoutEffect(() => {
    const rect = anchor?.getBoundingClientRect ? anchor.getBoundingClientRect() : anchor;
    const menu = ref.current;
    if (!rect || !menu) return;
    const width = Math.max(minWidth, menu.offsetWidth);
    const height = menu.offsetHeight;
    const margin = 8;
    let left = align === "right" ? rect.right - width : rect.left;
    left = Math.min(Math.max(margin, left), window.innerWidth - width - margin);
    let top = rect.bottom + 4;
    if (top + height > window.innerHeight - margin) top = Math.max(margin, rect.top - height - 4);
    setPosition({ left, top, minWidth: width });
  }, [anchor, align, minWidth, items.length]);

  useEffect(() => {
    const close = () => onClose();
    window.addEventListener("resize", close);
    return () => window.removeEventListener("resize", close);
  }, [onClose]);

  return createPortal(
    <div
      ref={ref}
      className="menu"
      role="menu"
      style={position ? { left: position.left, top: position.top, minWidth: position.minWidth } : { visibility: "hidden", left: 0, top: 0 }}
    >
      {items.filter(Boolean).map((item, index) =>
        item.divider ? (
          <div key={`d-${index}`} className="menu__divider" />
        ) : (
          <button
            key={item.label}
            type="button"
            role="menuitem"
            className={`menu__item ${item.danger ? "is-danger" : ""}`}
            disabled={item.disabled}
            onClick={(event) => {
              event.stopPropagation();
              onClose();
              item.onClick?.(event);
            }}
          >
            {item.icon ? <item.icon size={19} strokeWidth={1.8} /> : null}
            <span>{item.label}</span>
            {item.hint ? <span className="menu__hint">{item.hint}</span> : null}
          </button>
        ),
      )}
    </div>,
    document.body,
  );
}

/** Icon button that toggles a Menu. */
export function MenuButton({ icon, label, items, align = "right", className = "", size }) {
  const [anchor, setAnchor] = useState(null);
  return (
    <>
      <IconButton
        icon={icon}
        label={label}
        size={size}
        className={className}
        active={Boolean(anchor)}
        onClick={(event) => {
          event.stopPropagation();
          setAnchor(anchor ? null : event.currentTarget);
        }}
      />
      {anchor ? <Menu anchor={anchor} items={items} align={align} onClose={() => setAnchor(null)} /> : null}
    </>
  );
}

/* ---------------------------------------------------------------- Modal */
export function Modal({ title, children, onClose, footer, width = 440, className = "" }) {
  const ref = useRef(null);
  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && onClose?.();
    document.addEventListener("keydown", onKey);
    ref.current?.querySelector("input, textarea, button.btn--primary")?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose?.()}>
      <div ref={ref} className={`modal ${className}`} style={{ width }} role="dialog" aria-modal="true" aria-label={title}>
        {title ? (
          <div className="modal__header">
            <h2>{title}</h2>
            {onClose ? <IconButton icon={X} label="Close" onClick={onClose} /> : null}
          </div>
        ) : null}
        <div className="modal__body">{children}</div>
        {footer ? <div className="modal__footer">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}

export function ConfirmDialog({ title, message, confirmLabel = "OK", danger, onConfirm, onClose, busy, extra }) {
  return (
    <Modal
      title={title}
      onClose={busy ? undefined : onClose}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          {extra}
          <button type="button" className={`btn ${danger ? "btn--danger" : "btn--primary"}`} onClick={onConfirm} disabled={busy}>
            {busy ? <Spinner size={16} /> : confirmLabel}
          </button>
        </>
      }
    >
      {typeof message === "string" ? <p className="modal__text">{message}</p> : message}
    </Modal>
  );
}

/* ---------------------------------------------------------------- Panels */
export function PanelHeader({ title, onBack, actions, subtitle, variant = "default" }) {
  return (
    <header className={`panel-header panel-header--${variant}`}>
      {onBack ? (
        <button type="button" className="icon-btn" onClick={onBack} aria-label="Back">
          {variant === "close" ? <X size={22} /> : <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M20 12H5m6-7-7 7 7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>}
        </button>
      ) : null}
      <div className="panel-header__title">
        <h1>{title}</h1>
        {subtitle ? <span>{subtitle}</span> : null}
      </div>
      {actions ? <div className="panel-header__actions">{actions}</div> : null}
    </header>
  );
}

export function SearchInput({ value, onChange, placeholder = "Search", autoFocus, onKeyDown, loading }) {
  const ref = useRef(null);
  return (
    <div className={`search-input ${value ? "has-value" : ""}`}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden className="search-input__icon">
        <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="2" />
        <path d="m16 16 4.5 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <input
        ref={ref}
        value={value}
        autoFocus={autoFocus}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        aria-label={placeholder}
      />
      {loading ? <Spinner size={16} className="search-input__spinner" /> : null}
      {value ? (
        <button type="button" className="search-input__clear" aria-label="Clear search" onClick={() => { onChange(""); ref.current?.focus(); }}>
          <X size={16} />
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, text, children }) {
  return (
    <div className="empty-state">
      {Icon ? <Icon size={40} strokeWidth={1.4} /> : null}
      {title ? <h3>{title}</h3> : null}
      {text ? <p>{text}</p> : null}
      {children}
    </div>
  );
}

/* ---------------------------------------------------------------- Toasts */
export function ToastHost() {
  const [items, setItems] = useState([]);
  useEffect(() => subscribeToasts(setItems), []);
  return createPortal(
    <div className="toasts" role="status" aria-live="polite">
      {items.map((item) => (
        <div key={item.id} className={`toast toast--${item.type}`}>
          <span>{item.message}</span>
          {item.action ? (
            <button type="button" onClick={() => { item.action.onClick(); dismissToast(item.id); }}>
              {item.action.label}
            </button>
          ) : null}
        </div>
      ))}
    </div>,
    document.body,
  );
}
