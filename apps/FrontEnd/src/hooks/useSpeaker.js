import { useEffect, useRef, useState } from "react";
import { fetchAudio, isMock, resolveAudioUrl, speak } from "../api/client";

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
  const playToken = useRef(0);

  const stop = () => {
    playToken.current += 1;
    audio.current?.pause();
    audio.current = null;
    window.speechSynthesis?.cancel();
    setPlayingId(null);
  };

  useEffect(() => stop, []);

  function speakWithBrowser(id, text, lang) {
    if (!window.speechSynthesis) return setPlayingId(null);
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang === "ar" ? "ar-SA" : "en-US";
    const v = findVoice(lang);
    if (v) u.voice = v;
    u.onend = u.onerror = () => setPlayingId(null);
    window.speechSynthesis.speak(u);
    setPlayingId(id);
  }

  /** id: message id, text: answer text, lang: "ar" | "en", url: optional audio_url */
  async function play({ id, text, lang, url }) {
    stop();
    if (!url && isMock) return speakWithBrowser(id, text, lang);
    setPlayingId(id);
    const token = (playToken.current += 1);
    try {
      // Typed answers have no audio yet: ask the server to speak them (POST /tts)
      const audioUrl = url || resolveAudioUrl((await speak(text, lang)).audio_url);
      if (token !== playToken.current) return;
      const src = await fetchAudio(audioUrl);
      if (token !== playToken.current) return URL.revokeObjectURL(src); // stopped meanwhile
      const a = new Audio(src);
      audio.current = a;
      a.onended = () => { URL.revokeObjectURL(src); setPlayingId(null); };
      await a.play();
    } catch {
      // Server audio unavailable or autoplay blocked → read it with the browser voice
      if (token === playToken.current) speakWithBrowser(id, text, lang);
    }
  }

  return { playingId, play, stop };
}
