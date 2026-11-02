/**
 * Custom SVG icons for WhatsApp-specific glyphs (ticks, chat bubble tails,
 * status ring, nav icons). Generic glyphs come from lucide-react.
 */

const base = (size) => ({ width: size, height: size, viewBox: "0 0 24 24", fill: "none", "aria-hidden": true });

export function SingleTick({ size = 16, className }) {
  return (
    <svg {...base(size)} viewBox="0 0 16 11" className={className}>
      <path d="M11.07.65 4.6 7.12 1.93 4.45.87 5.51l3.73 3.73 7.53-7.53L11.07.65Z" fill="currentColor" />
    </svg>
  );
}

export function DoubleTick({ size = 16, className }) {
  return (
    <svg {...base(size)} viewBox="0 0 16 11" className={className}>
      <path d="M11.07.65 4.6 7.12 1.93 4.45.87 5.51l3.73 3.73 7.53-7.53L11.07.65Z" fill="currentColor" />
      <path d="m15.1.65-6.47 6.47-.95-.95-1.06 1.06 2.01 2.01 7.53-7.53L15.1.65Z" fill="currentColor" />
    </svg>
  );
}

export function ClockIcon({ size = 14, className }) {
  return (
    <svg {...base(size)} viewBox="0 0 16 16" className={className}>
      <circle cx="8" cy="8" r="6.2" stroke="currentColor" strokeWidth="1.4" />
      <path d="M8 4.6V8l2.3 1.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

export function ChatsIcon({ size = 24, filled }) {
  return (
    <svg {...base(size)}>
      <path
        d="M4.5 5.5h15a1.5 1.5 0 0 1 1.5 1.5v9a1.5 1.5 0 0 1-1.5 1.5H9l-4.2 3.15a.5.5 0 0 1-.8-.4V18a1.5 1.5 0 0 1-1-1.42V7a1.5 1.5 0 0 1 1.5-1.5Z"
        fill={filled ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M7.5 10h9M7.5 13.2h6" stroke={filled ? "var(--rail-bg)" : "currentColor"} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function StatusIcon({ size = 24, filled }) {
  return (
    <svg {...base(size)}>
      <path d="M12 3a9 9 0 1 1-8.2 5.3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeDasharray={filled ? "0" : "0"} />
      <path d="M4.9 6.1A9 9 0 0 1 8 3.6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="12" cy="12" r="4.6" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

export function NewChatIcon({ size = 22 }) {
  return (
    <svg {...base(size)}>
      <path
        d="M4.5 5h10.5M4.5 5A1.5 1.5 0 0 0 3 6.5v9.6c0 .6.5 1.1 1.1 1.1h.9v2.3c0 .4.5.7.8.4l3.2-2.7h9.5a1.5 1.5 0 0 0 1.5-1.5V11"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M18.5 2.5v6M15.5 5.5h6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

/** MHTalk's own mark: a chat bubble with an upward chevron ("up"). */
export function LogoMark({ size = 40 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden>
      <rect width="48" height="48" rx="14" fill="var(--accent)" />
      <path
        d="M13 15.5A3.5 3.5 0 0 1 16.5 12h15a3.5 3.5 0 0 1 3.5 3.5v12a3.5 3.5 0 0 1-3.5 3.5H22l-6.4 5.1c-.7.5-1.6 0-1.6-.8V31a3.5 3.5 0 0 1-1-2.5v-13Z"
        fill="#fff"
      />
      <path d="m18.5 24.5 5.5-5.5 5.5 5.5" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  );
}

/** Bubble tail (WhatsApp's small corner notch on the first bubble of a group). */
export function BubbleTail({ side }) {
  return side === "out" ? (
    <svg className="bubble-tail bubble-tail--out" viewBox="0 0 8 13" width="8" height="13" aria-hidden>
      <path d="M5.188 1H0v11.193l6.467-8.625C7.526 2.156 6.958 1 5.188 1Z" fill="currentColor" />
    </svg>
  ) : (
    <svg className="bubble-tail bubble-tail--in" viewBox="0 0 8 13" width="8" height="13" aria-hidden>
      <path d="M2.812 1H8v11.193L1.533 3.568C.474 2.156 1.042 1 2.812 1Z" fill="currentColor" />
    </svg>
  );
}

export function DefaultAvatarIcon({ group }) {
  return group ? (
    <svg viewBox="0 0 212 212" width="100%" height="100%" aria-hidden>
      <path fill="var(--avatar-bg)" d="M106 0a106 106 0 1 0 0 212 106 106 0 0 0 0-212Z" />
      <path
        fill="var(--avatar-fg)"
        d="M102.4 135.8c-8.5 0-16.8 1.4-24.8 4.3-8.6 3.2-15.2 7.7-18.7 13.1-.9 1.4-1.5 3-1.5 4.7v12.6c14.1 13.8 33.4 22.3 54.6 22.3 21.2 0 40.5-8.5 54.6-22.3v-12.6c0-1.7-.6-3.3-1.5-4.7-3.5-5.4-10.1-9.9-18.7-13.1-8-2.9-16.3-4.3-24.8-4.3h-19.2Zm9.6-79.4c-14.8 0-26.8 12-26.8 26.8s12 26.8 26.8 26.8 26.8-12 26.8-26.8-12-26.8-26.8-26.8ZM55.5 87.8c-10.3 0-18.7 8.4-18.7 18.7s8.4 18.7 18.7 18.7 18.7-8.4 18.7-18.7-8.4-18.7-18.7-18.7Zm101 0c-10.3 0-18.7 8.4-18.7 18.7s8.4 18.7 18.7 18.7 18.7-8.4 18.7-18.7-8.4-18.7-18.7-18.7Z"
      />
    </svg>
  ) : (
    <svg viewBox="0 0 212 212" width="100%" height="100%" aria-hidden>
      <path fill="var(--avatar-bg)" d="M106 0a106 106 0 1 0 0 212 106 106 0 0 0 0-212Z" />
      <path
        fill="var(--avatar-fg)"
        d="M173.6 164.7c-12.6-15.8-32.3-26-54.4-26.4h-26.4c-22.1.4-41.8 10.6-54.4 26.4C57.8 183.5 80.6 195.5 106 195.5s48.2-12 67.6-30.8ZM106 128.8c21.3 0 38.6-17.3 38.6-38.6S127.3 51.6 106 51.6 67.4 68.9 67.4 90.2s17.3 38.6 38.6 38.6Z"
      />
    </svg>
  );
}
