# Deploy to Railway

Your PC stays off. Railway runs the bot 24/7 from GitHub.

## 1. Push latest code to GitHub

Repo: https://github.com/maciv123/pixel-gardens-verify

## 2. Create project on Railway

1. Go to [railway.app/dashboard](https://railway.app/dashboard)
2. **New Project** → **Deploy from GitHub repo**
3. Select **`maciv123/pixel-gardens-verify`**
4. Railway builds from the `Dockerfile` automatically

## 3. Add environment variables

In Railway → your service → **Variables**, add:

| Variable | Value |
|----------|-------|
| `DISCORD_BOT_TOKEN` | Your bot token (Discord Developer Portal) |
| `DISCORD_GUILD_ID` | `1522696103676481817` |
| `HOLDER_ROLE_ID` | `1522696103676481820` |
| `CONTRACT_ADDRESS` | `0x0bfdf5e03e6480a8b40f40c468d55b239811aef0` |
| `CHAIN_ID` | `4663` |
| `ROBINHOOD_RPC_URL` | `https://rpc.mainnet.chain.robinhood.com` |
| `VERIFY_BASE_URL` | Leave blank until step 4 |

## 4. Public URL

1. Railway → service → **Settings** → **Networking** → **Generate Domain**
2. Copy the URL (e.g. `https://pixel-gardens-verify-production.up.railway.app`)
3. Add variable `VERIFY_BASE_URL` = that URL (no trailing slash)
4. Railway redeploys automatically

## 5. Use Discord

- Run **`/verify`** — you get a link to your Railway URL
- Connect MetaMask on Robinhood Chain → sign → get **PG Holder** role
- Stop using `start-bot.bat` on your PC

## 6. Auto-redeploy on push (optional)

GitHub pushes do not always redeploy Railway automatically. One-time setup:

1. Railway → service → **Settings** → **Deploy** → copy **Deploy Hook** URL
2. GitHub repo → **Settings** → **Secrets and variables** → **Actions** → New secret: `RAILWAY_DEPLOY_HOOK` = that URL
3. Future pushes to `master` trigger a redeploy via `.github/workflows/railway-deploy.yml`

If production is stale, manually **Redeploy** once from Railway → **Deployments**.

Verify deploy: open `https://YOUR-RAILWAY-URL/api/health` — should return `"refresh_roles":"enabled"`.

## Cost

- **Free plan:** $1/mo credit — may not last all month for 24/7 bot
- **Hobby:** ~$5/mo — recommended for always-on
