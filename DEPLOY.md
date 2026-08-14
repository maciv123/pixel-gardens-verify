# Deploy to Render (recommended)

GitHub stores your code. **Render** runs it 24/7 in the cloud so your PC can stay off.

## 1. Push latest code to GitHub

Repo: https://github.com/maciv123/pixel-gardens-verify

## 2. Create a Render account

1. Go to [render.com](https://render.com) and sign up (use **Sign in with GitHub**)
2. Connect your GitHub account

## 3. Deploy from GitHub

1. Click **New +** → **Blueprint**
2. Connect repo **`maciv123/pixel-gardens-verify`**
3. Render reads `render.yaml` automatically
4. Add these **secret** environment variables when prompted:
   - `DISCORD_BOT_TOKEN` — your bot token
   - `DISCORD_GUILD_ID` — `1522696103676481817`
   - `HOLDER_ROLE_ID` — `1522696103676481820`
   - `VERIFY_BASE_URL` — leave blank for now, set after step 4

5. Click **Apply** and wait for deploy (~2–5 min)

## 4. Set your public URL

After deploy, Render gives you a URL like:

`https://pixel-gardens-verify.onrender.com`

1. Go to Render → your service → **Environment**
2. Set `VERIFY_BASE_URL` to that URL (no trailing slash)
3. Save — Render redeploys automatically

## 5. Use Discord

Run **`/verify`** in your server — the bot runs in the cloud now.

---

## Cost

- Render **Starter** plan (~$7/month) keeps the bot online 24/7
- Free tier sleeps when idle — **not good for Discord bots**

## Alternative: Railway

1. [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Select `pixel-gardens-verify`
3. Add the same environment variables
4. Set start command: `cd bot && python main.py`

---

## You can stop running it on your PC

Once cloud deploy works:
- Close any local bot windows
- Don't run `start-bot.bat` anymore
- The bot stays online on Render/Railway
