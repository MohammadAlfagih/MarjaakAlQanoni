import { useApp } from "../context/AppContext";
import { AlertIcon, BlockIcon, QuestionIcon, SpeakerIcon, StopIcon } from "./Icons";

// Renders one assistant reply. `msg` is the API ChatResponse plus an `id`.
export default function AnswerCard({ msg, playing, onPlay, onStop, canSpeak }) {
  const { t, session } = useApp();
  const { status, answer, articles = [], next_steps = [], conflict } = msg;

  let head = null;
  if (status === "clarify") head = { cls: "clarify", icon: <QuestionIcon />, text: t.clarifyTitle };
  else if (status === "out_of_scope") head = { cls: "out_of_scope", icon: <BlockIcon />, text: t.outOfScopeTitle };
  else if (status === "unknown") head = { cls: "unknown", icon: <QuestionIcon />, text: t.unknownTitle };
  else if (conflict) head = { cls: "conflict", icon: <AlertIcon />, text: t.conflictTitle };

  const cardCls = ["answer", status === "clarify" && "clarify", conflict && status !== "clarify" && "conflict"]
    .filter(Boolean).join(" ");
  const showSpeaker = msg.audio_url || canSpeak;

  return (
    <article className={cardCls} lang={msg.lang} dir={msg.lang === "ar" ? "rtl" : "ltr"}>
      {head && <div className={`answer-head ${head.cls}`}>{head.icon}{head.text}</div>}

      <p className="answer-text">{answer}</p>

      {articles.length > 0 && (
        <>
          <div className="section-label">{t.articles}</div>
          {articles.map((a, i) => (
            <div key={i} className={`citation ${a.source === "policy" ? "policy" : ""}`}>
              <div className="citation-ref">
                {a.ref}
                <span className="citation-src">
                  {a.source === "policy" ? `· ${session?.company_name || ""}` : ""}
                </span>
              </div>
              {a.quote && <q>{a.quote}</q>}
            </div>
          ))}
        </>
      )}

      {next_steps.length > 0 && (
        <>
          <div className="section-label">{session?.role === "hr" ? t.hrNextSteps : t.nextSteps}</div>
          <ol className="steps">
            {next_steps.map((s, i) => <li key={i}>{s}</li>)}
          </ol>
        </>
      )}

      {showSpeaker && (
        <div className="answer-actions">
          {playing ? (
            <button className="chip-btn" onClick={onStop}><StopIcon width={14} height={14} />{t.stopAnswer}</button>
          ) : (
            <button className="chip-btn" onClick={onPlay}><SpeakerIcon />{t.playAnswer}</button>
          )}
        </div>
      )}
    </article>
  );
}
