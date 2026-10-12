import { useEffect, useRef, useState } from "react";
import { useApp } from "../context/AppContext";
import { deletePolicy, getPolicies, uploadPolicy } from "../api/client";
import { TrashIcon, UploadIcon } from "../components/Icons";

const MAX_BYTES = 10_000_000;
const ALLOWED = [".pdf", ".docx", ".txt"];

const ext = (name) => name.slice(name.lastIndexOf(".")).toLowerCase();
const sizeLabel = (b) => (b > 1024 * 1024 ? `${(b / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);

// HR uploads the company's own policies. Only this company's employees get answers from them.
export default function Policies() {
  const { t, lang, session } = useApp();
  const [files, setFiles] = useState(null);
  const [pending, setPending] = useState([]);
  const [error, setError] = useState("");
  const [over, setOver] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    getPolicies(session.company_id).then(setFiles).catch(() => setError(t.errorGeneric));
  }, [session.company_id, t.errorGeneric]);

  async function handleFiles(list) {
    setError("");
    for (const file of Array.from(list)) {
      if (!ALLOWED.includes(ext(file.name))) { setError(`${file.name}: ${t.fileBadType}`); continue; }
      if (file.size > MAX_BYTES) { setError(`${file.name}: ${t.fileTooBig}`); continue; }
      const tmp = { id: "tmp-" + file.name + Date.now(), filename: file.name, size: file.size };
      setPending((p) => [tmp, ...p]);
      try {
        const saved = await uploadPolicy(session.company_id, file);
        setFiles((f) => [saved, ...(f || []).filter((existing) => existing.id !== saved.id)]);
      } catch {
        setError(`${file.name}: ${t.errorGeneric}`);
      } finally {
        setPending((p) => p.filter((x) => x.id !== tmp.id));
      }
    }
  }

  async function remove(id) {
    if (!window.confirm(t.confirmDelete)) return;
    try {
      await deletePolicy(id);
      setFiles((f) => f.filter((x) => x.id !== id));
    } catch {
      setError(t.errorGeneric);
    }
  }

  const date = (iso) => new Date(iso).toLocaleDateString(lang === "ar" ? "ar-SA" : "en-GB", { day: "numeric", month: "short", year: "numeric" });

  return (
    <main className="page">
      <h1>{t.policiesTitle}</h1>
      <p>{t.policiesText}</p>

      <div
        className={`dropzone ${over ? "over" : ""}`}
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); handleFiles(e.dataTransfer.files); }}
      >
        <UploadIcon />
        <strong>{t.dropHere}</strong>
        <span>{t.fileTypes}</span>
        <input
          ref={inputRef}
          type="file"
          accept={ALLOWED.join(",")}
          multiple
          hidden
          onChange={(e) => { handleFiles(e.target.files); e.target.value = ""; }}
        />
      </div>

      {error && <p className="error" role="alert" style={{ marginTop: 16 }}>{error}</p>}

      {files === null ? (
        <div className="muted-box">{t.loading}</div>
      ) : files.length + pending.length === 0 ? (
        <div className="muted-box">{t.noPolicies}</div>
      ) : (
        <ul className="files">
          {pending.map((f) => (
            <li key={f.id} className="file pending">
              <div className="file-icon">{ext(f.filename).slice(1).toUpperCase()}</div>
              <div className="file-body">
                <div className="file-name">{f.filename}</div>
                <div className="file-meta">{t.uploading}</div>
              </div>
            </li>
          ))}
          {files.map((f) => (
            <li key={f.id} className="file">
              <div className="file-icon">{ext(f.filename).slice(1).toUpperCase()}</div>
              <div className="file-body">
                <div className="file-name">{f.filename}</div>
                <div className="file-meta">{sizeLabel(f.size)} · {t.uploadedOn} {date(f.uploaded_at)}</div>
              </div>
              <button className="icon-btn" onClick={() => remove(f.id)} aria-label={`${t.delete} ${f.filename}`} title={t.delete}>
                <TrashIcon />
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
