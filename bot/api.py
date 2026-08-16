import asyncio
import os
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
    count_verifications,
    create_session,
    get_first_verifier_ids,
    get_session,
    get_verification_by_discord,
    get_verification_by_wallet,
    is_og_verifier,
    mark_session_used,
    save_verification,
)
from sessions import build_verify_url, new_session_id, normalize_session_id
from verify import build_sign_message, compute_role_changes, recover_signer

WEB_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent / "web"


class VerifyRequest(BaseModel):
    session_id: str
    address: str
    signature: str


class VerifyResponse(BaseModel):
    status: str
    wallet: str
    roles: list[str]
    balances: dict[str, int]


def _short_wallet(address: str) -> str:
    if len(address) < 12:
        return address
    return f"{address[:6]}...{address[-4:]}"


def _verify_embed(verify_url: str) -> discord.Embed:
    embed = discord.Embed(
        title="Pixel Gardens Verification",
        description=(
            "Verify your NFT holdings on **Robinhood Chain** "
            "and receive the correct tier roles."
        ),
        color=0x00AA55,
    )
    embed.add_field(
        name="1. Open verify page",
        value=f"[Click here to verify]({verify_url})",
        inline=False,
    )
    embed.add_field(
        name="2. Connect & sign",
        value="Connect MetaMask on Robinhood Chain, then sign the message.",
        inline=False,
    )
    embed.set_footer(text="Single-use link · Expires in 15 minutes · Only you can see this")
    return embed


def _create_verify_session(settings: Settings, discord_user_id: str) -> tuple[str, str]:
    session_id = new_session_id()
    nonce = secrets.token_hex(8)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    create_session(
        settings.db_path,
        session_id,
        discord_user_id,
        nonce,
        expires_at,
    )
    return session_id, build_verify_url(settings.verify_base_url, session_id)


def _already_verified_embed(wallet: str) -> discord.Embed:
    embed = discord.Embed(
        title="Already Verified",
        description=f"Your wallet **{_short_wallet(wallet)}** is linked to this Discord account.",
        color=0x5865F2,
    )
    embed.set_footer(text="Run /verify again to refresh your tier roles.")
    return embed


def _resolve_role_names(guild: discord.Guild, role_ids: list[int]) -> list[str]:
    names: list[str] = []
    for role_id in sorted(set(role_ids)):
        role = guild.get_role(role_id)
        names.append(role.name if role is not None else f"role-{role_id}")
    return names


def _roles_refreshed_embed(
    wallet: str,
    stacked_roles: list[str],
    newly_assigned: list[str],
    balances: dict[str, int],
) -> discord.Embed:
    embed = discord.Embed(
        title="Roles Updated",
        description=(
            f"Stacked tier roles refreshed for wallet **{_short_wallet(wallet)}**."
        ),
        color=0x00AA55,
    )
    if stacked_roles:
        embed.add_field(
            name="Your stacked roles",
            value=", ".join(stacked_roles),
            inline=False,
        )
    if newly_assigned:
        embed.add_field(
            name="Newly assigned",
            value=", ".join(newly_assigned),
            inline=False,
        )
    elif stacked_roles:
        embed.add_field(
            name="Newly assigned",
            value="You already had all stacked roles.",
            inline=False,
        )
    pg_balance = balances.get("PG")
    if pg_balance is not None:
        embed.add_field(name="PG balance", value=str(pg_balance), inline=True)
    return embed


async def _refresh_roles_for_user(
    interaction: discord.Interaction,
    settings: Settings,
    wallet_address: str,
) -> tuple[list[str], list[str], dict[str, int]]:
    bot = interaction.client
    if not isinstance(bot, discord.Client):
        raise RuntimeError("Bot is not available")

    guild = bot.get_guild(settings.discord_guild_id)
    if guild is None:
        raise RuntimeError("Discord server not available")

    to_add, to_remove, balances = compute_role_changes(
        wallet_address, settings.collections
    )
    stacked_roles = _resolve_role_names(guild, to_add)

    if not to_add:
        raise ValueError("Wallet does not hold any qualifying NFTs.")

    async def assign_roles() -> list[str]:
        member = guild.get_member(interaction.user.id)
        if member is None:
            member = await guild.fetch_member(interaction.user.id)
        assigned = await apply_role_changes(member, to_add, to_remove)
        assigned.extend(await grant_og_role_if_eligible(member, settings))
        return assigned

    assigned = await _run_on_bot_loop(bot, assign_roles())
    return assigned, stacked_roles, balances


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


