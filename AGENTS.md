# AGENTS.md

## Cursor Cloud specific instructions

### What this is
Single Python 3.12 service: a Discord NFT-holder verification bot plus a FastAPI/uvicorn web+API server that run **together in one process**. Standard setup/run steps are in `README.md`; run it with `cd bot && python3 main.py` (serves on port `8080`). There is no separate frontend build — `web/` is static and served by the same process.

### Dependencies
Python deps are installed into the user site (`pip install --user --break-system-packages -r requirements.txt`); the startup update script refreshes them, so you normally don't reinstall manually. Deps are unpinned (`>=`) and there is no lockfile.

### Running locally (non-obvious gotchas)
- A local `.env` in the **repo root** (gitignored) is required. `bot/config.py` hard-fails at startup unless `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`, and a PG contract + role config are present. Copy `.env.example` to `.env` as a starting point.
- You do **not** need a real Discord token to work on the web/API. If the token is invalid, `main.py` logs `Discord login failed` and keeps the verify API online — so the HTTP endpoints and the wallet-signature flow are fully testable without Discord. Real Discord role assignment (and true holder checks) require a real bot token, guild membership, and a wallet that holds Pixel Gardens NFTs.
- RPC gotcha: setting `PG_RPC_URL=` (empty) in `.env` **overrides** the `ROBINHOOD_RPC_URL` fallback and produces an empty RPC URL, causing `/api/verify` to return `502 Could not connect to RPC at`. Leave `PG_RPC_URL` unset (omit the line) so it falls back to `ROBINHOOD_RPC_URL` (defaults to the public Robinhood Chain RPC). The same pattern applies to `PG_CONTRACT_ADDRESS` vs `CONTRACT_ADDRESS`.
- Single-instance lock: `main.py` binds `127.0.0.1:47201`; a second `python3 main.py` exits immediately with "Bot is already running". Kill the first instance (by PID) before starting another, or set `RENDER=1`/`RAILWAY_ENVIRONMENT=1` to skip the lock.
- SQLite DB is auto-created at `data/verifications.db` (gitignored); no separate DB service.

### Tests / lint / build
There are no automated tests and no configured linter in this repo. For a quick syntax check use `python3 -m compileall bot`. There is no build step (static frontend, no bundler).

### Quick end-to-end check of the core flow (no Discord/wallet needed)
Create a session row with `bot/db.create_session(...)`, `GET /api/session/{id}` to obtain the sign message, sign it with `eth_account` (equivalent to MetaMask `personal_sign`), then `POST /api/verify`. A fresh wallet correctly returns `403` (holds 0 Pixel Gardens NFTs) after the signature is recovered and matched, which exercises the full signature + on-chain balance pipeline.
