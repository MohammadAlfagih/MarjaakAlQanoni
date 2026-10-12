// ─────────────────────────────────────────────────────────────
// The ONLY file that talks to the backend.
// Set VITE_USE_MOCK=false in .env to use the real API (apps/api).
// The full contract is documented in README.md.
// ─────────────────────────────────────────────────────────────
import * as mock from "./mock";

const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";
const BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export const isMock = USE_MOCK;

async function request(path, options = {}) {
  // ngrok's free tunnel otherwise serves an HTML warning for browser requests.
  const tunnelHeaders = /^https:\/\/[^/]+\.ngrok(?:-free)?\.(?:app|dev|io)(?:\/|$)/.test(BASE)
    ? { "ngrok-skip-browser-warning": "1" }
    : {};
  const res = await fetch(BASE + path, {
    ...options,
    headers: { ...tunnelHeaders, ...options.headers },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${text}`.trim());
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