async def grant_og_role_if_eligible(
    member: discord.Member,
    settings: Settings,
) -> list[str]:
    assigned: list[str] = []
    if settings.pg_role_og is None:
        return assigned

    if not is_og_verifier(
        settings.db_path,
        str(member.id),
        settings.og_verifier_limit,
    ):
        return assigned

    role = member.guild.get_role(settings.pg_role_og)
    if role is None:
        raise RuntimeError(
            f"Configured OG role {settings.pg_role_og} was not found in the server"
        )

    if role not in member.roles:
        await member.add_roles(role, reason="OG Pixel Garden verifier")
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

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        build = os.getenv("RAILWAY_GIT_COMMIT_SHA", "local")
        return {
            "status": "ok",
            "build": build[:12] if build else "local",
            "refresh_roles": "enabled",
        }

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/verify/{session_id}")
    async def verify_page(session_id: str) -> FileResponse:
        try:
            normalize_session_id(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Invalid verification link") from exc
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/api/session/{session_id}")
    async def get_session_info(session_id: str) -> dict[str, Any]:
        try:
            session_id = normalize_session_id(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Invalid verification link") from exc
        row = get_session(settings.db_path, session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")

        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if row["used"]:
            raise HTTPException(
                status_code=410,
                detail="This link was already used. Return to Discord and run /verify for a new link.",
            )
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(status_code=410, detail="Session expired")

        message = build_sign_message(row["discord_user_id"], row["nonce"])
        return {
            "session_id": session_id,
            "message": message,
            "chain_id": settings.chain_id,
            "contract_address": settings.contract_address,
        }

    @app.post("/api/verify", response_model=VerifyResponse)
    async def verify_holder(payload: VerifyRequest) -> VerifyResponse:
        try:
            session_id = normalize_session_id(payload.session_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Invalid verification link") from exc
        payload = VerifyRequest(
            session_id=session_id,
            address=payload.address,
            signature=payload.signature,
        )
        row = get_session(settings.db_path, payload.session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")

        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if row["used"]:
            raise HTTPException(
                status_code=410,
                detail="This link was already used. Return to Discord and run /verify for a new link.",
            )
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
            assigned = await apply_role_changes(member, to_add, to_remove)
            save_verification(
                settings.db_path, row["discord_user_id"], payload.address
            )
            assigned.extend(await grant_og_role_if_eligible(member, settings))
            return assigned

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

        mark_session_used(settings.db_path, payload.session_id)

        return VerifyResponse(
            status="verified",
            wallet=payload.address.lower(),
            roles=assigned,
            balances=balances,
        )

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
        await interaction.response.defer(ephemeral=True)
        existing = get_verification_by_discord(
            self.settings.db_path, str(interaction.user.id)
        )
        if existing is not None:
            try:
                assigned, stacked_roles, balances = await _refresh_roles_for_user(
                    interaction, self.settings, existing["wallet_address"]
                )
                await interaction.followup.send(
                    embed=_roles_refreshed_embed(
                        existing["wallet_address"],
                        stacked_roles,
                        assigned,
                        balances,
                    ),
                    ephemeral=True,
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "I can't update roles. Move **Unfair Bot** above tier roles "
                    "and enable **Manage Roles**.",
                    ephemeral=True,
                )
            except Exception as exc:
                await interaction.followup.send(
                    f"Could not refresh roles: {exc}", ephemeral=True
                )
            return

        _, verify_url = _create_verify_session(
            self.settings, str(interaction.user.id)
        )
        await interaction.followup.send(
            embed=_verify_embed(verify_url),
            ephemeral=True,
        )


async def _start_verify_flow(
    interaction: discord.Interaction, settings: Settings
) -> None:
    await interaction.response.defer(ephemeral=True)
    existing = get_verification_by_discord(
        settings.db_path, str(interaction.user.id)
    )
    if existing is not None:
        try:
            assigned, stacked_roles, balances = await _refresh_roles_for_user(
                interaction, settings, existing["wallet_address"]
            )
            await interaction.followup.send(
                embed=_roles_refreshed_embed(
                    existing["wallet_address"],
                    stacked_roles,
                    assigned,
                    balances,
                ),
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "I can't update roles. Move **Unfair Bot** above tier roles "
                "and enable **Manage Roles**.",
                ephemeral=True,
            )
        except Exception as exc:
            await interaction.followup.send(
                f"Could not refresh roles: {exc}", ephemeral=True
            )
        return

    _, verify_url = _create_verify_session(settings, str(interaction.user.id))
    await interaction.followup.send(
        embed=_verify_embed(verify_url),
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
            try:
                synced = await self.tree.sync(guild=guild)
            except Exception as exc:
                print(f"Command sync failed: {exc}", flush=True)
                raise
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
        if isinstance(error, app_commands.CommandNotFound):
            msg = (
                "Bot just restarted. Open the slash menu and pick `/verify` again "
                "(don’t tap an old cached suggestion)."
            )
        else:
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
        description="Verify NFTs or refresh your stacked tier roles",
        guild=guild,
    )
    async def verify_slash(interaction: discord.Interaction) -> None:
        try:
            await _start_verify_flow(interaction, settings)
            print(f"/verify completed for {interaction.user}", flush=True)
        except discord.NotFound as exc:
            print(f"/verify interaction expired: {exc}", flush=True)
            if interaction.response.is_done():
                await interaction.followup.send(
                    "That menu entry expired. Open the slash menu and pick `/verify` again.",
                    ephemeral=True,
                )
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

    @bot.tree.command(
        name="og-status",
        description="(Admin) Show first OG-eligible verifiers and OG role status",
        guild=guild,
    )
    @app_commands.default_permissions(administrator=True)
    async def og_status_slash(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        total = count_verifications(settings.db_path)
        if settings.pg_role_og is None:
            await interaction.followup.send(
                f"Total verifications: {total}\nPG_ROLE_OG is not configured.",
                ephemeral=True,
            )
            return

        guild_obj = bot.get_guild(settings.discord_guild_id)
        if guild_obj is None:
            await interaction.followup.send("Discord server not available.", ephemeral=True)
            return

        role = guild_obj.get_role(settings.pg_role_og)
        role_label = role.name if role is not None else f"missing role {settings.pg_role_og}"

        verifier_ids = get_first_verifier_ids(
            settings.db_path, settings.og_verifier_limit
        )
        lines = [
            f"Total verifications: {total}",
            f"OG role: {role_label} ({settings.pg_role_og})",
            f"First {settings.og_verifier_limit} by verify time:",
        ]

        if not verifier_ids:
            lines.append("— none yet —")
        else:
            for idx, user_id in enumerate(verifier_ids, start=1):
                member = guild_obj.get_member(int(user_id))
                if member is None:
                    try:
                        member = await guild_obj.fetch_member(int(user_id))
                    except discord.NotFound:
                        lines.append(f"{idx}. `{user_id}` — left server")
                        continue
                has_og = role is not None and role in member.roles
                lines.append(
                    f"{idx}. {member.display_name} — OG: {'yes' if has_og else 'NO'}"
                )

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @bot.tree.command(
        name="og-backfill",
        description="(Admin) Assign OG role to first verifiers still in server",
        guild=guild,
    )
    @app_commands.default_permissions(administrator=True)
    async def og_backfill_slash(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        if settings.pg_role_og is None:
            await interaction.followup.send(
                "PG_ROLE_OG is not configured.", ephemeral=True
            )
            return

        guild_obj = bot.get_guild(settings.discord_guild_id)
        if guild_obj is None:
            await interaction.followup.send(
                "Discord server not available.", ephemeral=True
            )
            return

        role = guild_obj.get_role(settings.pg_role_og)
        if role is None:
            await interaction.followup.send(
                f"OG role {settings.pg_role_og} was not found in the server.",
                ephemeral=True,
            )
            return

        verifier_ids = get_first_verifier_ids(
            settings.db_path, settings.og_verifier_limit
        )
        if not verifier_ids:
            await interaction.followup.send(
                "No verifications in the database yet. OG is assigned to the first "
                f"{settings.og_verifier_limit} people who complete wallet verify.",
                ephemeral=True,
            )
            return

        assigned_names: list[str] = []
        already_had: list[str] = []
        skipped: list[str] = []
        failed: list[str] = []

        for user_id in verifier_ids:
            member = guild_obj.get_member(int(user_id))
            if member is None:
                try:
                    member = await guild_obj.fetch_member(int(user_id))
                except discord.NotFound:
                    skipped.append(user_id)
                    continue

            if role in member.roles:
                already_had.append(member.display_name)
                continue

            try:
                await member.add_roles(
                    role, reason="OG Pixel Garden verifier backfill"
                )
                assigned_names.append(member.display_name)
            except discord.Forbidden:
                failed.append(member.display_name)

        lines: list[str] = [
            f"First {len(verifier_ids)} verifier(s) in database (by verify time)."
        ]
        if assigned_names:
            lines.append(f"Assigned OG: {', '.join(assigned_names)}")
        if already_had:
            lines.append(f"Already had OG: {', '.join(already_had)}")
        if skipped:
            lines.append(f"Not in server anymore: {len(skipped)} user(s)")
        if failed:
            lines.append(
                f"Could not assign (move bot above OG role): {', '.join(failed)}"
            )
        if not assigned_names and not already_had and not failed:
            lines.append("No OG roles assigned.")

        await interaction.followup.send("\n".join(lines), ephemeral=True)
        print(f"/og-backfill completed for {interaction.user}", flush=True)

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
        _, verify_url = _create_verify_session(settings, str(ctx.author.id))
        await ctx.reply(
            f"Open this link to verify (Robinhood Chain + MetaMask): {verify_url}",
            mention_author=True,
        )

    return bot

