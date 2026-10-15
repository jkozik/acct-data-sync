# Notes

Everything about this project beyond "how do I install it" — architecture, day-to-day usage,
design decisions, and troubleshooting. See `README.md` for install, and `AUDIT.md` for the
security review.

## Architecture

Three always-on services, one shared Docker image, no systemd units:

| Service              | Port | Purpose                                                                 |
|-----------------------|------|--------------------------------------------------------------------------|
| `export-api`          | 8090 | The trigger API. `POST /exports/transactions/<account>` and `POST /exports/balance/<account>`. Also `GET /health`. |
| `export-file-server`  | 8080 | Read-only static file server over the export directory (fallback/general-purpose file access; the balance flow no longer strictly needs it since `export-api` returns balances inline). |
| `link-app`            | 5001 | The Plaid Link web UI -- used once per account to connect it, and again whenever a login needs re-authenticating (`ITEM_LOGIN_REQUIRED`) or a new product/account needs consent. **Stopped by default** -- see "Linking or re-authenticating an account" below. |

All three read Plaid credentials from `.env` and share `tokens.json` (the access-token store) and
the export directory (where CSVs and balance JSON files land) via bind mounts -- see
`docker-compose.yml`.

## Account map

The bookkeeping software's own account numbers are used as the `<account>` key in every
`export-api` URL and every client script call -- not Plaid's internal login label or mask.

| `<account>` | Institution / card                | Mask   | Plaid login label      | Export folder                              | Balance export? |
|-------------|------------------------------------|--------|--------------------------|----------------------------------------------|------------------|
| `101`       | Chase checking                    | `1018` | `chase_household_login`  | `Chase101Export/`                            | No               |
| `301`       | Chase Sapphire (credit card)       | `1818` | `chase_household_login`  | `Chase301Export/`                            | Yes              |
| `302`       | Chase shared card (credit card)    | `4803` | `chase_household_login`  | `Chase302Export/`                            | Yes              |
| `304`       | Citi AT&T Universal (credit card)  | `3166` | `citi_universal_card`    | `UniversalCard304Export/`                    | Yes              |

Balance snapshot JSON files always land in a dedicated `PlaidBalances/` folder (never inside the
per-account `*Export/` folders -- the bookkeeping software's "most recent file in this folder"
import logic is extension-agnostic, so a balance JSON there would get mistaken for the activity
CSV; this bit us once already during development).

## Day-to-day usage

From the client machine, `powershell/Trigger-Transactions.ps1` and `powershell/Get-Balance.ps1`
(wrapped in local `.cmd`/shortcut files, one per account/action -- those wrappers are
environment-specific and are not part of this repo, see the bottom of this file):

```powershell
.\Trigger-Transactions.ps1 -Account 101   # or 301 / 302 / 304
.\Get-Balance.ps1 -Account 301            # 301 / 302 / 304 only -- copies a journal entry to the clipboard
```

Equivalent raw curl, if ever needed directly:
```bash
curl -X POST http://<host-LAN-IP>:8090/exports/transactions/101
curl -X POST http://<host-LAN-IP>:8090/exports/balance/301
curl http://<host-LAN-IP>:8090/health
```

### Linking or re-authenticating an account (link-app)

