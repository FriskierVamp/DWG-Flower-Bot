"""
bot.py
Dreamweaving Garden Bot — entry point.
"""

import os
import logging
import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

# ── Logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("dwg.bot")

# ── Config ─────────────────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is not set.")

DWG_PINK = discord.Color(0xF0A8C0)
FOOTER   = "Dreamweaving Garden • Grow together, bloom brighter"

# ── Bot setup ──────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True

bot  = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


# ── Events ─────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    await tree.sync()
    log.info("Slash commands synced.")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="the garden bloom 🌸",
        )
    )
    # Save guild names for all already-connected servers on startup
    from db.schema import upsert_guild_config, is_approved
    for guild in bot.guilds:
        if not is_approved(str(guild.id)):
            log.warning(
                "Already in unauthorized guild %s (%s) — leaving.",
                guild.name, guild.id,
            )
            await guild.leave()
            continue
        try:
            upsert_guild_config(str(guild.id), guild_name=guild.name)
            log.debug("Saved guild name for %s (%s)", guild.name, guild.id)
        except Exception as e:
            log.warning("Could not save guild name for %s: %s", guild.id, e)


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Only allow approved guilds. Leave immediately if not authorized."""
    from db.schema import upsert_guild_config, is_approved
    if not is_approved(str(guild.id)):
        log.warning(
            "Unauthorized guild attempted install: %s (%s) — leaving.",
            guild.name, guild.id,
        )
        await guild.leave()
        return

    # Approved — save guild name
    try:
        upsert_guild_config(str(guild.id), guild_name=guild.name)
        log.info("Joined approved guild: %s (%s)", guild.name, guild.id)
    except Exception as e:
        log.warning("Could not save guild name on join for %s: %s", guild.id, e)


@bot.event
async def on_guild_update(before: discord.Guild, after: discord.Guild):
    """Keep guild name up to date if the server is renamed."""
    if before.name != after.name:
        from db.schema import upsert_guild_config, is_approved
        if not is_approved(str(after.id)):
            return
        try:
            upsert_guild_config(str(after.id), guild_name=after.name)
            log.info("Guild renamed: %s → %s (%s)", before.name, after.name, after.id)
        except Exception as e:
            log.warning("Could not update guild name for %s: %s", after.id, e)


@bot.event
async def on_member_join(member: discord.Member):
    """Auto-assign the 'New' role when someone joins."""
    from db.schema import get_guild_config
    cfg = get_guild_config(str(member.guild.id))
    if not cfg or not cfg.get("new_role_id"):
        return
    try:
        role = member.guild.get_role(int(cfg["new_role_id"]))
    except (ValueError, TypeError):
        return
    if role:
        try:
            await member.add_roles(role, reason="Auto-assigned New role on join")
            log.info("Assigned New role to %s in %s", member, member.guild)
        except discord.Forbidden:
            log.warning("Missing permission to assign New role in %s", member.guild)


@bot.event
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    log.error("Command error: %s", error)
    msg = "Something went wrong. Please try again."
    if isinstance(error, app_commands.CommandOnCooldown):
        msg = f"Slow down! Try again in {error.retry_after:.1f}s."
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                embed=discord.Embed(description=msg, color=DWG_PINK),
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                embed=discord.Embed(description=msg, color=DWG_PINK),
                ephemeral=True,
            )
    except Exception:
        pass


# ── Register all commands ──────────────────────────────────────────
from commands.setup    import register_setup
from commands.register import register_register
from commands.my       import register_my
from commands.lookup   import register_lookup
from commands.league   import register_league
from commands.admin    import register_admin
from commands.help     import register_help

register_setup(tree)
register_register(tree)
register_my(tree)
register_lookup(tree)
register_league(tree)
register_admin(tree)
register_help(tree)


# ── DB + Dashboard + Run ───────────────────────────────────────────
from db.queries import init_db

init_db()
log.info("Database ready.")

from admin.dashboard import start_admin_dashboard
start_admin_dashboard()

bot.run(TOKEN)
