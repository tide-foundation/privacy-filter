# Architecture audit — 1 October 2026

This records the baseline before the guest/history changes. The working tree, rather than older Next.js commits, is authoritative.

## Runtime and frontend

FastAPI serves Vite's `dist/` and `/api/service/*`. React's `src/App.tsx` owns upload, settings, polling, preview and the file list; `src/globals.css` contains the existing black-and-white design. Fonts and branding are local assets. Node runs only in development and the Docker frontend build stage. Production has one Uvicorn process and one inference thread.

Compose exposes `127.0.0.1:3001`, binds `./data` to `/app/data`, and mounts the independent `redacted-model` volume at `/models`. The approximately 1.7 GB runtime excludes the approximately 2.8 GB model. Startup validates the checkpoint and tokenizer cache, downloads missing assets, then enables offline model use. The model loads lazily and remains in memory. Keep one Uvicorn worker.

## Routes and storage before migration

| Route under `/api/service` | Baseline behavior |
| --- | --- |
| `GET /health` | Model installation/loading status |
| `GET /documents` | All documents, without ownership |
| `POST /documents` | Raw PDF/DOCX body; mode, type and sensitivity query parameters |
| `GET /documents/{id}/preview` | Generated text |
| `GET /documents/{id}/download/{extension}` | Generated PDF/DOCX/TXT |
| `DELETE /documents/{id}` | Delete record and outputs; active jobs cannot be deleted |

`data/documents.sqlite3` has one `documents` table: `id`, `created`, `mode`, `status`, `counts`, `error`, `warning`, `sensitivity`, `source_type`, `layout_preserved`. There are no sessions, owners or expiry times. Outputs persist indefinitely at `data/<UUID>/sanitized.{pdf,docx,txt}`. `data/.calibration` contains only decoder biases. Source filenames are not saved.

Uploads are buffered in RAM and parsed from bytes. Originals, detected values and replacement mappings are not deliberately saved. Export first writes clean text-derived outputs, then attempts a matching-format `.native` temporary file and atomically replaces that output on success. Partial native files are removed on failure. Startup marks interrupted jobs failed and removes their folders, but completed outputs have no expiry.

Local Host/Origin checks, cross-site rejection, UUID validation, safe errors, isolated static files and `Cache-Control: no-store` exist. They do not substitute for document ownership. Global listing and UUID-only access are the principal lifecycle gaps.

## Pipeline and fidelity

Admission is bounded to three jobs; a single thread serializes inference. Load PDF/DOCX → extract canonical text → OPF detection using selected calibration → require exact text alignment → construct one replacement/edit plan → generate all three outputs → attempt native matching-format export → save summary. A graceful shutdown waits for admitted work.

DOCX edits existing XML text nodes and retains runs, tables, headers, footers and images. It strips document properties, historical/deleted text, comments, field instructions, custom XML and external destinations; unsupported embedded content is rejected. Cross-run replacements inherit the first run's styling and can reflow.

PDF maps canonical character offsets to glyph geometry, removes detected glyphs with actual redactions and inserts replacements. Geometry and unaffected artwork remain. Metadata, annotations, links, attachments, scripts and bookmarks are removed. Rotated spans or replacements that cannot fit legibly trigger the existing clean rewrite. Images are not scanned; scanned pages require OCR outside this application. Existing input and expansion limits remain.

The pinned OPF `DetectedSpan` exposes label, start, end, text and placeholder. It supplies no supported per-detection confidence score. Sensitivity is a decoder setting, not an accuracy/confidence percentage.

## Verification and differences from the brief

Baseline: **44 backend tests pass**, TypeScript/Vite build succeeds, and both browser regression scripts pass against the running app. Existing fidelity tests cover native DOCX styling/tables/headers/images, PDF geometry/artwork, metadata removal, cross-run spans and partial-native-export fallback. These tests remain the regression baseline.

The runtime matches the brief. The missing features are guest isolation/cleanup, owned history, opaque protected storage, structured manifests, objective scan reports, review/onboarding UI, and actual authentication/encryption. `/secure-history` also needs explicit static entry-point routing; arbitrary SPA paths are not currently served.

Existing unowned documents are explicitly disposable. Migration must remove them rather than assign them to a guest or the first signed-in person. Preserve the model volume. See [the storage decision](adr/001-secure-history-storage.md) and [implementation status](secure-history.md).
