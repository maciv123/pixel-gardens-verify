import asyncio
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
from verify import build_sign_message, compute_role_changes, recover_signer

WEB_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent / "web"


class VerifyRequest(BaseModel):
    session_id: str
    address: str
    signature: str


async def apply_role_changes(
    member: discord.Member,
    to_add: list[int],
    to_remove: list[int],
) -> list[str]:
    guild = member.guild
    assigned: list[str] = []

    for role_id in sorted(set(to_remove)):
        role = guild.get_role(role_id)
        if role is None or role not in member.roles:
            continue
        await member.remove_roles(role, reason="NFT verify tier update")

    for role_id in sorted(set(to_add)):
        role = guild.get_role(role_id)
        if role is None:
            raise RuntimeError(f"Configured role {role_id} was not found in the server")
        if role not in member.roles:
            await member.add_roles(role, reason="NFT verify tier update")
            assigned.append(role.name)

    return assigned


async def _run_on_bot_loop(bot: discord.Client, coro):
    """Run Discord coroutines on the bot's event loop (API runs on a separate thread)."""
    loop = bot.loop
    if loop is None or not loop.is_running():
        raise RuntimeError("Discord bot is not connected yet. Try again in a few seconds.")
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return await asyncio.wrap_future(future)


def create_api(settings: Settings, bot: discord.Client) -> FastAPI:
    app = FastAPI(title="UnFairBears NFT Verify")
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
            to_add, to_remove, balances = compute_role_changes(
                payload.address, settings.collections
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        if not to_add:
            detail = "Wallet does not hold any qualifying NFTs."
            if balances.get("PG", 0) == 0:
                detail = "Wallet does not hold a Pixel Gardens NFT on Robinhood Chain."
            raise HTTPException(status_code=403, detail=detail)

        guild = bot.get_guild(settings.discord_guild_id)
        if guild is None:
            raise HTTPException(status_code=503, detail="Discord server not available")

        async def assign_member_roles() -> list[str]:
            member = guild.get_member(int(row["discord_user_id"]))
            if member is None:
                member = await guild.fetch_member(int(row["discord_user_id"]))
            return await apply_role_changes(member, to_add, to_remove)

        try:
            assigned = await _run_on_bot_loop(bot, assign_member_roles())
        except discord.NotFound as exc:
            raise HTTPException(
                status_code=404, detail="Discord member not found in server"
            ) from exc
        except discord.Forbidden as exc:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Bot lacks permission to assign roles. Move the bot's role above "
                    "holder/tier roles and enable Manage Roles."
                ),
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        save_verification(settings.db_path, row["discord_user_id"], payload.address)
        mark_session_used(settings.db_path, payload.session_id)

        return {
            "status": "verified",
            "wallet": payload.address.lower(),
            "roles": assigned,
            "balances": balances,
        }

    return app


class VerifyView(discord.ui.View):
    def __init__(self, settings: Settings):
        super().__init__(timeout=None)
        self.settings = settings

    @discord.ui.button(
        label="Verify NFTs",
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
            "**Connect your wallet to verify:**\n"
            f"{verify_url}\n\n"
            "Open that link → connect MetaMask on **Robinhood Chain** → sign. "
            "Roles are assigned automatically.",
            ephemeral=True,
        )


async def _start_verify_flow(
    interaction: discord.Interaction, settings: Settings
) -> None:
    existing = get_verification_by_discord(
        settings.db_path, str(interaction.user.id)
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
        settings.db_path,
        session_id,
        str(interaction.user.id),
        nonce,
        expires_at,
    )
    verify_url = f"{settings.verify_base_url}/?session={session_id}"
    await interaction.response.send_message(
        "**Connect your wallet to verify:**\n"
        f"{verify_url}\n\n"
        "Tap/click the link above → connect MetaMask on **Robinhood Chain** → sign. "
        "Roles are assigned automatically.",
        ephemeral=True,
    )


def create_bot(settings: Settings) -> commands.Bot:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.message_content = True

    guild = discord.Object(id=settings.discord_guild_id)

    class PixelGardensBot(commands.Bot):
        async def setup_hook(self) -> None:
            self.add_view(VerifyView(settings))
            synced = await self.tree.sync(guild=guild)
            names = [cmd.name for cmd in synced]
            print(
                f"Synced {len(synced)} command(s) to {settings.discord_guild_id}: {names}",
                flush=True,
            )

        async def on_ready(self) -> None:
            print(f"Logged in as {self.user} (id={self.user.id})", flush=True)
            print(f"Verify URL base: {settings.verify_base_url}", flush=True)

    bot = PixelGardensBot(command_prefix="!", intents=intents)

    @bot.tree.error
    async def on_app_command_error(
        interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        print(f"Command error: {error}", flush=True)
        msg = f"Something went wrong: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    async def post_verify_message(channel: discord.abc.Messageable) -> None:
        text = (
            "**UnFairBears NFT Verification**\n\n"
            "Own **Pixel Gardens** NFTs? Click **Verify NFTs** below, "
            "connect your wallet on **Robinhood Chain**, and get your tier roles."
        )
        await channel.send(content=text, view=VerifyView(settings))

    @bot.tree.command(
        name="verify",
        description="Verify your NFT holdings — connect wallet and get roles",
        guild=guild,
    )
    async def verify_slash(interaction: discord.Interaction) -> None:
        try:
            await _start_verify_flow(interaction, settings)
            print(f"/verify started for {interaction.user}", flush=True)
        except Exception as exc:
            print(f"/verify failed: {exc}", flush=True)
            if interaction.response.is_done():
                await interaction.followup.send(f"Error: {exc}", ephemeral=True)
            else:
                await interaction.response.send_message(f"Error: {exc}", ephemeral=True)

    @bot.tree.command(
        name="setup-verify",
        description="(Admin) Post a public Verify button in this channel",
        guild=guild,
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_verify_slash(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Posting public verify button...", ephemeral=True
        )
        try:
            await post_verify_message(interaction.channel)
            print(f"/setup-verify completed for {interaction.user}", flush=True)
        except discord.Forbidden as exc:
            print(f"/setup-verify failed: {exc}", flush=True)
            await interaction.followup.send(
                "I can't post in this channel. Give **Unfair Bot** **Send Messages** "
                "in this channel (Edit Channel → Permissions).",
                ephemeral=True,
            )
        except Exception as exc:
            print(f"/setup-verify failed: {exc}", flush=True)
            await interaction.followup.send(f"Error: {exc}", ephemeral=True)

    @bot.command(name="verify")
    async def verify_prefix(ctx: commands.Context) -> None:
        existing = get_verification_by_discord(
            settings.db_path, str(ctx.author.id)
        )
        if existing is not None:
            await ctx.reply(
                f"You are already verified with `{existing['wallet_address']}`.",
                mention_author=False,
            )
            return
        session_id = secrets.token_hex(16)
        nonce = secrets.token_hex(8)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        create_session(
            settings.db_path,
            session_id,
            str(ctx.author.id),
            nonce,
            expires_at,
        )
        verify_url = f"{settings.verify_base_url}/?session={session_id}"
        await ctx.reply(
            f"Open this link to verify (Robinhood Chain + MetaMask): {verify_url}",
            mention_author=True,
        )

    return bot

