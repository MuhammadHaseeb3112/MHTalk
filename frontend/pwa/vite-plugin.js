/**
 * Tiny Vite plugin (no dependencies) that writes dist/sw.js from pwa/sw.js
 * on `vite build`, filling in:
 *   - a version derived from the build output (new deploy => new cache), and
 *   - the precache list (index.html, offline page, icons, every built file).
 * It does nothing in `vite` dev, so development never runs a service worker.
 */
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const PUBLIC_SHELL = [
  "/index.html",
  "/offline.html",
  "/manifest.webmanifest",
  "/favicon.svg",
  "/pwa-192.png",
  "/pwa-512.png",
  "/pwa-badge-96.png",
  "/apple-touch-icon.png",
];

export default function mhtalkServiceWorker() {
  let outDir = "dist";
  return {
    name: "mhtalk-service-worker",
    apply: "build",
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
    },
    writeBundle(_options, bundle) {
      const built = Object.keys(bundle)
        .filter((file) => !file.endsWith(".map") && file !== "index.html")
        .map((file) => `/${file}`);
      const precache = [...new Set([...PUBLIC_SHELL, ...built])].sort();
      const template = readFileSync(resolve(here, "sw.js"), "utf8");
      const indexHtml = readFileSync(resolve(outDir, "index.html"), "utf8");
      const hash = createHash("sha256").update(template).update(indexHtml).update(precache.join("\n"));
      for (const file of PUBLIC_SHELL) {
        try {
          hash.update(readFileSync(resolve(outDir, `.${file}`)));
        } catch {
          /* optional file */
        }
      }
      const version = hash.digest("hex").slice(0, 12);
      const source = template
        .replace('"__MHTALK_SW_VERSION__"', JSON.stringify(version))
        .replace("[/* __MHTALK_SW_PRECACHE__ */]", JSON.stringify(precache, null, 2));
      writeFileSync(resolve(outDir, "sw.js"), source);
      // "App update" in Settings reads this to tell the user what's new.
      writeFileSync(resolve(outDir, "release-notes.json"), readFileSync(resolve(here, "../src/releaseNotes.json"), "utf8"));
    },
  };
}
