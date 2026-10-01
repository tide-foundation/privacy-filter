# Enable TideCloak and encrypted history

This is an optional integration. Ordinary `docker compose up -d` starts Redacted only. The local app and its documents remain usable in guest mode when TideCloak is stopped. Authentication and personal encryption require access to Tide's network.

## Owner setup

Python 3 and Docker Compose 2.24 or newer are required by the setup helper. Run commands from your Redacted checkout.

To download and create TideCloak without starting it:

```bash
python3 scripts/tidecloak.py prepare
```

To start it when you are ready:

```bash
python3 scripts/tidecloak.py start
```

The command opens (or prints) a private, single-use link to [Redacted setup](http://localhost:3001/secure-history/setup). There is no setup code or administrator password to copy into the browser. Keep that link private: it grants setup access for one hour.

The complete link is always printed, even when automatic launch succeeds. The helper uses the default browser on Windows/macOS/Linux and the Windows host browser on WSL when available. If no browser can be launched, open a browser on the same computer and paste the **entire** printed link, including `#setup=` and everything after it. Use `python3 scripts/tidecloak.py start --no-browser` to choose manual opening. This also works with `connect`.

Complete the remaining steps inside Redacted:

1. Choose a **new realm name**, enter your email (used for Tide licensing and the setup administrator), choose whether to allow sign-ups, and review/accept Tide’s terms.
2. Redacted creates the realm, activates Tide, and prepares the login client, personal-history permissions and supplied branding. The checklist shows progress.
3. Select **Connect my Tide account**. Complete the supported Tide account-linking window; Redacted checks for completion automatically.
4. If a signature is required, select **Review and approve with Tide** inside Redacted. The actual Tide enclave presents the signing request. Redacted submits the signed response and continues when quorum is satisfied. No routine console visit is needed.
5. Once configured, sign in and select **Test encrypted history** on the setup page. Then test an invented sample document, sign out/in, and check downloads and detection reveal.

The app configures personal encryption, login settings and branding before granting the first realm administrator. It uses Tide’s supported first-admin bootstrap approvals; once Tide requires a human enclave signature, setup stops for that signature. It never disables governance to finish a step. The default encryption permissions apply to ordinary users; administrator rights are separate.

New users sign in with Tide without a separate Keycloak username/email/name form. After licensing, setup makes email and name optional, disables profile required actions and disables the broker’s profile-review step. Tide supplies the account identifier; account uniqueness and existing-account verification remain enabled. No placeholder email or name is invented for ordinary users.

Progress is saved in `data/tide/onboarding.json`. Reloading resumes the same browser session. After a restart or expiry, rerun the initial command and open its fresh link: the checklist resumes the existing realm instead of creating it again. A collision with an unrelated realm name sends you back to choose another name without changing that realm.

The helper proves terminal access using a short-lived filesystem permit. It sends the bootstrap credentials directly to the local backend, which retains them **only in memory for at most one hour**, then expires them or clears them on completion/restart. The browser receives an HttpOnly setup-session cookie and CSRF token. The private link is removed from the address bar immediately after use; it is not put into browser storage or server access-log URLs. The app never mounts Docker’s socket. Successful configuration closes the setup API.

Owner credentials for the bundled service live in `.tidecloak/bootstrap.env` (owner-readable, ignored by Git and Docker builds). Only TideCloak mounts this file. Keep it for maintenance; replacing it does not rotate an existing administrator’s password.

### Connect a TideCloak that is already running

Redacted can create its own realm on another local TideCloak server. Existing realms are left alone. For a Docker app connecting to a host service on port 8080, put this in `.env` and recreate **only the app**:

```dotenv
TIDECLOAK_PORT=8080
TIDECLOAK_INTERNAL_URL=http://host.docker.internal:8080
```

```bash
docker compose up --build -d app
python3 scripts/tidecloak.py connect
```

The connect command prompts for that server’s owner credentials in the terminal, then opens the authorized wizard. If it is your local Docker container and its bootstrap password is still current, use `python3 scripts/tidecloak.py connect --container tidecloak` to read those credentials in memory instead. No other container is stopped or reconfigured.

For a Python app outside Docker, export `TIDECLOAK_INTERNAL_URL=http://localhost:8080` and `TIDECLOAK_PUBLIC_URL=http://localhost:8080` before starting it. Use the helper’s `--app-url` and `--data-dir` options if you customized the app address or storage path.

To use a different port for a **new bundled installation**, set `TIDECLOAK_PORT=8090` (or another free port) in `.env` before creating its realm, then recreate the app and run the start helper. A port collision produces an explanation; the helper never stops whatever owns that port. Changing an established issuer/port or switching TideCloak instances is not a migration of identities or ciphertext. Keep an existing installation’s addresses stable.

## Browser permission for local hosting

When the hosted Tide sign-in page asks to access your local network, allow it for
the configured Tide origin. Also allow this permission for Redacted's local app
origin when its embedded encryption window requests it. The enclave needs to load the local DPoP relay and
branding images from localhost. In Chrome, denying this permission can leave the
login form visible while blocking its local security handshake and images.
The local smoke check verified the relay and both branded images load once the
permission is granted. See [Chrome's Local Network Access permission](https://developer.chrome.com/blog/local-network-access).
Do not disable browser security checks globally.

## Accounts and documents

Sign in **before** uploading. A full-page login clears the working session; guest documents and their original source do not silently transfer through browser storage. Download the guest result first, then upload again after signing in.

For a signed-in user, completed results are encrypted and saved automatically. Once committed, the temporary working copy is deleted; if cleanup fails, the app asks the user to trash that copy. Source, filename, detection manifest and each output format are independently encrypted using the user's Tide `history` permissions. An interrupted save is discarded where possible; abandoned drafts expire after 15 minutes. A save failure leaves the temporary result available for download/retry until guest-session expiry.

Durable ciphertext is stored in `data/documents.sqlite3`. Metadata (time, format, mode, sensitivity, category counts and generated replacement values) is not encrypted. The browser decrypts filenames individually for the Files list. Opening Review detections reads category counts and generated replacements; Reveal values decrypts all originals for that document together, in one manifest operation. Original and output downloads decrypt only the selected artifact. Decrypted items are cached in tab memory until sign-out, reload or eviction (256 MiB limit). Older documents initially show a document ID; their first explicit Reveal adds a separate encrypted filename without changing existing ciphertext. There is no Reprocess action.

Default encryption roles are approved during initial setup. Additional administrators are never automatically granted. Self-registration is configurable; **unattended registration with QEA, including account linking without further admin approval, must be verified against the installed release**. Do not promise this until a second user passes that check.

## Start, stop and storage

```bash
python3 scripts/tidecloak.py stop
python3 scripts/tidecloak.py start
python3 scripts/tidecloak.py logs
```

The services bind to localhost: Redacted on port 3001 and TideCloak on 8080 by default. This release does not expose either service to other computers. Use the same app origin consistently; the realm configuration is bound to it. Choose custom local ports before setup so the generated client, issuer and origin settings match. Remote hosting is outside this release.

The TideCloak database is in the `redacted-tidecloak` Docker volume, mounted at `/opt/keycloak/data/h2`. A short-lived init container sets volume ownership; it has no network and exits before TideCloak starts. The actual TideCloak server runs as its normal unprivileged user. It has a 2 GB container memory limit; actual use and adequacy must be checked for your workload. TideCloak does not automatically start after a host restart.

Back up **together**:

- `data/documents.sqlite3` and `data/tide/config.json`;
- the stopped `redacted-tidecloak` volume;
- `.tidecloak/bootstrap.env`, stored securely outside a public repository;
- your Tide account recovery material through Tide's supported recovery process.

Stop both services before taking a simple filesystem/volume backup. Keep the model volume separately if you want to avoid downloading it again. Deleting/recreating the realm is not a recovery procedure for existing ciphertext. A restored deployment must retain its issuer, client configuration and user identities.

## Version and verification notes

The integration pins TideCloak image digest `sha256:06ad6dfc58a441c40cda99ce6800511846a27b6cfb47d9c084274470e10548db` (image label 0.14.38) and browser SDK `@tidecloak/js` 0.14.34. These were the supported image and latest stable JavaScript SDK available during implementation; exact interoperability still requires the live account tests above. Do not infer it from matching version numbers in older setup guides.

The SDK includes its own DPoP relay and CSP. Build copies those assets from the pinned package. FastAPI checks EdDSA access tokens against the locally trusted adapter keys, exact issuer/audience/client, expiry and required roles, plus ES256 DPoP proof signature, key binding, HTTP method, URL, access-token hash, nonce and replay protection. A bound-token claim alone is not accepted as proof of possession. No server decryption key is installed.

Automated tests cover token/proof rejection, owner isolation, single-use owner handoff and resumable setup, guest behavior, and the browser storage boundary with an explicitly isolated encryption fixture. Fixture tests do not prove live Tide network behavior, admin ceremonies, self-registration or cross-account cryptographic isolation; those require real accounts.

If realm provisioning, account linking or governance approval is incomplete, leave setup unfinished and keep using guest redaction. There is no plaintext secure-history fallback.

Upstream registration tests explicitly permit default self-encryption roles for
open self-registration: [default-role grants](https://github.com/tide-foundation/tidecloak-iga-extensions/blob/main/iga-core/src/test/java/org/tidecloak/iga/providers/IgaUserProviderRegistrationDefaultRolesTest.java)
and [default-role privilege guard](https://github.com/tide-foundation/tidecloak-iga-extensions/blob/main/iga-core/src/test/java/org/tidecloak/iga/providers/DefaultRoleCompositeGuardTest.java).
This source evidence supports the intended flow but does not replace a live test
of the pinned container and account-linking path.
