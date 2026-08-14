# Pixel Gardens Discord Verify Bot

Discord bot that verifies **Pixel Gardens** NFT holders on **Robinhood Chain** and assigns a holder role.

- Contract: `0x0bfdf5e03e6480a8b40f40c468d55b239811aef0`
- Chain: Robinhood Chain (ID `4663`)
- Token: PixelGardens (ERC-721)

## Setup

### 1. Create a Discord bot

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Create an application → **Bot** → copy the token
3. Enable **Server Members Intent** under Privileged Gateway Intents
4. Invite the bot to your server with `Manage Roles` and `Send Messages` permissions
5. Create a role (e.g. `@Pixel Gardens Holder`) and put holder channels behind it
6. Make sure the bot's role is **above** the holder role in Server Settings → Roles

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Description |
|----------|-------------|
| `DISCORD_BOT_TOKEN` | Bot token from Developer Portal |
| `DISCORD_GUILD_ID` | Your server ID (right-click server → Copy Server ID) |
| `HOLDER_ROLE_ID` | Role ID to assign (right-click role → Copy Role ID) |
| `VERIFY_BASE_URL` | Public URL of the verify page (use `http://localhost:8080` for local testing) |

### 3. Install and run

```bash
cd bot
pip install -r requirements.txt
python main.py
```

The bot and verify web server start together on port `8080`.

### 4. Post the verify button

In your Discord server, run the slash command:

```
/verify
```

(Admin only.) This posts the **Verify Holder** button in the channel.

## How verification works

1. User clicks **Verify Holder** in Discord
2. Bot sends a private link (expires in 15 minutes)
3. User connects MetaMask on Robinhood Chain and signs a message
4. Bot checks `balanceOf(wallet)` on the PixelGardens contract
5. If they hold at least 1 NFT → holder role is assigned

## Production deployment

For production, deploy to a VPS, Railway, or Render so the bot stays online 24/7. Set `VERIFY_BASE_URL` to your public domain (e.g. `https://verify.yourdomain.com`).

## Project structure

```
pixel-gardens-verify/
├── bot/
│   ├── main.py          # Entry point (Discord + API)
│   ├── api.py           # FastAPI routes + Discord views
│   ├── verify.py        # Signature + on-chain checks
│   ├── db.py            # SQLite storage
│   └── config.py        # Environment config
├── web/
│   ├── index.html       # Verify page
│   └── static/app.js    # MetaMask integration
└── data/                # SQLite database (created at runtime)
```
