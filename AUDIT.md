# Security audit

This project handles real bank credentials (via Plaid) and real financial data, so before making
the repository public it went through a deliberate security review. This document records what
was checked, what was changed, and how to verify or roll back each change. It's a best-effort
pass by one person for a personal tool, not a professional pentest — documented here so the
effort is visible, not to claim completeness.

Specific internal network addresses and hostnames are abstracted below (`<host>`, `<client>`,
`<subnet>`) — they're not secret, but there's no reason to spell out a live home network's
topology in a document whose whole point is "here's what I locked down."

## Scope

- The application code and how it handles Plaid credentials and access tokens.
- The Docker packaging (what's exposed, what's mounted, how).
- The host-level file permissions on anything secret.
- The home-network file share (NFS) used to hand exported files to the client machine, since it's
  part of the same data path even though it's not part of this repo.

Out of scope: Plaid's own backend security (a vendor trust decision, not something this project
can audit), and the client machine's OS-level security generally.

## Secrets & credential handling

- Plaid API credentials live only in `.env` (git-ignored); `.env.example` documents the required
  keys with blank values.
- Plaid access tokens (one per linked login) live only in `tokens.json` (git-ignored), written
  once via the Link UI and read by the API service. Neither file is ever logged, printed, or
  included in the Docker build context (`.dockerignore`) or image.
- The Link UI (`link-app`) is the only service that can write `tokens.json`; the trigger API
  mounts it read-only.

## Findings and remediations

### 1. Secret file permissions

`.env` and `tokens.json` were world-readable to any local account on the host (`664`). Tightened
to `600` (owner-only). The structured request log (`logs/export_api.log`), which includes
transaction dates/amounts/descriptions in its entries, was tightened from `664` to `640`.

### 2. `link-app`'s exposure

Two separate issues in the Plaid-Link web service:

- It ran with Flask's `debug=True`, which enables the Werkzeug interactive debugger — a
  browser-reachable Python console if an unhandled exception ever hit an endpoint. This is a
  real remote-code-execution surface on anything network-reachable, which this was (bound to all
  interfaces on the LAN). Removed.
- It was always running (`restart: unless-stopped`), despite being needed only rarely (initial
  account linking, or clearing a `ITEM_LOGIN_REQUIRED` re-auth). Changed to stopped-by-default —
  brought up on demand with `docker compose up -d link-app` and stopped again afterward. Its
  restart policy means an explicit stop is sticky across host reboots too.

### 3. Docker mount scope

Reviewed every bind mount in `docker-compose.yml` against what each service actually needs:

- The access-token file (`tokens.json`) is mounted read-only into the trigger API (`export-api`,
  which only ever reads it) and read-write only into `link-app` (the one service that writes it).
- The static file server (`export-file-server`) only ever serves files; its mount into the export
  directory was read-write with no need for write access. Changed to read-only.

### 4. Home-network file share (NFS)

The export directory is shared over NFS so the client machine's reconciliation software can read
the generated files directly. The original export rule:

- Allowed **read-write** access from the **entire LAN subnet** (not just the one client that
  actually uses it).
- Used `no_root_squash` — a client claiming to be `root` was trusted as real root over the shared
  directory, with no identity remapping (`no_all_squash`) at all.
- As a side effect, the shared folders had ended up world-writable (`777`) — a workaround for the
  Windows NFS client presenting an identity the server didn't recognize, with nothing in place to
  remap it.

Redesigned to:

- Scope the export to the **one specific client IP** that actually reads it, nothing broader.
- **Read-only** — the client only ever reads these files; the one other machine that used to write
  into this share writes over SSH/SCP instead (a separate, already-authenticated mechanism, not
  NFS), so NFS write access was never actually required for day-to-day operation.
- **`all_squash`** with a fixed low-privilege local user — every request, including one claiming
  to be root, is mapped to one ordinary local account. This removes the root-equivalent bypass
  entirely and makes read permission checks deterministic.
- Folder permissions brought back down from `777` to `755`, since nothing needs group/other write
  any more.

The previous rule was commented out in place (not deleted) rather than removed outright, together
with a dated backup of the export config, specifically so there's a fast, verified rollback path
if anything about the new scope turns out to be wrong — see "Rollback," below.

## Verification performed

- Re-triggered real exports against the tightened directory permissions and confirmed the
  application (which writes as a privileged user inside its container) still writes successfully
  — root bypasses ordinary Unix permission checks, but this was confirmed rather than assumed.
- Confirmed via the live NFS export table that only the intended client address is granted access,
  with the intended read-only/squashed options active — not just that the config file was edited.
- Had the actual client machine's reconciliation software read from every account's export folder
  after the change and confirmed it still worked end-to-end, since that's the one check that can't
  be done from the server side.

## Rollback

Each change above is independently reversible:

- **File permissions**: harmless to revert (`chmod 664`), though there's no reason to.
- **`link-app`**: `docker compose up -d link-app` brings it back; nothing was removed, only the
  always-on default and debug mode.
- **Docker mounts**: remove the `:ro` suffix in `docker-compose.yml` and recreate the affected
  service if read-write access is ever genuinely needed again.
- **NFS**: the previous rule is preserved, commented, in the export config, alongside a dated
  backup of the full file — reverting is restoring that backup (or un-commenting the old rule and
  re-commenting the new one) and reloading the NFS export table. If a similar one-off need for
  broader access arises again (there was a precedent: a one-time emergency backup of unrelated
  data that used to ride on the old broad rule), the intended pattern is a temporary, narrowly
  scoped addition for the duration, removed afterward — not reverting to a standing broad rule.
