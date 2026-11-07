/** Emoji catalogue for the picker (Unicode emoji, grouped like WhatsApp). */

const split = (text) => text.trim().split(/\s+/);

export const EMOJI_CATEGORIES = [
  {
    id: "smileys",
    label: "Smileys & People",
    icon: "😀",
    emojis: split(`😀 😃 😄 😁 😆 😅 🤣 😂 🙂 🙃 🫠 😉 😊 😇 🥰 😍 🤩 😘 😗 ☺️ 😚 😙 🥲 😋 😛 😜 🤪 😝 🤑 🤗 🤭 🫢 🫣 🤫 🤔 🫡 🤐 🤨 😐 😑 😶 🫥 😏 😒 🙄 😬 🤥 😌 😔 😪 🤤 😴 😷 🤒 🤕 🤢 🤮 🤧 🥵 🥶 🥴 😵 🤯 🤠 🥳 🥸 😎 🤓 🧐 😕 🫤 😟 🙁 ☹️ 😮 😯 😲 😳 🥺 🥹 😦 😧 😨 😰 😥 😢 😭 😱 😖 😣 😞 😓 😩 😫 🥱 😤 😡 😠 🤬 😈 👿 💀 ☠️ 💩 🤡 👹 👺 👻 👽 👾 🤖 😺 😸 😹 😻 😼 😽 🙀 😿 😾 🙈 🙉 🙊 👋 🤚 🖐️ ✋ 🖖 🫱 🫲 👌 🤌 🤏 ✌️ 🤞 🫰 🤟 🤘 🤙 👈 👉 👆 🖕 👇 ☝️ 🫵 👍 👎 ✊ 👊 🤛 🤜 👏 🙌 🫶 👐 🤲 🤝 🙏 ✍️ 💅 🤳 💪 🦾 🧠 👀 👁️ 👅 👄 🫦 👶 🧒 👦 👧 🧑 👱 👨 🧔 👩 🧓 👴 👵 🙍 🙎 🙅 🙆 💁 🙋 🧏 🙇 🤦 🤷 👮 🕵️ 💂 🥷 👷 🤴 👸 👳 👲 🧕 🤵 👰 🤰 🤱 👼 🎅 🤶 🦸 🦹 🧙 🧚 🧛 🧜 🧝 🧞 🧟 💆 💇 🚶 🧍 🧎 🏃 💃 🕺 👯 🧖 🧗 🤺 🏇 ⛷️ 🏂 🏌️ 🏄 🚣 🏊 ⛹️ 🏋️ 🚴 🚵 🤸 🤼 🤽 🤾 🤹 🧘 🛀 🛌 👭 👫 👬 💏 💑 👪 🗣️ 👤 👥 🫂`),
  },
  {
    id: "animals",
    label: "Animals & Nature",
    icon: "🐻",
    emojis: split(`🐶 🐱 🐭 🐹 🐰 🦊 🐻 🐼 🐻‍❄️ 🐨 🐯 🦁 🐮 🐷 🐽 🐸 🐵 🐔 🐧 🐦 🐤 🐣 🐥 🦆 🦅 🦉 🦇 🐺 🐗 🐴 🦄 🐝 🪱 🐛 🦋 🐌 🐞 🐜 🪰 🪲 🪳 🦟 🦗 🕷️ 🦂 🐢 🐍 🦎 🦖 🦕 🐙 🦑 🦐 🦞 🦀 🐡 🐠 🐟 🐬 🐳 🐋 🦈 🐊 🐅 🐆 🦓 🦍 🦧 🦣 🐘 🦛 🦏 🐪 🐫 🦒 🦘 🦬 🐃 🐂 🐄 🐎 🐖 🐏 🐑 🦙 🐐 🦌 🐕 🐩 🦮 🐈 🐓 🦃 🦤 🦚 🦜 🦢 🦩 🕊️ 🐇 🦝 🦨 🦡 🦫 🦦 🦥 🐁 🐀 🐿️ 🦔 🐾 🐉 🐲 🌵 🎄 🌲 🌳 🌴 🪵 🌱 🌿 ☘️ 🍀 🎍 🪴 🎋 🍃 🍂 🍁 🍄 🐚 🪨 🌾 💐 🌷 🌹 🥀 🌺 🌸 🌼 🌻 🌞 🌝 🌛 🌜 🌚 🌕 🌖 🌗 🌘 🌑 🌒 🌓 🌔 🌙 🌎 🌍 🌏 🪐 💫 ⭐ 🌟 ✨ ⚡ ☄️ 💥 🔥 🌪️ 🌈 ☀️ 🌤️ ⛅ 🌥️ ☁️ 🌦️ 🌧️ ⛈️ 🌩️ 🌨️ ❄️ ☃️ ⛄ 🌬️ 💨 💧 💦 🫧 ☔ ☂️ 🌊 🌫️`),
  },
  {
    id: "food",
    label: "Food & Drink",
    icon: "🍔",
    emojis: split(`🍏 🍎 🍐 🍊 🍋 🍌 🍉 🍇 🍓 🫐 🍈 🍒 🍑 🥭 🍍 🥥 🥝 🍅 🍆 🥑 🥦 🥬 🥒 🌶️ 🫑 🌽 🥕 🫒 🧄 🧅 🥔 🍠 🥐 🥯 🍞 🥖 🥨 🧀 🥚 🍳 🧈 🥞 🧇 🥓 🥩 🍗 🍖 🦴 🌭 🍔 🍟 🍕 🫓 🥪 🥙 🧆 🌮 🌯 🫔 🥗 🥘 🫕 🥫 🍝 🍜 🍲 🍛 🍣 🍱 🥟 🦪 🍤 🍙 🍚 🍘 🍥 🥠 🥮 🍢 🍡 🍧 🍨 🍦 🥧 🧁 🍰 🎂 🍮 🍭 🍬 🍫 🍿 🍩 🍪 🌰 🥜 🍯 🥛 🍼 🫖 ☕ 🍵 🧃 🥤 🧋 🍶 🍺 🍻 🥂 🍷 🥃 🍸 🍹 🧉 🍾 🧊 🥄 🍴 🍽️ 🥣 🥡 🥢 🧂`),
  },
  {
    id: "activity",
    label: "Activity",
    icon: "⚽",
    emojis: split(`⚽ 🏀 🏈 ⚾ 🥎 🎾 🏐 🏉 🥏 🎱 🪀 🏓 🏸 🏒 🏑 🥍 🏏 🪃 🥅 ⛳ 🪁 🏹 🎣 🤿 🥊 🥋 🎽 🛹 🛼 🛷 ⛸️ 🥌 🎿 🏆 🥇 🥈 🥉 🏅 🎖️ 🏵️ 🎗️ 🎫 🎟️ 🎪 🎭 🩰 🎨 🎬 🎤 🎧 🎼 🎹 🥁 🪘 🎷 🎺 🪗 🎸 🪕 🎻 🎲 ♟️ 🎯 🎳 🎮 🎰 🧩 🎉 🎊 🎈 🎁 🎀 🪅 🪩`),
  },
  {
    id: "travel",
    label: "Travel & Places",
    icon: "🚗",
    emojis: split(`🚗 🚕 🚙 🚌 🚎 🏎️ 🚓 🚑 🚒 🚐 🛻 🚚 🚛 🚜 🦯 🦽 🦼 🛴 🚲 🛵 🏍️ 🛺 🚨 🚔 🚍 🚘 🚖 🚡 🚠 🚟 🚃 🚋 🚞 🚝 🚄 🚅 🚈 🚂 🚆 🚇 🚊 🚉 ✈️ 🛫 🛬 🛩️ 💺 🛰️ 🚀 🛸 🚁 🛶 ⛵ 🚤 🛥️ 🛳️ ⛴️ 🚢 ⚓ 🪝 ⛽ 🚧 🚦 🚥 🚏 🗺️ 🗿 🗽 🗼 🏰 🏯 🏟️ 🎡 🎢 🎠 ⛲ ⛱️ 🏖️ 🏝️ 🏜️ 🌋 ⛰️ 🏔️ 🗻 🏕️ ⛺ 🛖 🏠 🏡 🏘️ 🏚️ 🏗️ 🏭 🏢 🏬 🏣 🏤 🏥 🏦 🏨 🏪 🏫 🏩 💒 🏛️ ⛪ 🕌 🕍 🛕 🕋 ⛩️ 🛤️ 🛣️ 🗾 🎑 🏞️ 🌅 🌄 🌠 🎇 🎆 🌇 🌆 🏙️ 🌃 🌌 🌉 🌁`),
  },
  {
    id: "objects",
    label: "Objects",
    icon: "💡",
    emojis: split(`⌚ 📱 📲 💻 ⌨️ 🖥️ 🖨️ 🖱️ 🖲️ 🕹️ 🗜️ 💽 💾 💿 📀 📼 📷 📸 📹 🎥 📽️ 🎞️ 📞 ☎️ 📟 📠 📺 📻 🎙️ 🎚️ 🎛️ 🧭 ⏱️ ⏲️ ⏰ 🕰️ ⌛ ⏳ 📡 🔋 🪫 🔌 💡 🔦 🕯️ 🪔 🧯 🛢️ 💸 💵 💴 💶 💷 🪙 💰 💳 💎 ⚖️ 🪜 🧰 🪛 🔧 🔨 ⚒️ 🛠️ ⛏️ 🪚 🔩 ⚙️ 🪤 🧱 ⛓️ 🧲 🔫 💣 🧨 🪓 🔪 🗡️ ⚔️ 🛡️ 🚬 ⚰️ 🪦 ⚱️ 🏺 🔮 📿 🧿 💈 ⚗️ 🔭 🔬 🕳️ 🩹 🩺 💊 💉 🩸 🧬 🦠 🧫 🧪 🌡️ 🧹 🪠 🧺 🧻 🚽 🚰 🚿 🛁 🛀 🧼 🪥 🪒 🧽 🪣 🧴 🛎️ 🔑 🗝️ 🚪 🪑 🛋️ 🛏️ 🛌 🧸 🪆 🖼️ 🪞 🪟 🛍️ 🛒 🎁 🎈 🎏 🎀 🪄 🪅 🎊 🎉 🎎 🏮 🎐 🧧 ✉️ 📩 📨 📧 💌 📥 📤 📦 🏷️ 🪧 📪 📫 📬 📭 📮 📯 📜 📃 📄 📑 🧾 📊 📈 📉 🗒️ 🗓️ 📆 📅 🗑️ 📇 🗃️ 🗳️ 🗄️ 📋 📁 📂 🗂️ 🗞️ 📰 📓 📔 📒 📕 📗 📘 📙 📚 📖 🔖 🧷 🔗 📎 🖇️ 📐 📏 🧮 📌 📍 ✂️ 🖊️ 🖋️ ✒️ 🖌️ 🖍️ 📝 ✏️ 🔍 🔎 🔏 🔐 🔒 🔓`),
  },
  {
    id: "symbols",
    label: "Symbols",
    icon: "❤️",
    emojis: split(`❤️ 🧡 💛 💚 💙 💜 🖤 🤍 🤎 💔 ❤️‍🔥 ❤️‍🩹 ❣️ 💕 💞 💓 💗 💖 💘 💝 💟 ☮️ ✝️ ☪️ 🕉️ ☸️ ✡️ 🔯 🕎 ☯️ ☦️ 🛐 ⛎ ♈ ♉ ♊ ♋ ♌ ♍ ♎ ♏ ♐ ♑ ♒ ♓ 🆔 ⚛️ 🉑 ☢️ ☣️ 📴 📳 🈶 🈚 🈸 🈺 🈷️ ✴️ 🆚 💮 🉐 ㊙️ ㊗️ 🈴 🈵 🈹 🈲 🅰️ 🅱️ 🆎 🆑 🅾️ 🆘 ❌ ⭕ 🛑 ⛔ 📛 🚫 💯 💢 ♨️ 🚷 🚯 🚳 🚱 🔞 📵 🚭 ❗ ❕ ❓ ❔ ‼️ ⁉️ 🔅 🔆 〽️ ⚠️ 🚸 🔱 ⚜️ 🔰 ♻️ ✅ 🈯 💹 ❇️ ✳️ ❎ 🌐 💠 Ⓜ️ 🌀 💤 🏧 🚾 ♿ 🅿️ 🛗 🈳 🈂️ 🛂 🛃 🛄 🛅 🚹 🚺 🚼 ⚧️ 🚻 🚮 🎦 📶 🈁 🔣 ℹ️ 🔤 🔡 🔠 🆖 🆗 🆙 🆒 🆕 🆓 0️⃣ 1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣ 6️⃣ 7️⃣ 8️⃣ 9️⃣ 🔟 🔢 #️⃣ *️⃣ ⏏️ ▶️ ⏸️ ⏯️ ⏹️ ⏺️ ⏭️ ⏮️ ⏩ ⏪ ⏫ ⏬ ◀️ 🔼 🔽 ➡️ ⬅️ ⬆️ ⬇️ ↗️ ↘️ ↙️ ↖️ ↕️ ↔️ ↪️ ↩️ ⤴️ ⤵️ 🔀 🔁 🔂 🔄 🔃 🎵 🎶 ➕ ➖ ➗ ✖️ 🟰 ♾️ 💲 💱 ™️ ©️ ®️ 〰️ ➰ ➿ 🔚 🔙 🔛 🔝 🔜 ✔️ ☑️ 🔘 🔴 🟠 🟡 🟢 🔵 🟣 ⚫ ⚪ 🟤 🔺 🔻 🔸 🔹 🔶 🔷 🔳 🔲 ▪️ ▫️ ◾ ◽ ◼️ ◻️ 🟥 🟧 🟨 🟩 🟦 🟪 ⬛ ⬜ 🟫 🔈 🔇 🔉 🔊 🔔 🔕 📣 📢 💬 💭 🗯️ ♠️ ♣️ ♥️ ♦️ 🃏 🎴 🀄 🕐 🕑 🕒 🕓 🕔 🕕 🕖 🕗 🕘 🕙 🕚 🕛`),
  },
  {
    id: "flags",
    label: "Flags",
    icon: "🏳️",
    emojis: split(`🏳️ 🏴 🏁 🚩 🏳️‍🌈 🏴‍☠️ 🇵🇰 🇮🇳 🇧🇩 🇦🇫 🇸🇦 🇦🇪 🇶🇦 🇰🇼 🇴🇲 🇧🇭 🇹🇷 🇮🇷 🇮🇶 🇯🇴 🇪🇬 🇲🇦 🇩🇿 🇹🇳 🇳🇬 🇰🇪 🇿🇦 🇬🇧 🇺🇸 🇨🇦 🇲🇽 🇧🇷 🇦🇷 🇨🇱 🇨🇴 🇵🇪 🇫🇷 🇩🇪 🇮🇹 🇪🇸 🇵🇹 🇳🇱 🇧🇪 🇨🇭 🇦🇹 🇸🇪 🇳🇴 🇩🇰 🇫🇮 🇮🇪 🇵🇱 🇺🇦 🇷🇺 🇬🇷 🇨🇳 🇯🇵 🇰🇷 🇮🇩 🇲🇾 🇸🇬 🇹🇭 🇻🇳 🇵🇭 🇦🇺 🇳🇿`),
  },
];

