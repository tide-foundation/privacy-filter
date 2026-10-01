# Guest lifecycle and secure-history preparation

## Current status

The application retains the single FastAPI runtime and static React/Vite frontend. Guest isolation, ephemeral working results, manifests, scan reports, owner-scoped opaque persistence and secure-history UI boundaries are implemented as the preparation stages. Real TideCloak authentication and Tide self-encryption/decryption are **not configured**. They must be implemented using Raziel MCP before secure retention can be enabled.

There is no production demo identity, local-account replacement, unverified JWT parser or plaintext encryption fallback. Unauthenticated history requests fail closed; supplying credentials cannot activate a provider. Test dependency overrides supply isolated verified-owner fixtures, never production identities. Current guest operations do not require Tide infrastructure.

## Guest lifecycle

`GET /api/service/guest/current` establishes an opaque random HttpOnly, SameSite=Strict browser-session cookie and returns a CSRF token. The server retains only a digest of the session token. A session can access only its own current job/result. Mutations require the CSRF token as well as the existing local Host/Origin/Fetch Metadata checks. HTTPS adds Secure to the cookie; local HTTP remains supported.

Upload bytes are buffered transiently, then passed through the existing PDF/DOCX detector and renderer. No original source file is deliberately saved. The selected browser `File` can remain in memory for a later protected save, but is never written to localStorage or IndexedDB. Full detection manifests stay in bounded server memory. The default guest review response omits original values and exact offsets/lengths. An explicit Reveal values request returns the current document’s detected originals to the same guest session in one response. One control reveals or hides the entire review; the three columns retain their widths as text wraps. Guest originals remain unencrypted in temporary memory; a black bar is a visibility control, not encryption. Hide, close, tab hiding, expiry and session changes cancel pending requests and clear revealed values.

The optional `X-Document-Name` upload header carries a percent-encoded UTF-8 filename. A validated basename is held only in the guest record in RAM, shown in the file list, and never placed in URLs, logs or SQLite. One current result replaces the old finished result. The registry admits at most 64 sessions; retained outputs are capped at 128 MiB per result and 256 MiB in total before publication. An in-progress render can temporarily exceed those application limits; Docker’s 512 MiB tmpfs is the hard ceiling. Concurrent work in one session is rejected. The deadline is one hour from acceptance of each upload, not from completion; polling does not renew it. Replacement, explicit deletion, session reset, expiry and restart remove results. A periodic sweep cleans abandoned sessions, and startup clears orphaned temporary files. Running work is invalidated when its session disappears and cannot publish a late result. A download already authorized and underway can finish before its temporary file is removed.

Compose uses a 512 MiB tmpfs at `/app/data/guest`; it is a ceiling, not reserved memory. Direct Python uses `data/guest/` with explicit cleanup. The source/parser/model can observe plaintext in RAM; generated guest files can still contain confidential text or images. Host swap, snapshots and user downloads are outside the deletion guarantee. Browser closure is not a reliable server signal; expiry is the backstop, including browsers that restore session cookies.

## Durable history model

SQLite remains at `data/documents.sqlite3`. `history_documents` requires an internal `owner_id`, UUID, timestamp, status, draft expiry, constrained metadata and protection version. `history_artifacts` stores opaque binary values keyed by document and kind; foreign-key cascading deletion keeps metadata and artifacts together.

The artifact kinds are `source`, `manifest`, `output_pdf`, `output_docx`, and `output_txt`. All five must exist before commit. A record is invisible to the history list until committed, and committed payloads are immutable. Changed redaction settings create a new history record. Incomplete drafts expire after 15 minutes. Draft expiry starts at creation and is not renewed by uploads. Current limits are 64 MiB per artifact, 192 MiB per document and 100 retained/draft documents per owner. These local-app limits can be revisited with the final encrypted envelope overhead and hosted quotas.

Every repository method requires a verified-owner value, and every document/artifact lookup checks that owner. Browser input cannot set ownership. The future identity adapter will derive it only from verified authentication; no Tide claim convention is assumed now. Opaque-byte handling cannot establish that arbitrary bytes are cryptographically protected. Real protection must be enforced by the final provider/envelope integration before these endpoints become available.

