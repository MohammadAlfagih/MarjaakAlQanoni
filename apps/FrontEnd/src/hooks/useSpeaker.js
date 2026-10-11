import { useEffect, useRef, useState } from "react";

// Plays an answer out loud.
// 1) If the backend sent an audio_url (real TTS), play that file.
// 2) Otherwise fall back to the browser's built-in voice (speechSynthesis).

function findVoice(lang) {
  const voices = window.speechSynthesis?.getVoices() || [];
  return voices.find((v) => v.lang?.toLowerCase().startsWith(lang)) || null;
}

/** True if this browser can read text aloud in `lang` ("ar" | "en"). */
export function useCanSpeak(lang) {
  const [can, setCan] = useState(() => !!(window.speechSynthesis && findVoice(lang)));
  useEffect(() => {
    if (!window.speechSynthesis) return;
    const update = () => setCan(!!findVoice(lang));
    update();
    window.speechSynthesis.addEventListener?.("voiceschanged", update);
    return () => window.speechSynthesis.removeEventListener?.("voiceschanged", update);
  }, [lang]);
  return can;
}

export function useSpeaker() {
  const [playingId, setPlayingId] = useState(null);
  const audio = useRef(null);

  const stop = () => {
    audio.current?.pause();
    audio.current = null;
    window.speechSynthesis?.cancel();
    setPlayingId(null);
  };

  useEffect(() => stop, []);

  /** id: message id, text: answer text, lang: "ar" | "en", url: optional audio_url */
  function play({ id, text, lang, url }) {
    stop();
    if (url) {
      const a = new Audio(url);
      audio.current = a;
      a.onended = a.onerror = () => setPlayingId(null);
      a.play().then(() => setPlayingId(id)).catch(() => setPlayingId(null));
      return;
    }
    if (!window.speechSynthesis) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang === "ar" ? "ar-SA" : "en-US";
    const v = findVoice(lang);
    if (v) u.voice = v;
    u.onend = u.onerror = () => setPlayingId(null);
    window.speechSynthesis.speak(u);
    setPlayingId(id);
  }

  return { playingId, play, stop };
}
