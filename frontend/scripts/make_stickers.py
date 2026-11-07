"""
Builds MHTalk's built-in sticker packs (original artwork, drawn in SVG):
  public/stickers/<pack>/<name>.webp  +  public/stickers/packs.json
Run:  python3 scripts/make_stickers.py   (needs rsvg-convert and Pillow)
"""
import json
import os
import subprocess
import tempfile

from PIL import Image

ROOT = os.path.join(os.path.dirname(__file__), "..", "public", "stickers")
FONT = "Poppins"

def outline(svg_body, size=512):
    # White sticker border + soft shadow around everything, like WhatsApp stickers.
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 512 512">
<defs>
 <filter id="o" x="-20%" y="-20%" width="140%" height="140%">
  <feMorphology in="SourceAlpha" operator="dilate" radius="9" result="d"/>
  <feFlood flood-color="#ffffff"/><feComposite in2="d" operator="in" result="w"/>
  <feGaussianBlur in="d" stdDeviation="6" result="b"/><feOffset in="b" dy="5" result="bo"/>
  <feFlood flood-color="#000" flood-opacity="0.25"/><feComposite in2="bo" operator="in" result="s"/>
  <feMerge><feMergeNode in="s"/><feMergeNode in="w"/><feMergeNode in="SourceGraphic"/></feMerge>
 </filter>
 <radialGradient id="g" cx="40%" cy="30%" r="75%"><stop offset="0" stop-color="#7CF2A6"/><stop offset="1" stop-color="#1DAA61"/></radialGradient>
 <radialGradient id="cat" cx="40%" cy="30%" r="75%"><stop offset="0" stop-color="#FFD39A"/><stop offset="1" stop-color="#F29A38"/></radialGradient>
 <radialGradient id="red" cx="40%" cy="30%" r="75%"><stop offset="0" stop-color="#FF9C8A"/><stop offset="1" stop-color="#E5483B"/></radialGradient>
