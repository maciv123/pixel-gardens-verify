# Pixel Gardens Verify — Pick Up Here

Last updated: Aug 14, 2026

Use this file when you come back. Everything you need is below.

---

## Status: LIVE on Railway

| What | Value |
|------|-------|
| **Public verify URL** | https://pixel-gardens-verify-production.up.railway.app |
| **Railway dashboard** | https://railway.com/dashboard |
| **GitHub repo** | https://github.com/maciv123/pixel-gardens-verify |
| **Runs on your PC?** | **No** — do not run `start-bot.bat` |

Secrets live in **Railway Variables** and local **`.env`** / **`railway-paste.env`** (gitignored).

---

## What this project does

Discord bot for **UnFairBears** — tiered NFT verification on **Robinhood Chain**.

1. User runs **`/verify`** in Discord → gets a private verify link
2. Opens link → connects MetaMask on Robinhood Chain → signs
3. Bot checks on-chain balance → assigns **tier roles**

**Collections:**
- **PG (Pixel Gardens)** — live
- **UB (UnFairBears)** — not minted yet (`UB_ENABLED=false`)

---

## Discord

| Setting | Value |
|---------|-------|
| Bot | Unfair Bot#7344 |
| App ID | `1537607312754085998` |
| Server | UnFairBears |
| Guild ID | `1522696103676481817` |

### PG tier roles (configured)

| Tier | Env variable | Role ID |
|------|--------------|---------|
| Flower [25+] | `PG_ROLE_FLOWER` | `1537622373342117918` |
| Flowering [15-24] | `PG_ROLE_FLOWERING` | `1537621743521505300` |
| Veg [6-14] | `PG_ROLE_VEG` | `1537621033765314671` |
| sprout [1-5] | `PG_ROLE_SPROUT` | `1537620256262979684` |
| PG Holder | `HOLDER_ROLE_ID` / `PG_ROLE_HOLDER` | `1522696103676481820` |

**Bot role hierarchy:** Unfair Bot must be **above** all tier roles with **Manage Roles**.

### Commands

- **`/verify`** — anyone; ephemeral link to verify page
- **`/setup-verify`** — admin; posts public Verify button in channel

---

## Chain / contract

| Setting | Value |
|---------|-------|
| Contract | `0x0bfdf5e03e6480a8b40f40c468d55b239811aef0` |
| Chain ID | `4663` (Robinhood Chain) |
| RPC | `https://rpc.mainnet.chain.robinhood.com` |

---

## Railway env vars (copy from `railway-paste.env`)

```
DISCORD_BOT_TOKEN=...
DISCORD_GUILD_ID=1522696103676481817
HOLDER_ROLE_ID=1522696103676481820
PG_ROLE_FLOWER=1537622373342117918
PG_ROLE_FLOWERING=1537621743521505300
PG_ROLE_VEG=1537621033765314671
PG_ROLE_SPROUT=1537620256262979684
PG_ROLE_HOLDER=1522696103676481820
CONTRACT_ADDRESS=0x0bfdf5e03e6480a8b40f40c468d55b239811aef0
CHAIN_ID=4663
ROBINHOOD_RPC_URL=https://rpc.mainnet.chain.robinhood.com
VERIFY_BASE_URL=https://pixel-gardens-verify-production.up.railway.app
```

Railway → service → **Variables** → **Raw Editor** → paste → Save.

See also **`RAILWAY.md`**.

---

## GitHub & Railway login from Cursor

Cursor has its **own browser** (not Chrome/Edge). Log in once there if you want the agent to open those sites while you work in Cursor:

1. In Cursor chat, ask to open **https://github.com/login**
2. Sign in with your GitHub account
3. Open **https://railway.com/dashboard** → **Continue with GitHub** → authorize

**Easier day-to-day:** use Chrome/Edge for Railway/GitHub (you’re already logged in there). Use Cursor browser only when the agent needs to click through deploy steps with you.

**Git from terminal:** `gh auth login` if `gh` commands fail (one-time setup).

---

## Local files (do not commit secrets)

| File | Purpose |
|------|---------|
| `.env` | Local secrets (gitignored) |
| `railway-paste.env` | Full Railway Variables paste file (gitignored) |
| `data/` | SQLite verifications DB (gitignored) |

---

## If something breaks

1. **Railway 502** — check Variables match `railway-paste.env`; view **Deployments → Logs**
2. **`/verify` command not found** — pick `/verify` fresh from slash menu after bot restart
3. **Roles not assigned** — bot role order + Manage Roles; re-run `/verify`
4. **Wrong tier** — user re-verifies; old roles removed, new tier applied

---

## Repo layout

```
pixel-gardens-verify/
├── bot/           # Discord bot + FastAPI verify API
├── web/           # MetaMask verify page
├── railway.toml
├── Dockerfile
├── RAILWAY.md
└── railway-paste.env   # local only — Railway Variables
```

Push code: commit → `git push origin master` → Railway auto-redeploys from GitHub.
