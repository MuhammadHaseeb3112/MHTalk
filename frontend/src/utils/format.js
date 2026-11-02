/** Date/time and number formatting matching WhatsApp Web conventions. */

const DAY = 24 * 60 * 60 * 1000;

function toDate(value) {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function startOfDay(date) {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

export function clockTime(value) {
  const date = toDate(value);
  if (!date) return "";
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

/** Chat list timestamp: time today, "Yesterday", weekday this week, else date. */
export function listTime(value) {
  const date = toDate(value);
  if (!date) return "";
  const days = Math.round((startOfDay(new Date()) - startOfDay(date)) / DAY);
  if (days <= 0) return clockTime(date);
  if (days === 1) return "Yesterday";
  if (days < 7) return date.toLocaleDateString([], { weekday: "long" });
  return date.toLocaleDateString();
}

/** Separator label between days in a conversation. */
export function dayLabel(value) {
  const date = toDate(value);
  if (!date) return "";
  const days = Math.round((startOfDay(new Date()) - startOfDay(date)) / DAY);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return date.toLocaleDateString([], { weekday: "long" });
  return date.toLocaleDateString([], { day: "numeric", month: "long", year: "numeric" });
}

export function sameDay(a, b) {
  const x = toDate(a);
  const y = toDate(b);
  return Boolean(x && y && x.toDateString() === y.toDateString());
}

/** "last seen today at 4:05 PM" */
export function lastSeenLabel(value) {
  const date = toDate(value);
  if (!date) return "";
  if (Date.now() - date.getTime() < 60 * 1000) return "last seen just now";
  const days = Math.round((startOfDay(new Date()) - startOfDay(date)) / DAY);
  const time = clockTime(date);
  if (days <= 0) return `last seen today at ${time}`;
  if (days === 1) return `last seen yesterday at ${time}`;
  return `last seen ${date.toLocaleDateString([], { day: "numeric", month: "short" })} at ${time}`;
}

/** "Today at 4:05 PM" for detail panels. */
export function detailTime(value) {
  const date = toDate(value);
  if (!date) return "";
  const age = Date.now() - date.getTime();
  if (age < 60 * 1000) return "Just now";
  if (age < 60 * 60 * 1000) return `${Math.floor(age / 60000)} min ago`;
  const days = Math.round((startOfDay(new Date()) - startOfDay(date)) / DAY);
  const time = clockTime(date);
  if (days <= 0) return `Today at ${time}`;
  if (days === 1) return `Yesterday at ${time}`;
  return `${date.toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" })} at ${time}`;
}

export function duration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function fileSize(bytes) {
  const value = Number(bytes) || 0;
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} kB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

export function initials(name) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "";
  const first = parts[0][0] || "";
  const second = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + second).toUpperCase();
}