`link-app` is a credential-linking tool, not a day-to-day service -- it's needed only to link a
new account or to clear an `ITEM_LOGIN_REQUIRED` error, so it's kept **stopped** the rest of the
time rather than always-on (its `unless-stopped` restart policy means an explicit stop sticks
across host reboots too -- it won't silently come back on its own):

```bash
docker compose up -d link-app      # bring it up
# ... open http://<host-LAN-IP>:5001, link/re-auth the account ...
docker compose stop link-app       # take it back down when done
```

### Why manual triggering, not a schedule

This intentionally replaces a prior screen-scraping setup that worked well until the bank sites'
front ends changed enough (hidden DOM, React internals) to make scraping too fragile. The
switch to Plaid is about reliability, not automation -- triggering stays a deliberate, visible
action (about once per account per week, matching the old scraping cadence) so the user stays
aware of what's running, on the assumption that "when this all works, I'll forget about it"
otherwise. Don't add a cron job or scheduled task for this.

## Troubleshooting

`export-api` responses use HTTP status to tell you *where* to look before you even read the
body:

- **200** -- success.
- **404** -- a *local* problem: an unrecognized `<account>` key, an action not supported for
  that account (e.g. no balance export for `101`), or an expected local resource missing
  (export directory, stored access token). This is deliberately what surfaces if a future
  server migration didn't bring along the export-directory mount or `tokens.json`.
- **502** -- Plaid itself returned an error. The response body carries Plaid's real
  `error_type`, `error_code`, `error_message`, `plaid_request_id`, and a troubleshooting hint
  (see `PLAID_ERROR_HINTS` in `plaid_client.py`) -- including for rate-limit/usage-cap errors,
  which are NOT transient for `TRIAL_CONNECTION_LIMIT`/`CREDITS_EXHAUSTED` specifically.
- **500** -- anything else unexpected (a bug here, not Plaid's fault).

Every request (success or failure) is also logged as one JSON line to `logs/export_api.log` on
the host, including a full traceback for 500s -- `docker compose logs export-api` shows the raw
stdout/access log; `logs/export_api.log` is the structured one worth `grep`-ing.

`GET /health` (no Plaid calls, pure local filesystem/token checks) is the first thing to hit
after moving this to a new host or otherwise suspecting something's wrong before you even try a
real export.

### Pending transactions

`POST /exports/transactions/<account>` only writes transactions Plaid considers posted
(`pending: false`) -- see `write_chase_checking_csv`'s running-balance assumption. Plaid's own
pending->posted transition can lag what the bank's website already shows as cleared, sometimes by
a day or more (confirmed empirically -- Plaid replaces the pending transaction with a brand-new
posted one rather than flipping it in place, and that swap doesn't always happen the moment the
bank considers it posted). Nothing is lost: since every trigger re-pulls Plaid's full current
snapshot from scratch (no persisted cursor), an excluded transaction shows up automatically on a
later trigger once Plaid catches up. The response body (and `Trigger-Transactions.ps1`'s console
output) surfaces this directly via `pending_excluded_count` and `pending_excluded` so it isn't a
silent gap -- if something time-sensitive (e.g. a large deposit) is missing from a given week's
CSV, check there before assuming a bug.

### Plaid limits

- **Trial plan: 10 Production Items max.** Currently uses 2 (one household login covers three
  accounts; the fourth is a separate Item) -- nowhere close.
- **Per-endpoint rate limits** (e.g. `/accounts/balance/get`: 5/min, 30/hour per Item) are all
  far above this tool's actual usage (roughly once per account per week). If you ever see a 502
  with a rate-limit `error_code`, it's far more likely a retry loop than real load.

## Client-side scripts (`powershell/`)

`Trigger-Transactions.ps1` and `Get-Balance.ps1` are the two scripts actually run day to day, and
they're versioned here. In the original setup they're wrapped by a handful of tiny `.cmd` files
(one per account/action) and pinned as Start-menu shortcuts on the client machine -- those
wrappers are pure local glue (hardcoded local paths, one line each) and intentionally live only on
that machine, not in this repo. If ever needed again, they're trivial to recreate: each one just
runs

```
powershell.exe -NoLogo -NoExit -File "<path-to>\Get-Balance.ps1" -Account <account>
```

(or `Trigger-Transactions.ps1` for the transactions side), one per `<account>`/script
combination.

**Lesson learned the hard way:** before this was in git, the client machine's copy of these
scripts drifted ahead of this repo's copy (a feature got added on the client side and never
synced back), and a later "fix" here accidentally reverted it. Now that it's versioned, always
diff against what's actually deployed on the client before assuming this repo's copy is current,
and copy any changes back to the client machine after editing here -- there's no automatic sync.