</defs>
<g filter="url(#o)">{svg_body}</g></svg>'''

# ---------- faces --------------------------------------------------------
INK = "#1F2A30"

def eyes(kind, y=245, dx=62, cx=256):
    l, r = cx - dx, cx + dx
    if kind == "open":
        return f'<ellipse cx="{l}" cy="{y}" rx="20" ry="27" fill="{INK}"/><ellipse cx="{r}" cy="{y}" rx="20" ry="27" fill="{INK}"/><circle cx="{l+7}" cy="{y-9}" r="7" fill="#fff"/><circle cx="{r+7}" cy="{y-9}" r="7" fill="#fff"/>'
    if kind == "happy":
        return f'<path d="M{l-24} {y+8} Q{l} {y-26} {l+24} {y+8}" stroke="{INK}" stroke-width="12" fill="none" stroke-linecap="round"/><path d="M{r-24} {y+8} Q{r} {y-26} {r+24} {y+8}" stroke="{INK}" stroke-width="12" fill="none" stroke-linecap="round"/>'
    if kind == "laugh":
        return f'<path d="M{l-24} {y-12} L{l+18} {y} L{l-24} {y+12}" stroke="{INK}" stroke-width="12" fill="none" stroke-linecap="round" stroke-linejoin="round"/><path d="M{r+24} {y-12} L{r-18} {y} L{r+24} {y+12}" stroke="{INK}" stroke-width="12" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    if kind == "hearts":
        h = lambda x: f'<path transform="translate({x-30} {y-30}) scale(1.25)" d="M24 44 C-8 22 4 0 24 14 C44 0 56 22 24 44Z" fill="#FF3B5C"/>'
        return h(l) + h(r)
    if kind == "sad":
        return f'<ellipse cx="{l}" cy="{y+6}" rx="17" ry="22" fill="{INK}"/><ellipse cx="{r}" cy="{y+6}" rx="17" ry="22" fill="{INK}"/><path d="M{l-30} {y-30} L{l+20} {y-42}" stroke="{INK}" stroke-width="10" stroke-linecap="round"/><path d="M{r+30} {y-30} L{r-20} {y-42}" stroke="{INK}" stroke-width="10" stroke-linecap="round"/>'
    if kind == "angry":
        return f'<ellipse cx="{l}" cy="{y+8}" rx="18" ry="20" fill="{INK}"/><ellipse cx="{r}" cy="{y+8}" rx="18" ry="20" fill="{INK}"/><path d="M{l-34} {y-40} L{l+24} {y-16}" stroke="{INK}" stroke-width="13" stroke-linecap="round"/><path d="M{r+34} {y-40} L{r-24} {y-16}" stroke="{INK}" stroke-width="13" stroke-linecap="round"/>'
    if kind == "wink":
        return f'<ellipse cx="{l}" cy="{y}" rx="20" ry="27" fill="{INK}"/><circle cx="{l+7}" cy="{y-9}" r="7" fill="#fff"/><path d="M{r-24} {y+4} Q{r} {y-22} {r+24} {y+4}" stroke="{INK}" stroke-width="12" fill="none" stroke-linecap="round"/>'
    if kind == "wide":
        return f'<circle cx="{l}" cy="{y}" r="30" fill="#fff" stroke="{INK}" stroke-width="8"/><circle cx="{r}" cy="{y}" r="30" fill="#fff" stroke="{INK}" stroke-width="8"/><circle cx="{l}" cy="{y}" r="12" fill="{INK}"/><circle cx="{r}" cy="{y}" r="12" fill="{INK}"/>'
    if kind == "cool":
        return f'<path d="M{l-52} {y-24} H{r+52} V{y-12} H{r+44} Q{r+40} {y+34} {r} {y+30} Q{r-38} {y+30} {r-40} {y-8} H{l+40} Q{l+38} {y+30} {l} {y+30} Q{l-40} {y+34} {l-44} {y-12} H{l-52}Z" fill="{INK}"/><path d="M{r+8} {y-6} l18 0" stroke="#fff" stroke-width="7" stroke-linecap="round" opacity="0.7"/>'
    if kind == "sleep":
        return f'<path d="M{l-24} {y} Q{l} {y+18} {l+24} {y}" stroke="{INK}" stroke-width="11" fill="none" stroke-linecap="round"/><path d="M{r-24} {y} Q{r} {y+18} {r+24} {y}" stroke="{INK}" stroke-width="11" fill="none" stroke-linecap="round"/>'
    if kind == "up":
        return f'<ellipse cx="{l}" cy="{y}" rx="20" ry="27" fill="{INK}"/><ellipse cx="{r}" cy="{y}" rx="20" ry="27" fill="{INK}"/><circle cx="{l+4}" cy="{y-14}" r="8" fill="#fff"/><circle cx="{r+4}" cy="{y-14}" r="8" fill="#fff"/>'
    if kind == "stars":
        s = lambda x: f'<path transform="translate({x} {y})" d="M0 -30 L9 -9 L30 -8 L13 6 L19 28 L0 15 L-19 28 L-13 6 L-30 -8 L-9 -9Z" fill="#FFC531" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>'
        return s(l) + s(r)
    return ""

def mouth(kind, y=318, cx=256):
    if kind == "smile":
        return f'<path d="M{cx-52} {y-8} Q{cx} {y+44} {cx+52} {y-8}" stroke="{INK}" stroke-width="12" fill="none" stroke-linecap="round"/>'
    if kind == "grin":
        return f'<path d="M{cx-70} {y-14} Q{cx} {y-6} {cx+70} {y-14} Q{cx+62} {y+66} {cx} {y+68} Q{cx-62} {y+66} {cx-70} {y-14}Z" fill="{INK}"/><path d="M{cx-36} {y+44} Q{cx} {y+20} {cx+36} {y+44} Q{cx} {y+64} {cx-36} {y+44}Z" fill="#FF6B7D"/>'
    if kind == "frown":
        return f'<path d="M{cx-44} {y+26} Q{cx} {y-12} {cx+44} {y+26}" stroke="{INK}" stroke-width="12" fill="none" stroke-linecap="round"/>'
    if kind == "o":
        return f'<ellipse cx="{cx}" cy="{y+14}" rx="24" ry="30" fill="{INK}"/>'
    if kind == "flat":
        return f'<path d="M{cx-34} {y+8} H{cx+34}" stroke="{INK}" stroke-width="12" stroke-linecap="round"/>'
    if kind == "kiss":
        return f'<path d="M{cx-8} {y-6} Q{cx+22} {y+4} {cx-4} {y+16} Q{cx+24} {y+28} {cx-8} {y+38}" stroke="{INK}" stroke-width="10" fill="none" stroke-linecap="round"/>'
    if kind == "smirk":
        return f'<path d="M{cx-40} {y+14} Q{cx+10} {y+22} {cx+48} {y-10}" stroke="{INK}" stroke-width="12" fill="none" stroke-linecap="round"/>'
    if kind == "teeth":
        return f'<rect x="{cx-58}" y="{y-4}" width="116" height="40" rx="18" fill="#fff" stroke="{INK}" stroke-width="9"/><path d="M{cx-58} {y+16} H{cx+58}" stroke="{INK}" stroke-width="6"/>'
    return ""

def blush(cx=256, y=290, dx=104, color="#FF7A8A"):
    return f'<ellipse cx="{cx-dx}" cy="{y}" rx="24" ry="13" fill="{color}" opacity="0.55"/><ellipse cx="{cx+dx}" cy="{y}" rx="24" ry="13" fill="{color}" opacity="0.55"/>'

def extras(kind):
    if kind == "tears":
        return '<path d="M150 262 Q120 330 140 360 Q170 380 175 340 Q172 300 150 262Z" fill="#5BC8FF"/><path d="M362 262 Q392 330 372 360 Q342 380 337 340 Q340 300 362 262Z" fill="#5BC8FF"/>'
    if kind == "tear":
        return '<path d="M196 268 Q180 310 192 328 Q210 340 214 316 Q212 292 196 268Z" fill="#5BC8FF"/>'
    if kind == "zz":
        return f'<text x="350" y="140" font-family="{FONT}" font-weight="700" font-size="74" fill="#5B6CFF" stroke="#fff" stroke-width="6" paint-order="stroke">Z</text><text x="410" y="90" font-family="{FONT}" font-weight="700" font-size="50" fill="#5B6CFF" stroke="#fff" stroke-width="5" paint-order="stroke">z</text>'
    if kind == "question":
        return f'<text x="380" y="150" font-family="{FONT}" font-weight="700" font-size="120" fill="#FFC531" stroke="{INK}" stroke-width="7" paint-order="stroke">?</text>'
    if kind == "party":
        return ('<path d="M206 98 L256 -2 L306 98Z" fill="#B266FF" stroke="#fff" stroke-width="6" stroke-linejoin="round"/>'
                '<circle cx="256" cy="0" r="16" fill="#FFC531"/>'
                '<rect x="60" y="120" width="16" height="30" rx="4" fill="#FF3B5C" transform="rotate(-25 68 135)"/>'
                '<rect x="430" y="150" width="16" height="30" rx="4" fill="#3BA7FF" transform="rotate(30 438 165)"/>'
                '<circle cx="90" cy="200" r="10" fill="#FFC531"/><circle cx="440" cy="240" r="10" fill="#1DAA61"/>')
    if kind == "heart":
        return '<path transform="translate(360 70) scale(2.1)" d="M24 44 C-8 22 4 0 24 14 C44 0 56 22 24 44Z" fill="#FF3B5C" stroke="#fff" stroke-width="3"/>'
    if kind == "steam":
        return f'<path d="M90 140 q-20 -30 0 -60 q20 -30 0 -60" stroke="#ff6b5b" stroke-width="12" fill="none" stroke-linecap="round"/><path d="M422 140 q20 -30 0 -60 q-20 -30 0 -60" stroke="#ff6b5b" stroke-width="12" fill="none" stroke-linecap="round"/>'
    if kind == "thumb":
        return (f'<g transform="translate(330 300) rotate(-8)"><rect x="0" y="40" width="110" height="96" rx="26" fill="#FFD39A" stroke="{INK}" stroke-width="8"/>'
                f'<path d="M14 46 Q20 -36 62 -20 Q74 -8 66 40" fill="#FFD39A" stroke="{INK}" stroke-width="8" stroke-linejoin="round"/>'
                f'<path d="M30 76 H100 M30 104 H100" stroke="{INK}" stroke-width="6" stroke-linecap="round"/></g>')
    if kind == "wave":
        return (f'<g transform="translate(360 150) rotate(18)"><rect x="0" y="40" width="96" height="100" rx="34" fill="#FFD39A" stroke="{INK}" stroke-width="8"/>'
                f'<path d="M8 50 V-6 M34 46 V-20 M60 46 V-14 M86 50 V0" stroke="{INK}" stroke-width="22" stroke-linecap="round"/>'
                f'<path d="M8 50 V-6 M34 46 V-20 M60 46 V-14 M86 50 V0" stroke="#FFD39A" stroke-width="10" stroke-linecap="round"/></g>'
                '<path d="M470 120 q20 20 0 44 M492 104 q30 34 0 76" stroke="#5B6CFF" stroke-width="8" fill="none" stroke-linecap="round"/>')
    return ""

def head(kind):
    if kind == "buddy":
        return '<ellipse cx="256" cy="282" rx="196" ry="186" fill="url(#g)"/><ellipse cx="200" cy="170" rx="54" ry="28" fill="#fff" opacity="0.35"/>'
    if kind == "buddy-red":
        return '<ellipse cx="256" cy="282" rx="196" ry="186" fill="url(#red)"/><ellipse cx="200" cy="170" rx="54" ry="28" fill="#fff" opacity="0.35"/>'
    if kind == "cat":
        return ('<path d="M92 210 L110 50 L210 130Z" fill="url(#cat)"/><path d="M420 210 L402 50 L302 130Z" fill="url(#cat)"/>'
                '<path d="M120 170 L128 90 L180 134Z" fill="#FF9FB0"/><path d="M392 170 L384 90 L332 134Z" fill="#FF9FB0"/>'
                '<ellipse cx="256" cy="296" rx="200" ry="170" fill="url(#cat)"/>'
                '<path d="M220 110 q36 -14 72 0 M210 140 q46 -12 92 0" stroke="#C96F1C" stroke-width="10" fill="none" stroke-linecap="round" opacity="0.6"/>'
                f'<path d="M243 296 h26 l-13 14Z" fill="#FF6B7D"/>'
                '<path d="M80 300 h-60 M84 326 h-58 M432 300 h60 M428 326 h58" stroke="#C96F1C" stroke-width="7" stroke-linecap="round" opacity="0.7"/>')
    return ""

def face(head_kind, eye, mouth_kind, extra="", blushing=False, mouth_y=318, eye_y=245):
    parts = [head(head_kind), eyes(eye, y=eye_y), mouth(mouth_kind, y=mouth_y)]
    if blushing:
        parts.append(blush())
    parts.append(extras(extra))
    return "".join(parts)

BUDDY = [
    ("hello", "hi hello wave salam", face("buddy", "happy", "smile", "wave", True)),
    ("happy", "happy smile glad", face("buddy", "happy", "smile", "", True)),
    ("lol", "lol haha laugh funny joy", face("buddy", "laugh", "grin", "tears")),
    ("love", "love heart hearts cute", face("buddy", "hearts", "smile", "", True)),
    ("kiss", "kiss love mwah", face("buddy", "wink", "kiss", "heart", True)),
    ("wow", "wow surprised shock omg", face("buddy", "wide", "o")),
    ("sad", "sad cry upset", face("buddy", "sad", "frown", "tear")),
    ("crying", "crying cry tears sob", face("buddy", "laugh", "frown", "tears")),
    ("angry", "angry mad gussa", face("buddy-red", "angry", "frown", "steam")),
    ("cool", "cool sunglasses swag", face("buddy", "cool", "smirk")),
    ("sleepy", "sleep sleepy tired good night", face("buddy", "sleep", "o", "zz")),
    ("thinking", "thinking hmm question", face("buddy", "up", "flat", "question")),
    ("party", "party celebrate birthday", face("buddy", "stars", "grin", "party")),
    ("thumbs-up", "ok thumbs up yes good", face("buddy", "happy", "smile", "thumb", True)),
    ("awkward", "awkward oops sorry", face("buddy", "open", "teeth", "", True)),
]
KITTY = [
    ("hi", "hi hello cat kitty", face("cat", "open", "smile", "wave", True, mouth_y=330)),
    ("purr", "happy cat purr", face("cat", "happy", "smile", "", True, mouth_y=330)),
    ("lol", "lol laugh cat", face("cat", "laugh", "grin", "tears", mouth_y=326)),
    ("love", "love cat heart", face("cat", "hearts", "smile", "heart", True, mouth_y=330)),
    ("shock", "wow shock cat", face("cat", "wide", "o", mouth_y=326)),
    ("sad", "sad cat cry", face("cat", "sad", "frown", "tear", mouth_y=330)),
    ("grumpy", "angry grumpy cat", face("cat", "angry", "frown", "steam", mouth_y=330)),
    ("sleepy", "sleep cat night", face("cat", "sleep", "flat", "zz", mouth_y=330)),
    ("cool", "cool cat", face("cat", "cool", "smirk", mouth_y=330)),
    ("wink", "wink cat", face("cat", "wink", "smile", "", True, mouth_y=330)),
]

def word_sticker(text, top, bottom, rotate, size=110):
    lines = text.split("\n")
    body = (f'<g transform="rotate({rotate} 256 256)">'
            f'<defs><linearGradient id="t" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient></defs>'
            f'<rect x="40" y="{256 - 70 * len(lines) - 20}" width="432" height="{140 * len(lines) + 40}" rx="70" fill="url(#t)"/>')
    for index, line in enumerate(lines):
        y = 256 - 70 * (len(lines) - 1) + 140 * index + size * 0.36
        body += (f'<text x="256" y="{y}" text-anchor="middle" font-family="{FONT}" font-weight="700" font-size="{size}" '
                 f'fill="#fff" stroke="#1F2A30" stroke-width="12" paint-order="stroke" stroke-linejoin="round">{line}</text>')
    return body + "</g>"

WORDS = [
    ("salam", "salam hello assalam", word_sticker("Salam!", "#34D399", "#059669", -6)),
    ("hi", "hi hello hey", word_sticker("Hi!", "#60A5FA", "#2563EB", 5, 150)),
    ("thank-you", "thanks thank you shukriya", word_sticker("Thank\nyou!", "#F472B6", "#DB2777", -4, 104)),
    ("shukriya", "shukriya thanks", word_sticker("Shukriya", "#A78BFA", "#7C3AED", 4, 92)),
    ("ok", "ok okay fine done", word_sticker("OK!", "#FBBF24", "#D97706", -8, 160)),
    ("lol", "lol haha funny", word_sticker("LOL", "#FB923C", "#EA580C", 6, 160)),
    ("haha", "haha lol laugh", word_sticker("Haha", "#FDE047", "#CA8A04", -5, 130)),
    ("wow", "wow amazing", word_sticker("Wow!", "#22D3EE", "#0891B2", 7, 140)),
    ("good-night", "good night sleep", word_sticker("Good\nnight", "#818CF8", "#4338CA", -3, 104)),
    ("good-morning", "good morning", word_sticker("Good\nmorning", "#FCD34D", "#F59E0B", 3, 96)),
    ("miss-you", "miss you love", word_sticker("Miss\nyou", "#FB7185", "#E11D48", -6, 110)),
    ("on-my-way", "on my way coming", word_sticker("On my\nway!", "#4ADE80", "#16A34A", 4, 100)),
    ("inshallah", "inshallah", word_sticker("InshaAllah", "#2DD4BF", "#0F766E", -3, 80)),
    ("mashallah", "mashallah", word_sticker("MashaAllah", "#F59E0B", "#B45309", 3, 78)),
    ("ameen", "ameen amen", word_sticker("Ameen", "#93C5FD", "#3B82F6", -5, 120)),
    ("congrats", "congrats congratulations mubarak", word_sticker("Mubarak!", "#F0ABFC", "#C026D3", 5, 100)),
]

PACKS = [
    ("buddy", "MHTalk Buddy", BUDDY),
    ("kitty", "Kitty", KITTY),
    ("words", "Say it", WORDS),
]

def build():
    manifest = []
    for pack_id, name, items in PACKS:
        folder = os.path.join(ROOT, pack_id)
        os.makedirs(folder, exist_ok=True)
        entries = []
        for sticker_id, tags, body in items:
            with tempfile.TemporaryDirectory() as tmp:
                svg = os.path.join(tmp, "s.svg")
                png = os.path.join(tmp, "s.png")
                open(svg, "w").write(outline(body))
                subprocess.run(["rsvg-convert", "-w", "512", "-h", "512", svg, "-o", png], check=True)
                Image.open(png).save(os.path.join(folder, f"{sticker_id}.webp"), "WEBP", quality=88, method=6)
            entries.append({"id": f"{pack_id}/{sticker_id}", "file": f"/stickers/{pack_id}/{sticker_id}.webp", "tags": tags})
        manifest.append({"id": pack_id, "name": name, "icon": entries[0]["file"], "stickers": entries})
    with open(os.path.join(ROOT, "packs.json"), "w") as handle:
        json.dump({"packs": manifest}, handle, indent=1)
    print("stickers:", sum(len(p["stickers"]) for p in manifest))

if __name__ == "__main__":
    build()