Searchable metadata permits source type, mode, sensitivity, category counts, native/fallback state and constrained warning codes. Filenames, detected values, exact spans and arbitrary warning/error text are excluded. Counts and timestamps still reveal limited information; metadata is minimized rather than claimed to reveal nothing. Original filenames belong inside the future encrypted manifest.

## API boundaries

All routes below use `/api/service`. Sensitive responses have `Cache-Control: no-store`. Filesystem paths are never returned.

| Route | Purpose and authorization |
| --- | --- |
| `GET /health` | Local service/model status |
| `GET /capabilities` | Truthful secure-history availability |
| `GET /guest/current` | Bootstrap/read the cookie-scoped working result and CSRF token |
| `DELETE /guest/current` | CSRF-protected session reset; invalidate active work and clear cookie |
| `POST /guest/documents` | CSRF-protected raw PDF/DOCX upload with mode/type/sensitivity |
| `GET /guest/documents/{id}/preview` | Session-scoped generated text |
| `GET /guest/documents/{id}/review` | Session-scoped concealed detections and objective report |
| `GET /guest/documents/{id}/revealed-detections` | Explicit reveal of current document originals from guest RAM; same-session authorization |
| `GET /guest/documents/{id}/detections/{category}/{occurrence}` | Explicit reveal of one original value from current guest RAM; same-session authorization |
| `GET /guest/documents/{id}/protected-manifest` | Transient full manifest handoff; requires both verified owner and current guest session, unavailable before integration |
| `GET /guest/documents/{id}/download/{format}` | Session-scoped generated PDF/DOCX/TXT |
| `DELETE /guest/documents/{id}` | CSRF-protected removal of the finished working result |
| `GET, POST /history` | Verified-owner listing or draft creation |
| `GET, DELETE /history/{id}` | Verified-owner record access/removal |
| `PUT, GET /history/{id}/artifacts/{kind}` | Verified-owner opaque binary upload/retrieval |
| `POST /history/{id}/commit` | Verified-owner publication after all protected artifacts exist |

The old global `/documents` routes are removed. Unknown API routes remain JSON 404s. `/secure-history` and `/disclaimer` are explicit UI entry points; static serving never exposes `data/` or model files.

The processing boundary is deliberately transient and separate from durable history. Final authenticated reprocessing can retrieve ciphertext, decrypt it in the browser, and submit the resulting source through the working-document pipeline. A narrow verified-owner plus current-session manifest handoff is prepared for the final secure-save flow and currently fails closed. No server-side decryption is provided. Guest reveal reads only the current guest’s RAM manifest; it never decrypts or accesses durable history.

## Manifests and report limits

The manifest is built from the exact validated edit plan used to render the output, including the actual synthetic replacements. It preserves categories, originals, replacements, occurrence order and canonical extracted-text spans. These offsets refer to extracted Unicode text, not original bytes or reliable visual coordinates. It records mode, sensitivity, input format, native/fallback result and applicable warnings. It is versioned so later page/part mapping can be added deliberately.

The pinned OPF public result has no supported per-detection confidence score. The scan report shows sensitivity, counts/categories, input format, layout path, warnings and OCR/image limitations. It reports that OCR was not performed. Detection counts are not accuracy, and sensitivity is not confidence. Existing native sanitization protections and clean rewrite fallback remain in place. A source file or image can contain unsupported/unscanned information; redaction never guarantees anonymization.

## Frontend boundary

The main upload/settings/redact/result workflow remains primary. A restrained circular user icon and post-result prompt lead to `/secure-history` while Tide is unconfigured. Once a real provider is available, the icon opens Sign in when signed out or Sign out when authenticated. The REDACT button keeps its label on disabled hover while its arrow turns toward the upload field. During processing a looping black rectangle sweeps over the displayed filename, with a static reduced-motion alternative. The information page explains retention, detection review, authorized reveal/recovery and revisiting results before introducing TideCloak. Both modes are free. Real sign-in, secure saving and protected-history decryption remain unavailable until a real provider is installed; guest Reveal/Hide works immediately.

