# مرجعك القانوني — Frontend

React + Vite web app for the Saudi Labor Law assistant.

Pages: **Landing** · **Login** (role + company) · **Chat** (text + voice) · **Policies** (HR only).
Arabic (RTL) by default, with an English toggle.

## Run it

Needs Node.js 18+.

```bash
cd apps/FrontEnd
npm install
cp .env.example .env      # Windows: copy .env.example .env
npm run dev
```

Open http://localhost:5173

By default it runs on **mock data** (`VITE_USE_MOCK=true`), so it works without the backend.
To connect the real API, edit `.env`:

```
VITE_USE_MOCK=false
VITE_API_URL=http://localhost:8000
```

Then restart `npm run dev`. The backend must allow CORS from `http://localhost:5173`.

The Qwen/RAG text-chat backend can now run locally or in Colab using the same
Python files. See [backend setup](../api/README.md). For Colab, use the HTTPS
tunnel URL as `VITE_API_URL`; keep the request functions below unchanged.
The real backend supports companies, text chat and PDF/DOCX/TXT company-policy
management. Voice remains to be implemented.

## Where things are

```
src/
├── api/client.js      ← the only file that calls the backend
├── api/mock.js        ← fake answers used while the backend isn't ready
├── pages/             ← Landing, Login, Chat, Policies
├── components/        ← AnswerCard, Header, Icons
├── hooks/             ← useRecorder (mic), useSpeaker (play answers)
├── i18n/strings.js    ← all UI text, Arabic + English
└── context/           ← language + session (role, company)
```

## Voice

- **Recording:** the browser records the mic (`MediaRecorder`) and sends the audio file to `POST /voice`. The backend does speech-to-text.
- **Playback:** if the backend returns `audio_url`, the app plays it. If `audio_url` is `null`, the app reads the answer with the browser's built-in voice. The "Listen" button is hidden if the browser has no voice for that language.
- The mic only works on `http://localhost` or `https://` (browser rule).
- Audio format depends on the browser: `audio/webm` (Chrome, Edge, Firefox) or `audio/mp4` (Safari). The backend should accept both (e.g. Whisper handles both).

---

## API contract (for `apps/api`)

All JSON responses. `role` is `"employee"` or `"hr"`. `lang` is `"ar"` or `"en"`.

### `GET /companies`
```json
[{ "id": "c_101", "name": "شركة النخبة للتقنية" }]
```

### `POST /chat`
Request:
```json
{
  "question": "كم يوم إجازتي السنوية؟",
  "role": "employee",
  "company_id": "c_101",
  "lang": "ar",
  "history": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "...", "status": "clarify" }
  ]
}
```
Response (`ChatResponse`):
```json
{
  "answer": "تستحق إجازة سنوية لا تقل عن 21 يوم…",
  "articles": [
    { "ref": "المادة 109", "source": "law", "quote": "يستحق العامل…" },
    { "ref": "سياسة الإجازات - بند 3", "source": "policy", "quote": "يمنح الموظف…" }
  ],
  "next_steps": ["راجع رصيد إجازاتك مع الموارد البشرية"],
  "conflict": false,
  "status": "answered",
  "lang": "ar"
}
```

| Field | Meaning |
|---|---|
| `articles[].source` | `"law"` = Labor Law, `"policy"` = this company's policy |
| `conflict` | `true` if a company policy conflicts with the law |
| `status` | `answered` · `out_of_scope` · `unknown` (no relevant article found) · `clarify` (asking the user about their contract before answering) |
| `lang` | language of the answer (should match the question) |

When `status` is `clarify`, the user's next message is their reply; the backend sees it in `history`.

### `POST /voice` (multipart/form-data)
Fields: `audio` (file), `role`, `company_id`, `lang`, `history` (JSON string).
Response: `ChatResponse` plus:
```json
{ "transcript": "راتبي متأخر شهرين، وش أسوي؟", "audio_url": "/audio/abc.mp3" }
```
`audio_url` can be `null` (the app then uses the browser voice). A relative URL is joined with `VITE_API_URL`.

### `GET /policies?company_id=c_101`
```json
[{ "id": "p1", "filename": "سياسة الإجازات.pdf", "size": 245000, "uploaded_at": "2026-10-01T09:12:00Z" }]
```

### `POST /policies` (multipart/form-data)
Fields: `file` (PDF, DOCX or TXT, max 10 MB), `company_id`. Returns one policy object (same shape as above).

### `DELETE /policies/{id}`
Returns `204` (or `200` with any JSON).

---

Note: the article numbers and texts in `mock.js` are placeholders for the demo. Real answers come from the RAG backend.
