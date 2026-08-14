import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import Settings
from db import (
    create_session,
    get_session,
    get_verification_by_discord,
    get_verification_by_wallet,
    mark_session_used,
    save_verification,
)
from verify import build_sign_message, check_nft_holder, recover_signer

WEB_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent / "web"


class VerifyRequest(BaseModel):
    session_id: str
    address: str
    signature: str


def create_api(settings: Settings, bot: discord.Client) -> FastAPI:
    app = FastAPI(title="Pixel Gardens Verify")
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/api/session/{session_id}")
    async def get_session_info(session_id: str) -> dict[str, Any]:
        row = get_session(settings.db_path, session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")

        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if row["used"]:
            raise HTTPException(status_code=410, detail="Session already used")
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(status_code=410, detail="Session expired")

        message = build_sign_message(row["discord_user_id"], row["nonce"])
        return {
            "session_id": session_id,
            "message": message,
            "chain_id": settings.chain_id,
            "contract_address": settings.contract_address,
        }

    @app.post("/api/verify")
    async def verify_holder(payload: VerifyRequest) -> dict[str, str]:
        row = get_session(settings.db_path, payload.session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")

        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if row["used"]:
            raise HTTPException(status_code=410, detail="Session already used")
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(status_code=410, detail="Session expired")

        message = build_sign_message(row["discord_user_id"], row["nonce"])
        try:
            recovered = recover_signer(message, payload.signature)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid signature") from exc

        if recovered.lower() != payload.address.lower():
            raise HTTPException(status_code=400, detail="Signature does not match wallet")

        existing_wallet = get_verification_by_wallet(settings.db_path, payload.address)
        if (
            existing_wallet is not None
            and existing_wallet["discord_user_id"] != row["discord_user_id"]
        ):
            raise HTTPException(
                status_code=409,
                detail="This wallet is already linked to another Discord account",
            )

        try:
            is_holder = check_nft_holder(
                settings.robinhood_rpc_url,
                settings.contract_address,
                payload.address,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        if not is_holder:
            raise HTTPException(
                status_code=403,
                detail="Wallet does not hold a Pixel Gardens NFT",
            )

        guild = bot.get_guild(settings.discord_guild_id)
        if guild is None:
            raise HTTPException(status_code=503, detail="Discord server not available")

        member = guild.get_member(int(row["discord_user_id"]))
        if member is None:
            try:
                member = await guild.fetch_member(int(row["discord_user_id"]))
            except discord.NotFound as exc:
                raise HTTPException(
                    status_code=404, detail="Discord member not found in server"
                ) from exc

        role = guild.get_role(settings.holder_role_id)
        if role is None:
            raise HTTPException(status_code=503, detail="Holder role not found")

        await member.add_roles(role, reason="Pixel Gardens holder verified")
        save_verification(settings.db_path, row["discord_user_id"], payload.address)
        mark_session_used(settings.db_path, payload.session_id)

        return {"status": "verified", "wallet": payload.address.lower()}

    return app


class VerifyView(discord.ui.View):
    def __init__(self, settings: Settings):
        super().__init__(timeout=None)
        self.settings = settings

    @discord.ui.button(
        label="Verify Holder",
        style=discord.ButtonStyle.green,
        custom_id="pixel_gardens_verify",
    )
    async def verify_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        existing = get_verification_by_discord(
            self.settings.db_path, str(interaction.user.id)
        )
        if existing is not None:
            await interaction.response.send_message(
                f"You are already verified with wallet `{existing['wallet_address']}`.",
                ephemeral=True,
            )
            return

        session_id = secrets.token_hex(16)
        nonce = secrets.token_hex(8)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        create_session(
            self.settings.db_path,
            session_id,
            str(interaction.user.id),
            nonce,
            expires_at,
        )

        verify_url = f"{self.settings.verify_base_url}/?session={session_id}"
        await interaction.response.send_message(
            "Click the link below to connect your wallet and verify your Pixel Gardens NFT:\n"
            f"**[Verify Now]({verify_url})**\n\n"
            "This link expires in 15 minutes. Make sure MetaMask is on **Robinhood Chain**.",
            ephemeral=True,
        )


def create_bot(settings: Settings) -> commands.Bot:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.message_content = True

    bot = commands.Bot(command_prefix="!", intents=intents)
    guild = discord.Object(id=settings.discord_guild_id)

    @bot.event
    async def on_ready() -> None:
        bot.add_view(VerifyView(settings))
        print(f"Logged in as {bot.user} (id={bot.user.id})", flush=True)
        try:
            synced = await bot.tree.sync(guild=guild)
            names = [cmd.name for cmd in synced]
            print(f"Synced {len(synced)} command(s) to {settings.discord_guild_id}: {names}", flush=True)
        except Exception as exc:
            print(f"Failed to sync slash commands: {exc}", flush=True)

    async def post_verify_message(channel: discord.abc.Messageable) -> None:
        embed = discord.Embed(
            title="Pixel Gardens Holder Verification",
            description=(
                "Own a Pixel Gardens NFT on Robinhood Chain?\n\n"
                "Click **Verify Holder** below to connect your wallet and unlock holder channels."
            ),
            color=0x00AA55,
        )
        await channel.send(embed=embed, view=VerifyView(settings))

    @bot.tree.command(
        name="verify",
        description="Post the Pixel Gardens verify button in this channel",
        guild=guild,
    )
    @app_commands.default_permissions(administrator=True)
    async def verify_slash(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await post_verify_message(interaction.channel)
            await interaction.followup.send("Verify button posted.", ephemeral=True)
            print(f"/verify used by {interaction.user} in #{interaction.channel}", flush=True)
        except Exception as exc:
            print(f"/verify failed: {exc}", flush=True)
            await interaction.followup.send(f"Error: {exc}", ephemeral=True)

    @bot.command(name="verify")
    @commands.has_permissions(administrator=True)
    async def verify_prefix(ctx: commands.Context) -> None:
        await post_verify_message(ctx.channel)
        await ctx.message.add_reaction("✅")

    return bot

