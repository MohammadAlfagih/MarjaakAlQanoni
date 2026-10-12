import { useEffect, useRef, useState } from "react";
import { useApp } from "../context/AppContext";
import { resolveAudioUrl, sendQuestion, sendVoice } from "../api/client";
import { isRecordingSupported, useRecorder } from "../hooks/useRecorder";
import { useCanSpeak, useSpeaker } from "../hooks/useSpeaker";
import AnswerCard from "../components/AnswerCard";
import { MicIcon, PlusIcon, SendIcon, StopIcon, XIcon } from "../components/Icons";

let seq = 0;
const newId = () => `m${++seq}`;

// History sent to the API: [{ role, content, status? }]
const toHistory = (messages) =>
  messages.map((m) =>
    m.role === "user" ? { role: "user", content: m.text } : { role: "assistant", content: m.answer, status: m.status }
  );

// Shows the server's reason (e.g. "502: The LLM returned an invalid structured answer").
function errorText(e, t) {
  if (!e?.status) return `${t.errorGeneric} (${t.serverUnreachable})`;
  return `${t.errorGeneric} (${e.status}${e.detail ? ": " + e.detail : ""})`;
}

export default function Chat() {
  const { t, lang, session } = useApp();
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(null); // null | "thinking" | "transcribing"
  const [error, setError] = useState("");
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const speaker = useSpeaker();
  const canSpeak = { ar: useCanSpeak("ar"), en: useCanSpeak("en") };
  const recorder = useRecorder((blob) => submitVoice(blob));

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  // grow the textarea with its content
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [text]);

  const base = () => ({ role: session.role, company_id: session.company_id || null, lang, history: toHistory(messages) });

  async function submitText(question) {
    const q = question.trim();
    if (!q || busy) return;
    setError("");
    setText("");
    const payload = base();
    setMessages((m) => [...m, { id: newId(), role: "user", text: q }]);
    setBusy("thinking");
    try {
      const res = await sendQuestion({ ...payload, question: q });
      setMessages((m) => [...m, { id: newId(), role: "assistant", ...res }]);
    } catch (e) {
      console.error(e);
      setError(errorText(e, t));
    } finally {
      setBusy(null);
      inputRef.current?.focus();
    }
  }

  async function submitVoice(blob) {
    setError("");
    const payload = base();
    const userId = newId();
    setMessages((m) => [...m, { id: userId, role: "user", text: "…", via: "voice" }]);
    setBusy("transcribing");
    try {
      const res = await sendVoice({ ...payload, audio: blob });
      const botId = newId();
      setMessages((m) => [
        ...m.map((x) => (x.id === userId ? { ...x, text: res.transcript || "…" } : x)),
        { id: botId, role: "assistant", ...res },
      ]);
      // Voice in → voice out
      speaker.play({ id: botId, text: res.answer, lang: res.lang || lang, url: resolveAudioUrl(res.audio_url) });
    } catch (e) {
      console.error(e);
      setMessages((m) => m.filter((x) => x.id !== userId));
      setError(errorText(e, t));
    } finally {
      setBusy(null);
    }
  }

  async function startRecording() {
    setError("");
    speaker.stop();
    try {
      await recorder.start();
    } catch (e) {
      setError(e.code === "unsupported" ? t.micUnsupported : t.micDenied);
    }
  }

  async function stopRecording() {
    const blob = await recorder.stop();
    if (!blob) return setError(t.tooShort);
    submitVoice(blob);
  }

  function newChat() {
    speaker.stop();
    setMessages([]);
    setError("");
  }

  const suggestions = session.role === "hr" ? t.suggestionsHr : t.suggestionsEmployee;
  const recording = recorder.state === "recording";
  const mmss = `${Math.floor(recorder.seconds / 60)}:${String(recorder.seconds % 60).padStart(2, "0")}`;

  return (
    <main className="chat">
      <div className="chat-scroll" ref={scrollRef}>
        <div className="chat-inner">
          {messages.length === 0 && (
            <div className="empty">
              <h2>{t.chatEmptyTitle}</h2>
              <p>{t.chatEmptyText}</p>
              <div className="suggestions">
                {suggestions.map((s) => (
                  <button key={s} className="suggestion" onClick={() => submitText(s)}>{s}</button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m) => {
            if (m.role === "user") {
              return (
                <div key={m.id} className="msg-user">
                  <div className="bubble-user">{m.text}</div>
                  {m.via === "voice" && <div className="voice-tag"><MicIcon width={14} height={14} />{t.youSaid}</div>}
                </div>
              );
            }
            return (
              <AnswerCard
                key={m.id}
                msg={m}
                canSpeak={canSpeak[m.lang] ?? canSpeak[lang]}
                playing={speaker.playingId === m.id}
                onPlay={() => speaker.play({ id: m.id, text: m.answer, lang: m.lang || lang, url: resolveAudioUrl(m.audio_url) })}
                onStop={speaker.stop}
              />
            );
          })}

          {busy && (
            <div className="thinking">
              <span className="dots"><i /><i /><i /></span>
              {busy === "transcribing" ? t.transcribing : t.thinking}
            </div>
          )}
          {error && <div className="error" role="alert">{error}</div>}
        </div>
      </div>

      <div className="composer-wrap">
        <div className="composer">
          <div className="composer-box">
            {recording ? (
              <>
                <div className="recording-bar">
                  <span className="rec-dot" />
                  <span className="rec-time">{mmss}</span>
                  <span className="rec-label">{t.recording}</span>
                </div>
                <button className="icon-btn" onClick={recorder.cancel} aria-label={t.cancelRecording} title={t.cancelRecording}>
                  <XIcon />
                </button>
                <button className="send-btn" onClick={stopRecording} aria-label={t.stopRecording} title={t.stopRecording}>
                  <StopIcon />
                </button>
              </>
            ) : (
              <>
                <textarea
                  ref={inputRef}
                  rows={1}
                  value={text}
                  placeholder={t.inputPlaceholder}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                      e.preventDefault();
                      submitText(text);
                    }
                  }}
                  aria-label={t.inputPlaceholder}
                />
                <button
                  className="icon-btn"
                  onClick={startRecording}
                  disabled={!!busy || !isRecordingSupported()}
                  aria-label={t.record}
                  title={isRecordingSupported() ? t.record : t.micUnsupported}
                >
                  <MicIcon />
                </button>
                <button className="send-btn" onClick={() => submitText(text)} disabled={!text.trim() || !!busy} aria-label={t.send}>
                  <SendIcon className="flip" />
                </button>
              </>
            )}
          </div>
          <div className="composer-meta">
            <span>{t.asRole} {session.role === "hr" ? t.roleHr : t.roleEmployee} · {session.company_name || t.lawOnly}</span>
            {messages.length > 0 && (
              <button className="chip-btn" onClick={newChat}><PlusIcon />{t.newChat}</button>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
