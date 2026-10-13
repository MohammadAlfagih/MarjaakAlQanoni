# Marjaak AlQanoni API — Qwen + RAG + Voice

The same Python backend runs on a local machine or a Colab GPU. No project
notebooks are required. The frontend keeps its existing JSON requests.

```text
Frontend POST /chat → retrieve law + selected-company policy evidence → Qwen chat template → generate
→ validate JSON + evidence labels → frontend ChatResponse

Frontend POST /voice → Cohere speech-to-text → the same /chat pipeline → text-to-speech
→ ChatResponse + transcript + audio_url
```

## Local run

From the repository root, with the virtual environment activated:

```powershell
python -m pip install -r apps/api/requirements.txt
python app.py --build-index --preload
```

`--build-index` builds the E5/Chroma law index, or reuses a matching complete
index. It refuses to overwrite a stale/incomplete index; see `services/RAG/README.md`.
`--preload` loads Qwen before accepting requests. Without it, Qwen loads on the
first nonempty-evidence chat request. Downloads happen only when the cache is
missing. These are two separate models: E5 retrieves; Qwen generates the answer.

Open `http://127.0.0.1:8000/docs`. `GET /health` reports whether Qwen is loaded
and the serving process `pid`. For background startup, check that `pid` equals
`server.pid`; a response from an older process does not prove the new one started.
This is a process health check, not an evaluation of retrieval or answer accuracy.
The launcher reserves the port before indexing or preloading, so an occupied
port stops startup before another copy of the models is allocated.

GPU is selected automatically when supported by the installed PyTorch build.
GPU inference uses float16; CPU uses float32 and needs considerably more RAM
and time. Install a CUDA-enabled PyTorch build on a workstation with an NVIDIA
GPU. `LLM_DEVICE=cpu` or `LLM_DEVICE=cuda` can override automatic placement.
Use one server worker to avoid loading multiple copies of the model.

## Colab: upload Python files, then run app.py

Select a GPU runtime (for example T4). Upload **root `app.py` plus the entire
`apps/api/` folder**, including the law PDF and companies.json, preserving paths.
Uploading just the inner `apps/api/app/app.py` is insufficient because it imports
the RAG and LLM services.

For an easy upload, make a backend-only source ZIP locally:

```powershell
python scripts/package_api.py
```

This creates `tmp/marjaak-api.zip`, with no model caches, vector database,
virtual environment, credentials or frontend dependencies. Upload that ZIP
using Colab's Files panel. Then use the following setup commands in Colab cells;
the application itself remains ordinary `.py` files.

```python
from pathlib import Path
from google.colab import files
import io, os, zipfile

root = Path('/content/marjaak-api')
root.mkdir(exist_ok=True)
uploaded = files.upload()
assert len(uploaded) == 1, 'Select the new marjaak-api.zip only'
with zipfile.ZipFile(io.BytesIO(next(iter(uploaded.values())))) as archive:
    for member in archive.infolist():
        if not (root / member.filename).resolve().is_relative_to(root.resolve()):
            raise ValueError('Invalid archive path')
    archive.extractall(root)
os.chdir(root)
```

Install the backend dependencies while preserving Colab's installed CUDA PyTorch:

```python
import subprocess, sys, torch
assert torch.cuda.is_available(), 'Select a GPU runtime first'
dependencies = [
    line.strip()
    for line in Path('apps/api/requirements.txt').read_text().splitlines()
    if line.strip() and not line.startswith(('#', 'torch=='))
]
subprocess.check_call([sys.executable, '-m', 'pip', 'install', *dependencies, 'pyngrok'])
```

The speech model (`CohereLabs/cohere-transcribe-arabic-07-2026`) is gated. Once,
with the Hugging Face account whose token you use, accept its terms on
https://huggingface.co/CohereLabs/cohere-transcribe-arabic-07-2026 and add the
token to Colab 🔑 Secrets as `HF_TOKEN` (Notebook access on). Then, before starting
the server, pass it to the server process:

```python
from google.colab import userdata
os.environ['HF_TOKEN'] = userdata.get('HF_TOKEN')
```

Start the API once in a background process so you can open the tunnel in another
cell. Stop the previous process and wait for it to exit before restarting:

