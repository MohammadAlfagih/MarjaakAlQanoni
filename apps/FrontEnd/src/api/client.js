// ─────────────────────────────────────────────────────────────
// The ONLY file that talks to the backend.
// Set VITE_USE_MOCK=false in .env to use the real API (apps/api).
// The full contract is documented in README.md.
// ─────────────────────────────────────────────────────────────
import * as mock from "./mock";

const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";
const BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export const isMock = USE_MOCK;

// ngrok's free tunnel otherwise serves an HTML warning for browser requests.
const TUNNEL_HEADERS = /^https:\/\/[^/]+\.ngrok(?:-free)?\.(?:app|dev|io)(?:\/|$)/.test(BASE)
  ? { "ngrok-skip-browser-warning": "1" }
  : {};

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    ...options,
    headers: { ...TUNNEL_HEADERS, ...options.headers },
  });
  if (!res.ok) {
    // FastAPI errors look like {"detail": "..."}; keep the reason for the UI.
    const text = await res.text().catch(() => "");
    let detail = text;
    try {
      const d = JSON.parse(text).detail;
      detail = typeof d === "string" ? d : JSON.stringify(d);
    } catch { /* not JSON */ }
    const err = new Error(`${res.status} ${detail}`.trim());
    err.status = res.status;
    err.detail = detail.slice(0, 300);
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

/** GET /companies → [{ id, name }] */
export function getCompanies() {
  return USE_MOCK ? mock.getCompanies() : request("/companies");
}

/**
 * POST /chat
 * body: { question, role, company_id (nullable), lang, history: [{ role: "user"|"assistant", content }] }
 * → ChatResponse (see README)
 */
export function sendQuestion({ question, role, company_id, lang, history }) {
  if (USE_MOCK) return mock.sendQuestion({ question, role, company_id, lang, history });
  return request("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, role, company_id, lang, history }),
  });
}

/**
 * POST /voice  (multipart/form-data)
 * fields: audio (file), role, company_id, lang, history (JSON string)
 * → ChatResponse + { transcript, audio_url }
 */
export function sendVoice({ audio, role, company_id, lang, history }) {
  if (USE_MOCK) return mock.sendVoice({ audio, role, company_id, lang, history });
  const form = new FormData();
  const ext = audio.type.includes("mp4") ? "m4a" : audio.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", audio, `question.${ext}`);
  form.append("role", role);
  if (company_id) form.append("company_id", company_id);
  form.append("lang", lang);
  form.append("history", JSON.stringify(history));
  return request("/voice", { method: "POST", body: form });
}

/** POST /tts { text, lang } → { audio_url } (server voice for any answer) */
export async function speak(text, lang) {
  if (USE_MOCK) return { audio_url: null };
  return request("/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, lang }),
  });
}

/** GET /policies?company_id= → [{ id, filename, size, uploaded_at }] */
export function getPolicies(company_id) {
  if (USE_MOCK) return mock.getPolicies(company_id);
  return request(`/policies?company_id=${encodeURIComponent(company_id)}`);
}

/** POST /policies (multipart: file, company_id) → { id, filename, size, uploaded_at } */
export function uploadPolicy(company_id, file) {
  if (USE_MOCK) return mock.uploadPolicy(company_id, file);
  const form = new FormData();
  form.append("file", file);
  form.append("company_id", company_id);
  return request("/policies", { method: "POST", body: form });
}

/** DELETE /policies/{id} */
export function deletePolicy(id) {
  if (USE_MOCK) return mock.deletePolicy(id);
  return request(`/policies/${encodeURIComponent(id)}`, { method: "DELETE" });
}

/** Turns a relative audio_url from the backend into a full URL. */
export function resolveAudioUrl(url) {
  if (!url) return null;
  return /^(https?:|blob:|data:)/.test(url) ? url : BASE + url;
}

/**
 * Downloads the spoken answer and returns a local blob: URL for <audio>.
 * (An <audio src> on an ngrok link can't send the bypass header and gets HTML.)
 */
export async function fetchAudio(url) {
  const res = await fetch(url, { headers: TUNNEL_HEADERS });
  const type = res.headers.get("content-type") || "";
  if (!res.ok || !type.startsWith("audio/")) throw new Error(`audio ${res.status} ${type}`);
  return URL.createObjectURL(await res.blob());
}
