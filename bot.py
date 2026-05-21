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

bot = discord.Client(intents=intents)
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


@bot.event
async def on_member_join(member: discord.Member):
    """Auto-assign the Seedling role when someone joins."""
    from db.queries import get_guild_config
    cfg = get_guild_config(str(member.guild.id))
    if not cfg or not cfg.get("seedling_role_id"):
        return
    role = member.guild.get_role(int(cfg["seedling_role_id"]))
    if role:
        try:
            await member.add_roles(role, reason="Auto-assigned Seedling on join")
            log.info("Assigned Seedling to %s in %s", member, member.guild)
        except discord.Forbidden:
            log.warning("Missing permission to assign Seedling in %s", member.guild)


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
from commands.track    import register_track
from commands.add      import register_add
from commands.lookup   import register_lookup
from commands.league   import register_league
from commands.admin    import register_admin

register_setup(tree)
register_register(tree)
register_track(tree)
register_add(tree)
register_lookup(tree)
register_league(tree)
register_admin(tree)


# ── DB + Dashboard + Run ───────────────────────────────────────────
from db.queries import init_db

init_db()
log.info("Database ready.")

from admin.dashboard import start_admin_dashboard
start_admin_dashboard()

bot.run(TOKEN)
