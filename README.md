# Redacted

A local app for masking, labelling or replacing sensitive text in PDF and Word documents with [OpenAI Privacy Filter](https://github.com/openai/privacy-filter). React is built into static files with Vite; one FastAPI server serves the interface, handles documents and runs the model. Production needs no Node server, paid API or cloud inference.

## Run with Docker

Install Docker with Compose, then run from the repository root:

```bash
mkdir -p data/guest
docker compose up --build -d
```

Open **http://localhost:3001**. Follow startup progress with `docker compose logs -f app`. On first start, the app downloads the model and tokenizer into the persistent `redacted-model` Docker volume. The page becomes available after those assets are ready; model inference loads into RAM on the first document and stays loaded.

Subsequent starts validate and reuse the cached assets without checking Hugging Face for updates. Missing or incomplete assets are downloaded again. The model is separate from the application image, so rebuilding the app does not download or embed another copy. Dependency installation and the first model download need internet; processing uses local assets and enables Hugging Face offline mode after initialization.

Updates use the same `docker compose up --build -d` command. `docker compose stop` stops the app. Preserve both `data/` and the model volume when updating or moving the installation.

The container runs as UID/GID 1000 by default. On Linux, if your account uses different IDs, use these build settings so the app can write to your `data/` directory:

```bash
LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)" docker compose up --build -d
```

Copy `.env.example` to `.env` to keep overrides such as `REDACTED_PORT`, `LOCAL_UID` and `LOCAL_GID`. The port is published only on `127.0.0.1`. Docker runs a single Python worker on internal port 8000. Node is used only in the frontend build stage; development tools and model weights are excluded from the runtime image.

### Reuse a model already downloaded in this checkout

If `models/privacy-filter/` already contains its `original/` checkpoint and `tiktoken/` cache, copy them into the volume before first startup to avoid another download:

```bash
docker compose build
docker compose run --rm --no-deps --entrypoint python \
  --volume "$(pwd)/models/privacy-filter:/seed:ro" \
  app -c 'import shutil; shutil.copytree("/seed", "/models/privacy-filter", dirs_exist_ok=True)'
docker compose up -d
```

Startup validates the copied assets. Use the same UID/GID overrides for these commands if you customized them.

## Use the app

Choose a PDF or DOCX, then press **REDACT**. **Settings** expands to show sensitivity and three modes:

| Mode | Replacement |
| --- | --- |
| **Mask** (default) | Six asterisks (`******`) per detected span; dates always use `**/**/**`. Length and date format do not depend on the original text. |
| **Label** | Category labels such as `[Name]`, `[Date]` and `[Phone Number]`. |
| **Replace** | Consistent fictional values within the document. |

Guest mode works immediately, without an account or TideCloak. Each browser session has **one current document**, with a text preview and PDF, DOCX and TXT downloads. A new upload replaces the finished result. Trashing asks for confirmation and removes temporary results. Results expire after one hour and disappear on server restart; polling does not extend their lifetime. Guest filenames are kept only in session memory and shown in the result list. While processing, an animated black redaction bar sweeps over the filename.

**Review detections** shows concealed detection summaries and an objective scan report: settings, categories, counts, native layout versus rewrite, and text/image limitations. Values start covered by black bars. One **Reveal values** button fetches all original values for the current review; **Hide values** conceals them together. Column widths remain fixed, with long values wrapping inside their column. Originals stay in temporary memory and clear on close, expiry or session change. Exact character spans are excluded from this interface.

The **user icon** opens the secure-history information page while Tide is unconfigured. Its prepared account menu shows Sign in or Sign out when a real provider is available. The owner-scoped storage and UI boundaries are prepared, but actual sign-in, encryption, saving and protected-history revelation remain unavailable until the final Raziel-guided TideCloak integration. Both guest use and the planned secure-history mode are free. There is no demo account or plaintext encryption fallback. See [implementation status and API boundaries](docs/secure-history.md).

All eight model categories are used: `private_person`, `private_address`, `private_email`, `private_phone`, `private_date`, `private_url`, `account_number` and `secret`. The model identifies spans; the app applies the selected replacements. Exact alignment between model input and returned text is required before any output is saved.

## Storage and processing

| Content | Host location with Compose | Container location |
| --- | --- | --- |
| Owned history metadata and opaque protected artifacts (prepared; disabled until integration) | `data/documents.sqlite3` | `/app/data/documents.sqlite3` |
| Temporary guest outputs | Memory-backed tmpfs, up to 512 MiB | `/app/data/guest/<document-id>/` |
| Guest sessions, filenames and full detection manifests | Process memory only | Python process memory |
| Sensitivity calibration values (no document content) | `data/.calibration/` | `/app/data/.calibration/` |
| Model and tokenizer | Docker volume `redacted-model` | `/models/privacy-filter/` |

The model and durable database survive restarts. Guest documents do not. Direct Python uses `data/guest/` on the filesystem, with replacement, deletion, expiration and startup cleanup; use an appropriately protected temporary filesystem if needed. `PRIVACY_DATA_DIR` overrides the root. Model files and documents are ignored by Git. Docker's tmpfs is temporary but can be swapped by the host; it does not promise forensic erasure ([Docker documentation](https://docs.docker.com/engine/storage/tmpfs/)).

Original uploads are held temporarily in process memory and are not intentionally written as source files. Full manifests contain detected original values and exact edits, but remain in bounded temporary memory. Only generated outputs are written to the guest workspace. **Model misses, images and confidential body content can remain in those outputs.** Review before sharing; detection does not guarantee anonymization.

The planned durable architecture retains the original, manifest and cached outputs as separately encrypted artifacts, with mandatory ownership. Outputs will also be encrypted because they may remain confidential. Before real authentication/encryption is connected, every durable-history API fails closed. No manifest or original is saved as a plaintext intermediate shortcut. See [the storage decision and alternatives](docs/adr/001-secure-history-storage.md).

Up to three jobs can be admitted; one worker processes them sequentially and shares one loaded model. One guest cannot submit a second active job. Keep a single Uvicorn worker to avoid duplicated model memory and conflicting sessions/queues. Normal shutdown waits for admitted jobs and clears guest work; Compose allows ten minutes before a forced stop. Expired/reset jobs cannot publish a result after their session has been invalidated.

**Migration:** the old global, unowned document table and its UUID output folders are removed on first startup of this version, as authorized for this installation. They are not reassigned to the first guest/account or silently retained as history. This does not affect `redacted-model`. Deletion is application cleanup, not guaranteed removal from previous backups, snapshots or browser downloads.

No external fonts, analytics or document APIs are used. The app checks local Host and same-origin requests; data and model directories are never served as static files. It is intended for a trusted local machine, not public or shared network deployment.

## Output fidelity and limits

The **matching-format download** attempts to preserve the original document: DOCX for a Word upload, PDF for a PDF upload. The other format is a rebuilt text conversion; TXT and the preview show extracted text. Hover a download button to see which is which. The source file on your machine is never overwritten.

- **Word:** replacements edit existing XML text nodes, retaining paragraph/run styling, page setup, tables, headers, footers, notes, text boxes and images. A replacement spanning differently styled runs inherits the first run's style; longer replacements can reflow lines or pages. Comments, deleted revision text, field instructions, external hyperlink destinations, custom XML and document properties are removed. Embedded objects, macros, charts, SmartArt and embedded HTML are rejected rather than copied without scanning.
- **PDF:** detected glyphs are physically removed by redaction, then replacements are written into their locations. Page geometry and unaffected text/vector artwork remain. Replacement text uses a matching standard font family, style and color, reducing size if necessary; exact embedded-font matching is not guaranteed. If a replacement cannot fit at a legible size (6 pt minimum), uses unsupported rotated text, or native export otherwise fails, the job falls back to a clean text rewrite with a brief note. Native export uses a temporary file, so a partial failure cannot damage the clean outputs. Interactive forms must be flattened first. Metadata, annotations, attachments, scripts, links and bookmarks are removed. Files are saved afresh with garbage collection rather than appended revisions containing old text.
- **Images:** native exports preserve images, which this text-only model does not scan. Documents containing images show a warning. PDF image pixels beneath detected redactions are blanked too, but other sensitive visual information and image metadata can remain. Scanned image-only pages need local OCR first.
- **Limits:** 20 MB per upload, 200,000 extracted characters and 250 PDF pages. Legacy `.doc` files need conversion to `.docx`; encrypted PDFs are unsupported. A rebuilt PDF is also capped at 1,000 output pages.

Layout preservation and clean-rewrite fallback apply to all three modes. Fixed masks conceal the original character count in their replacement text; they do not promise to conceal dimensions or spacing in preserved document layouts.

## Sensitivity and fictional data

Sensitivity is an app-defined 0–100 scale in steps of 5, not a confidence percentage. **50 preserves OPF's default calibration**. Higher values favor more detections and can catch ordinary text too. These settings are not independently validated operating points.

For other values, the app adjusts the checkpoint's Viterbi transition biases using `d = (sensitivity - 50) / 25`: background-stay decreases by `d`, background-to-start increases by `d`, and inside-to-continue increases by `d / 2`. Each temporary result records its selected value and uses a per-call decoder while sharing the model. Calibration files contain only bias values.

Replace mode uses an in-memory map keyed by `(category, original_text.casefold())`; repeated values in the same category receive the same fictional replacement throughout that document, including headers and footers. Templates produce `Alex Example N`, `N Example Street, Sampletown`, reserved example email/URL domains, fictional-range US phone numbers, January 2000 dates, and `DEMO-…` / `SYNTHETIC-…` accounts and secrets. Emails, URLs, accounts and secrets include a random per-document token. The model does not generate these identities.

Templates do not preserve locale, validation checksums, date intervals, identity relationships or name aliases. Dates and phone numbers can cycle and collide for different values. Case differences are ignored; whitespace differences are not. The full manifest retains the exact replacements temporarily for future protected handoff, then is cleared with the working result. Internal mode keys remain `redact`, `placeholder` and `synthetic`.

## Run without Docker

Use Python 3.11, Git and a supported Node.js version (22.12+; 24 recommended). Node is needed to build the frontend, not to serve it. These Bash commands run from the repository root; Windows users can use WSL.

```bash
npm ci
npm run build
python3.11 -m venv .venv
.venv/bin/pip install -c backend/requirements.lock.txt torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -c backend/requirements.lock.txt -r backend/requirements-runtime.txt -r backend/requirements-model.txt
.venv/bin/python scripts/download-model.py

export OPF_CHECKPOINT="$PWD/models/privacy-filter/original"
export TIKTOKEN_CACHE_DIR="$PWD/models/privacy-filter/tiktoken"
export OPF_DEVICE=cpu
export HF_HUB_OFFLINE=1
.venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Open **http://127.0.0.1:8000**. That one Python process serves the built interface and API. The downloader defaults to `models/privacy-filter/` and reuses valid assets on later runs. `PRIVACY_MODEL_DIR` or its `--target` option changes the download destination; point `OPF_CHECKPOINT` and `TIKTOKEN_CACHE_DIR` at the corresponding subdirectories when doing so. `PRIVACY_FRONTEND_DIR` can override the static `dist/` directory.

Python reads shell environment variables; it does not automatically load `.env` or `.env.local`. The supplied dependency constraints reproduce the verified Linux CPU environment. CUDA requires a separately compatible PyTorch/CUDA installation and `OPF_DEVICE=cuda`; the provided image and commands use CPU.

### Frontend development

After the setup above, start Python with one explicitly allowed development origin:

```bash
PRIVACY_DEV_ORIGIN=http://127.0.0.1:5173 \
  .venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

In another terminal, run `npm run dev` and open **http://127.0.0.1:5173**. Vite provides hot reload and proxies `/api/service/*` to port 8000. Use that exact origin; production does not need `PRIVACY_DEV_ORIGIN`. Do not enable Python reload while documents are processing.

## Validation

```bash
npm run build
.venv/bin/pip install -c backend/requirements.lock.txt -r backend/requirements.txt
.venv/bin/python -m pytest backend/tests -q
npx playwright install chromium
# With the Docker app running (use port 8000 for direct Python):
BASE_URL=http://127.0.0.1:3001 npm run test:browser
# Optional real inference smoke check; creates and removes its own sample files:
BASE_URL=http://127.0.0.1:3001 .venv/bin/python scripts/model-smoke.py
```

The build includes TypeScript checks. Browser tests use a fixture API to cover the interface, including file-selection delays, sensitivity, previews, whole-review reveal/hide, filename animation, account menu, onboarding, expiry and confirmed deletion; they do not process real model inputs. Pipeline/API tests inject a deterministic detector and do not measure model accuracy. The separate model smoke script exercises real inference, generated downloads, concealed review and cross-session denial. OPF is pinned to commit `f7f00ca7fb869683eb732c010299d901457f19c3`.

## Possible follow-ups

- Local OCR with explicit page coverage reporting.
- A review step to approve or correct detected spans before export.
- Better PDF font matching and support for rotated text.
- Evaluation of sensitivity settings against representative synthetic documents.

## Architecture records

- [Baseline audit](docs/architecture-audit.md)
- [Storage decision: alternatives A/B/C](docs/adr/001-secure-history-storage.md)
- [Current implementation, API boundaries and remaining Tide integration](docs/secure-history.md)