/** Keyword index for the most common emoji (used by the search box). */
export const EMOJI_KEYWORDS = {
  "😀": "grin smile happy", "😃": "smile happy", "😄": "smile laugh", "😁": "grin beam", "😆": "laugh",
  "😅": "sweat laugh", "🤣": "rofl laugh rolling", "😂": "joy laugh tears lol", "🙂": "smile slight",
  "🙃": "upside down", "😉": "wink", "😊": "blush smile", "😇": "angel halo", "🥰": "love hearts",
  "😍": "heart eyes love", "🤩": "star struck wow", "😘": "kiss", "😋": "yum tasty", "😛": "tongue",
  "😜": "wink tongue crazy", "🤪": "zany crazy", "🤗": "hug", "🤔": "think thinking hmm", "🤐": "zip quiet",
  "😐": "neutral", "😏": "smirk", "😒": "unamused", "🙄": "eye roll", "😬": "grimace", "😌": "relieved",
  "😔": "pensive sad", "😴": "sleep zzz", "😷": "mask sick", "🤒": "sick fever", "🤢": "nausea sick",
  "🤮": "vomit", "🥵": "hot", "🥶": "cold freezing", "🤯": "mind blown", "🥳": "party celebrate",
  "😎": "cool sunglasses", "🤓": "nerd", "😕": "confused", "😟": "worried", "😮": "wow surprised",
  "😳": "flushed embarrassed", "🥺": "pleading please", "🥹": "holding tears", "😢": "cry sad",
  "😭": "sob crying", "😱": "scream fear", "😩": "weary tired", "😤": "triumph angry", "😡": "angry mad rage",
  "😠": "angry", "🤬": "swear curse", "💀": "skull dead", "💩": "poop", "🤡": "clown", "👻": "ghost",
  "🙈": "see no evil monkey", "👋": "wave hello hi bye", "👌": "ok perfect", "✌️": "peace victory",
  "🤞": "fingers crossed luck", "👍": "thumbs up like yes ok", "👎": "thumbs down dislike no",
  "👏": "clap applause", "🙌": "raise hands praise", "🫶": "heart hands love", "🤝": "handshake deal",
  "🙏": "pray please thanks", "💪": "muscle strong", "👀": "eyes look", "❤️": "heart love red",
  "🧡": "orange heart", "💛": "yellow heart", "💚": "green heart", "💙": "blue heart", "💜": "purple heart",
  "🖤": "black heart", "🤍": "white heart", "💔": "broken heart", "💕": "hearts love", "💯": "hundred perfect",
  "🔥": "fire lit hot", "✨": "sparkles", "⭐": "star", "🌟": "glowing star", "🎉": "party tada celebrate",
  "🎂": "birthday cake", "🎁": "gift present", "🌹": "rose flower", "🌸": "blossom flower", "☀️": "sun",
  "🌙": "moon night", "⚽": "football soccer", "🏏": "cricket", "☕": "coffee tea", "🍕": "pizza",
  "🍔": "burger", "✅": "check done yes", "❌": "cross no wrong", "⚠️": "warning", "📞": "phone call",
  "📷": "camera photo", "💰": "money", "🇵🇰": "pakistan flag",
};

