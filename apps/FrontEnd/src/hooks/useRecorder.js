import { useEffect, useRef, useState } from "react";

// Records microphone audio with the browser's MediaRecorder and returns a Blob.
// Works in Chrome, Edge, Firefox and Safari. Needs http://localhost or https.

const MIME_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
const MAX_SECONDS = 60;
const MIN_MS = 700;

function pickMimeType() {
  if (typeof MediaRecorder === "undefined" || !MediaRecorder.isTypeSupported) return "";
  return MIME_TYPES.find((t) => MediaRecorder.isTypeSupported(t)) || "";
}

export function isRecordingSupported() {
  return (
    typeof window !== "undefined" &&
    window.isSecureContext &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== "undefined"
  );
}

/** onAutoStop(blob) is called if recording hits the 60s limit by itself. */
export function useRecorder(onAutoStop) {
  const autoStopRef = useRef(onAutoStop);
  autoStopRef.current = onAutoStop;
  const [state, setState] = useState("idle"); // idle | recording
  const [seconds, setSeconds] = useState(0);
  const recorder = useRef(null);
  const stream = useRef(null);
  const chunks = useRef([]);
  const startedAt = useRef(0);
  const timer = useRef(null);
  const resolveStop = useRef(null);

  const cleanup = () => {
    clearInterval(timer.current);
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    recorder.current = null;
    setState("idle");
    setSeconds(0);
  };

  useEffect(() => cleanup, []);

  /** Starts recording. Throws an Error with code "unsupported" | "denied" | "nomic". */
  async function start() {
    if (!isRecordingSupported()) throw Object.assign(new Error("unsupported"), { code: "unsupported" });
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      const code = e?.name === "NotFoundError" ? "nomic" : "denied";
      throw Object.assign(new Error(code), { code });
    }
    const mimeType = pickMimeType();
    const rec = new MediaRecorder(stream.current, mimeType ? { mimeType } : undefined);
    chunks.current = [];
    rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
    rec.onstop = () => {
      const blob = new Blob(chunks.current, { type: rec.mimeType || mimeType || "audio/webm" });
      const duration = Date.now() - startedAt.current;
      cleanup();
      const result = duration < MIN_MS ? null : blob;
      if (resolveStop.current) resolveStop.current(result);
      else if (result) autoStopRef.current?.(result);
      resolveStop.current = null;
    };
    recorder.current = rec;
    startedAt.current = Date.now();
    rec.start();
    setState("recording");
    timer.current = setInterval(() => {
      const s = Math.floor((Date.now() - startedAt.current) / 1000);
      setSeconds(s);
      if (s >= MAX_SECONDS) recorder.current?.stop();
    }, 250);
  }

  /** Stops and resolves with the audio Blob (or null if it was too short / cancelled). */
  function stop() {
    return new Promise((resolve) => {
      if (!recorder.current) return resolve(null);
      resolveStop.current = resolve;
      recorder.current.stop();
    });
  }

  function cancel() {
    resolveStop.current = null;
    if (recorder.current) {
      recorder.current.onstop = null;
      recorder.current.stop();
    }
    cleanup();
  }

  return { state, seconds, start, stop, cancel };
}
