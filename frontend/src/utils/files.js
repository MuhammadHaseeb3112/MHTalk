import { toast } from "../services/toast";

export const MAX_UPLOAD_MB = 100;
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;

/**
 * Validate picked files before previewing/uploading.
 * mode: "media" (photos/videos), "audio", or anything else for documents.
 * Returns the accepted files and shows one toast summarising rejections.
 */
export function validateFiles(files, mode) {
  const accepted = [];
  const problems = [];
  files.forEach((file) => {
    if (!file.size) problems.push(`"${file.name}" is empty`);
    else if (file.size > MAX_UPLOAD_BYTES) problems.push(`"${file.name}" is larger than ${MAX_UPLOAD_MB} MB`);
    else if (mode === "media" && !/^(image|video)\//.test(file.type)) problems.push(`"${file.name}" is not a photo or video`);
    else if (mode === "audio" && !file.type.startsWith("audio/")) problems.push(`"${file.name}" is not an audio file`);
    else accepted.push(file);
  });
  if (problems.length) toast.error(problems.slice(0, 2).join(", ") + (problems.length > 2 ? ` and ${problems.length - 2} more` : "") + ".");
  return accepted;
}

// Magic numbers for the photo/video formats we preview. Some apps (the
// WhatsApp desktop app among them) save photos without a file extension, so
// the browser reports no type; we read the first bytes to recover it.
const SIGNATURES = [
  { type: "image/jpeg", ext: "jpg", test: (b) => b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff },
  { type: "image/png", ext: "png", test: (b) => b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47 },
  { type: "image/gif", ext: "gif", test: (b) => b[0] === 0x47 && b[1] === 0x49 && b[2] === 0x46 },
  { type: "image/webp", ext: "webp", test: (b) => ascii(b, 0, 4) === "RIFF" && ascii(b, 8, 12) === "WEBP" },
  { type: "video/mp4", ext: "mp4", test: (b) => ascii(b, 4, 8) === "ftyp" },
  { type: "video/webm", ext: "webm", test: (b) => b[0] === 0x1a && b[1] === 0x45 && b[2] === 0xdf && b[3] === 0xa3 },
  { type: "audio/mpeg", ext: "mp3", test: (b) => ascii(b, 0, 3) === "ID3" },
  { type: "audio/ogg", ext: "ogg", test: (b) => ascii(b, 0, 4) === "OggS" },
  { type: "application/pdf", ext: "pdf", test: (b) => ascii(b, 0, 4) === "%PDF" },
];

function ascii(bytes, start, end) {
  return String.fromCharCode(...bytes.slice(start, end));
}

/**
 * Give files with no recognised type (usually no extension) their real type
 * and extension, so they preview and upload as what they are.
 */
export async function normalizeFiles(files) {
  return Promise.all(
    files.map(async (file) => {
      if (file.type && file.type !== "application/octet-stream") return file;
      try {
        const bytes = new Uint8Array(await file.slice(0, 16).arrayBuffer());
        const match = SIGNATURES.find((sig) => sig.test(bytes));
        if (!match) return file;
        const hasExt = /\.[a-z0-9]{2,5}$/i.test(file.name);
        const name = hasExt ? file.name : `${file.name}.${match.ext}`;
        return new File([file], name, { type: match.type, lastModified: file.lastModified });
      } catch {
        return file;
      }
    }),
  );
}

/** Programmatically open a hidden <input type="file"> by id. */
export function openFilePicker(id) {
  document.getElementById(id)?.click();
}