```python
if 'server' in globals() and server.poll() is None:
    raise RuntimeError('The previous server is still running; stop it first')
log = open('/content/marjaak-api.log', 'w')
server = subprocess.Popen(
    [sys.executable, 'app.py', '--build-index', '--preload'],
    stdout=log, stderr=subprocess.STDOUT,
)
print('Server PID:', server.pid)
```

The first run builds the law index and downloads `Qwen/Qwen2.5-3B-Instruct` and the
Cohere speech model; `--preload` loads both before the server accepts requests.
It can take several minutes. Check the log in another cell:

```python
print(Path('/content/marjaak-api.log').read_text()[-5000:])
```

Binding the port is not readiness: wait until `/health` comes from the new PID.
An older server can remain alive if earlier cells overwrote the `server` variable.

```python
import requests, time
for _ in range(180):
    if server.poll() is not None:
        raise RuntimeError(Path('/content/marjaak-api.log').read_text()[-5000:])
    try:
        response = requests.get('http://127.0.0.1:8000/health', timeout=5)
        response.raise_for_status()
        health = response.json()
        if health.get('pid') != server.pid:
            raise RuntimeError('An older backend is answering on port 8000')
        if health.get('stt_error'):
            print('Voice unavailable (chat still works):', health['stt_error'])
        if health.get('llm_loaded') and (health.get('stt_loaded') or health.get('stt_error')):
            print('New backend ready:', health)
            break
    except requests.RequestException:
        pass
    time.sleep(5)
else:
    raise RuntimeError('Startup timed out; inspect the log before restarting')
```

Create an HTTPS tunnel using your own ngrok account token. Enter it privately;
do not put the token in source files:

```python
from getpass import getpass
from pyngrok import ngrok

ngrok.set_auth_token(getpass('ngrok authtoken: '))
tunnel = ngrok.connect(addr='127.0.0.1:8000', proto='http')
print('VITE_API_URL=' + tunnel.public_url)
```

The tunnel and server live only while the Colab runtime stays active. Recreating
the tunnel may change the URL. Stop it when finished:

```python
ngrok.disconnect(tunnel.public_url)
server.terminate()
server.wait(timeout=30)
log.close()
```

## Connect the frontend

Create `apps/FrontEnd/.env` from `.env.example` and set:

```dotenv
VITE_USE_MOCK=false
VITE_API_URL=http://localhost:8000
```

For Colab, replace only `VITE_API_URL` with the printed HTTPS tunnel URL. Do not
append `/chat` or `/docs`. Restart Vite after changing `.env`.

CORS allows `http://localhost:5173` and `http://127.0.0.1:5173` by default.
Set `FRONTEND_ORIGINS` to comma-separated frontend origins if using other ports
or a hosted frontend; these are frontend URLs, not the backend tunnel URL.
The API client adds ngrok's warning-bypass header for ngrok URLs so browser
requests receive JSON rather than an HTML interstitial.

## Implemented API contract

- `GET /companies`: demo company choices from `companies.json` (same IDs as the UI).
- `GET /policies?company_id=...`: list that company's saved policy files.
- `POST /policies`: save and index one PDF, DOCX or UTF-8 TXT policy.
- `DELETE /policies/{id}`: remove the saved file and its cached vectors.
- `POST /chat`: existing frontend request fields: `question`, `role`,
  `company_id`, `lang`, `history`.
- Response: `answer`, `articles`, `next_steps`, `conflict`, `status`, `lang`.
- `POST /chat/evidence`: accepts the same request as `/chat` and runs the same
  retrieval without Qwen. Returns `company_id`, the retrieval `query`, `context`,
  and all retrieved `sources`, before the model selects citations.
- Existing `POST /rag/search` remains available for evidence-only retrieval
  with an optional request-local policy PDF.
- `POST /voice` (multipart): `audio` file plus the `/chat` fields as form fields
  (`history` as a JSON string). Transcribes with Cohere using `lang` (`ar`/`en`;
  the model has no language detection), runs the same pipeline as `/chat`, and
  returns its response plus `transcript` and `audio_url` (`null` if text-to-speech
  failed; the frontend then uses the browser voice).
- `POST /tts` `{text, lang}` → `{audio_url}`: speaks any answer (the "Listen" button).
- `GET /audio/{id}.mp3|wav`: spoken answers, kept for one hour in `apps/api/.data/audio`.
- `GET /health`: model ID, Qwen and speech-model loading status (`llm_loaded`,
  `stt_loaded`, `stt_error`), and serving process `pid`. If the speech model fails
  to load at startup, the API keeps serving `/chat` and `/voice` returns `503`.

