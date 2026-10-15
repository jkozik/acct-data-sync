# acct-data-sync

Pulls your own bank transactions and balances via the [Plaid](https://plaid.com) API and writes
them in a bookkeeping-software-ready CSV/JSON format. Runs as three Docker services on a headless
host; triggered on demand from a client machine (see `powershell/` for the reference client).

For architecture, day-to-day usage, and troubleshooting, see `NOTES.md`. For the security review
this project went through before going public, see `AUDIT.md`.

## Prerequisites

- Docker + the `docker compose` plugin.
- A Plaid developer account with Production API access (the free Trial plan is sufficient for a
  handful of personal accounts — see `NOTES.md` for the exact limits).

## Install

```bash
git clone <this-repo-url>
cd acct-data-sync

cp .env.example .env
# edit .env -- see "Secrets" below

# tokens.json must exist as a FILE before the first `docker compose up`, or Docker will
# create an empty DIRECTORY at that path instead (a bind-mount gotcha) and every service
# will fail to read it.
echo '{}' > tokens.json

mkdir -p logs

docker compose up -d
```

Then open `http://<host-LAN-IP>:5001` in a browser to link each account through Plaid Link. Once
every account is linked, you can stop the linking UI — it's only needed again for re-linking or
re-authenticating, not day to day:

```bash
docker compose stop link-app
```

## Secrets

Everything below is set in `.env` (copied from `.env.example`, which is committed with blank
values — `.env` itself is git-ignored and must never be committed).

| Variable               | Required | Purpose                                                                 |
|-------------------------|----------|--------------------------------------------------------------------------|
| `PLAID_CLIENT_ID`       | Yes      | From the [Plaid dashboard](https://dashboard.plaid.com/team/keys).       |
| `PLAID_SECRET`          | Yes      | Production secret, from the same dashboard page.                         |
| `PLAID_SECRET_SANDBOX`  | Only for Sandbox testing | Sandbox secret, if you want to test against Plaid's fake data before using real accounts. |
| `PLAID_ENV`             | Yes      | `production` or `sandbox`.                                                |
| `PLAID_PRODUCTS`        | Yes      | Comma-separated Plaid products requested, e.g. `transactions,liabilities`. |
| `PLAID_COUNTRY_CODES`   | Yes      | Comma-separated ISO country codes, e.g. `US`.                             |
| `PLAID_REDIRECT_URI`    | Only if your institution needs it | Plaid's OAuth redirect flow for certain institutions. |

The other file with secret-equivalent content is `tokens.json` — it holds the Plaid access tokens
produced once you link an account via `link-app`. It's created empty above and populated by the
app itself; also git-ignored.