The provider interface separates identity state, authenticated history access and future browser protection/decryption from components. Original values are concealed by default and revealed together using one panel control. Future protected-history originals and filenames must be decrypted in the browser, and filenames must stay in the protected manifest rather than durable searchable metadata. Hide/close, navigation, identity changes, expiry and logout must abort pending sensitive requests and clear decrypted state; object URLs are revoked after use. Plaintext sources/manifests and tokens are not put in persistent frontend storage. JavaScript and Python memory release is not guaranteed physical erasure.

## Remaining final phase: Raziel-guided integration

Raziel MCP is required by the project brief and is not exposed in the current tool session. Do not infer Tide SDK methods, token claims or ciphertext formats from the prepared interfaces. Once connected, use it to implement and test frontend authentication, token lifecycle, backend EdDSA-compatible verification, Tide self-encrypt/self-decrypt, roles, binary handling, logout and errors.

The final flow must encrypt source, manifest **and cached outputs before durable retention**. Original recovery and ordinary downloads should decrypt in the browser without sending plaintext to the backend. Reprocessing necessarily sends plaintext for transient processing. Clear temporary artifacts after a successful protected save, and recover gracefully from interrupted encryption/upload/commit. No Forseti or delegated server decryption is planned.

A browser-memory source survives in-app navigation but not a full-page authentication redirect or reload. Raziel must guide that handoff; require a fresh source selection when no source remains, or add a bounded authorized RAM handoff if the verified flow requires one. Never silently substitute persistent browser storage or a plaintext durable source.

Required final tests include invalid/expired/wrong-issuer/audience/signature tokens, owner isolation under actual verified identities, real self-encryption/decryption round trips, wrong-user denial, logout clearing, interrupted saves, original recovery and transient reprocessing cleanup. Do not describe these as passed before the real integration exists.

## Migration and deployment

Upgrading from a legacy version drops the global unowned document table and removes its UUID output directories. Export any legacy files you need before upgrading. The migration never assigns old data to a new user or claims it is encrypted. Guest results intentionally do not survive restart. Model reuse, the `redacted-model` volume, one Uvicorn worker, local-only binding and the approximately 1.7 GB application image remain intact.

Public hosting is outside this change. It would need explicit allowed origins, HTTPS, proxy configuration, suitable quotas and operational data/key policies. Do not remove the local request checks merely to expose the service publicly.

## Verified preparation release — 1 October 2026

- Full backend suite: 99 passed, including native/fallback fidelity, isolated guests, owner-scoped opaque storage, expiry/reset/restart, download disconnects/Range errors and retrying failed cleanup.
- TypeScript/Vite build and all four browser scripts pass, including a test-only injected provider lifecycle fixture. Those fixtures do not implement or validate Tide cryptography.
- Live Docker smoke passes real local inference on DOCX Mask, PDF Mask, DOCX Label and PDF Replace; each verifies all three output formats, concealed review and cross-session denial. Test documents were deleted.
- FastAPI directly serves both the upload page and `/secure-history` with no browser runtime errors. Production has no Node executable.
- Runtime image: 1,698,528,775 bytes (about 1.7 GB). Existing `redacted-model` cache reused across rebuild/restart. Guest storage verified as tmpfs; restart removes working results. No durable history records were created.
- Actual TideCloak/JWT/self-encryption tests remain pending Raziel integration.

## Guest review update — 1 October 2026

Guest filenames now remain in session RAM and appear under the looping redaction-bar loader. Guest detections have one panel-wide Reveal/Hide control; the same-session endpoint returns detected originals together. The individual-value endpoint remains available for compatibility. Hidden values are not preloaded into the UI, and pending requests are cancelled on hide/close/expiry/identity change. A user icon replaces the header text action; its actual authentication behavior still depends on the future Tide provider. Disabled REDACT hover preserves its text and rotates only the arrow.

Validation: 123 backend tests pass, all four browser scripts pass, and real local-model DOCX/PDF checks across Mask/Label/Replace verify filename retention, per-value reveal, other-session denial, generated downloads and cleanup. No actual Tide authentication or encryption was added.