Policy files and metadata are persisted in `apps/api/.data/policies.sqlite3` by
default. Policy vectors are not persisted: each upload is embedded once and added
to an `InMemoryVectorStore` for its company. After a server restart, the saved
files remain and each company's vector store is rebuilt lazily on that company's
first chat request. Set `POLICIES_DATA_DIR` to move the on-disk SQLite database.
For Colab, that default directory disappears with the runtime unless you copy it
to persistent storage before shutdown and restore it before startup.

PDF references use page numbers; DOCX references use paragraph/table positions;
TXT references use source line numbers. Text-based PDF is supported up to 40
pages. Scanned PDFs need OCR, which is not implemented. All uploads are limited
to 10,000,000 bytes; expanded DOCX content is also bounded. Exact duplicate
content within one company returns the existing policy record.

`/chat` always searches the selected company's in-memory store for every question,
independent of role or words such as "my company". It passes company-policy (`P`)
and law (`L`) excerpts to Qwen in separate `company_policy_evidence` and
`labor_law_evidence` fields. A generated conflict is accepted only when
the model cites at least one retrieved law source and one retrieved policy source.
The company/role values are demo selections, not authenticated authorization.
This is a development/demo server.

## Voice

| Part | Model | Notes |
|---|---|---|
| Speech → text | Cohere Transcribe Arabic (2B) | GPU; float16 on T4 (~4.5 GB) next to Qwen |
| Text → speech | `edge-tts` (`ar-SA-HamedNeural`, `en-US-AndrewNeural`), then MMS-TTS | edge-tts is refused (403) on Colab, so the API switches to `facebook/mms-tts-ara` / `mms-tts-eng` (open-source, in-process, CC-BY-NC 4.0) |

Code is in `apps/api/voice/`. Browser audio (webm/mp4) is converted with the
ffmpeg bundled in `imageio-ffmpeg`, so nothing extra is installed on Windows.
Optional environment variables: `STT_DTYPE=float32` if transcripts come out empty
or garbled; `TTS_ENGINE=auto|mms|edge`; `TTS_VOICE_AR` / `TTS_VOICE_EN` for edge-tts voices.
MMS reads letters only, so numbers are spelled out (`num2words`) and evidence labels
and diacritics are removed before speaking.
Errors: `422` unreadable/too-short audio or invalid fields; `503` speech model
unavailable (check `HF_TOKEN`, the accepted terms and GPU memory); `/chat` errors
pass through unchanged.

History accepts frontend assistant `status` fields, including `clarify`. Recent
user messages help retrieval understand follow-ups; the latest eight history
messages (up to 2000 characters each) are passed as data to the model. User
history cannot supply system-role messages.

The model returns internal JSON with evidence labels, not source quotations.
The server validates it, rejects unknown references and uncited `answered`
responses, and constructs article names, page references and quotes from RAG's
original sources. This guards the reference structure; it does **not** prove that
every generated statement is legally correct or supported by its citation.

For a law-only answer, compare `/chat/evidence` with `/chat` using the same
question, company and history. Policy sources in the former but no policy
citations in the latter mean the model did not cite the retrieved policies;
they do not mean retrieval returned no policies. If there are no policy sources,
check `GET /policies?company_id=...` and the server's `POLICIES_DATA_DIR`, especially
after restarting Colab. An empty stored-policy list cannot be fixed by prompting.

`422` means invalid input or an oversized prompt, `503` means unavailable
index/model/storage, and `502` means malformed/unsupported model output.

## Verification

```powershell
python -m unittest discover -s tests -v
```

Tests exercise the frontend contract, history, CORS, source integrity, error
handling and generation token slicing without downloading Qwen. For real model
verification on your GPU, submit a question to `/chat` in `/docs`, then test the
same flow through the frontend. The existing opt-in E5 tests remain documented
in `services/RAG/README.md`.

Implementation follows the lab's `AutoTokenizer` + `AutoModelForCausalLM` +
`apply_chat_template` + `generate` approach, using the requested 3B Instruct model:
[Qwen model card](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct),
[Hugging Face chat templates](https://huggingface.co/docs/transformers/v5.19.0/en/chat_templating),
[ngrok browser interstitial](https://ngrok.com/docs/errors/err_ngrok_6024).