const RECENT_KEY = "mhtalk_recent_emoji";

export function recentEmoji() {
  try {
    const value = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    return Array.isArray(value) ? value.slice(0, 32) : [];
  } catch {
    return [];
  }
}

export function rememberEmoji(emoji) {
  try {
    const next = [emoji, ...recentEmoji().filter((item) => item !== emoji)].slice(0, 32);
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    /* storage unavailable */
  }
}

let keywordLibrary = null;

/** Full English keyword list for every emoji (emojilib), loaded on first search. */
export async function loadEmojiKeywords() {
  if (!keywordLibrary) keywordLibrary = (await import("emojilib")).default;
  return keywordLibrary;
}

/**
 * Emoji whose names / keywords start with every word typed ("cry", "red
 * heart", "thumbs"). Works with the small built-in list straight away and
 * with the full library once ``library`` has loaded.
 */
export function searchEmoji(query, library = keywordLibrary) {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const scored = [];
  const seen = new Set();
  const consider = (emoji, keywords) => {
    if (seen.has(emoji)) return;
    const tokens = keywords.flatMap((keyword) => keyword.toLowerCase().split(/[_\s-]+/));
    let score = 0;
    for (const word of words) {
      if (tokens.includes(word)) score += 3;
      else if (tokens.some((token) => token.startsWith(word))) score += 1;
      else return;
    }
    seen.add(emoji);
    scored.push([emoji, score]);
  };
  Object.entries(EMOJI_KEYWORDS).forEach(([emoji, keywords]) => consider(emoji, Array.isArray(keywords) ? keywords : String(keywords).split(/\s+/)));
  if (library) Object.entries(library).forEach(([emoji, keywords]) => consider(emoji, keywords));
  return scored.sort((a, b) => b[1] - a[1]).slice(0, 160).map(([emoji]) => emoji);
}

export const QUICK_REACTIONS = ["👍", "❤️", "😂", "😮", "😢", "🙏"];

const EMOJI_PART = /\p{Extended_Pictographic}|\p{Emoji_Modifier}|\p{Regional_Indicator}|‍|️|⃣/gu;

/**
 * The emoji in `text` when it is only emoji (at most `max` of them), else
 * null. "😂", "❤️", "👍🏽" and "😍😍" count; "ok 👍" and "1" don't.
 */
export function emojiOnly(text, max = 3) {
  const value = String(text || "").replace(/\s+/g, "");
  if (!value || value.replace(EMOJI_PART, "") !== "" || !/\p{Extended_Pictographic}|\p{Regional_Indicator}/u.test(value)) return null;
  const count = typeof Intl !== "undefined" && Intl.Segmenter ? [...new Intl.Segmenter().segment(value)].length : [...value].length;
  return count <= max ? value : null;
}
