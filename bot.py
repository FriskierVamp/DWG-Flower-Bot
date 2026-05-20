"""
bot.py
Dreamweaving Garden Bot — Entry point
"""

import os
import logging
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from db.schema import init_db
from commands.setup    import register_setup
from commands.register import register_register
from commands.track    import register_track
from commands.lookup   import register_lookup
from commands.add      import register_add
from commands.league   import register_league
from commands.admin    import register_admin
from admin.dashboard   import start_admin_dashboard

# ------------------------------------------------------------------
# ENV + LOGGING
# ------------------------------------------------------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN not found in environment.")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("dwg")

# ------------------------------------------------------------------
# BOT SETUP
# ------------------------------------------------------------------
intents = discord.Intents.default()
intents.members         = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ------------------------------------------------------------------
# STYLE CONSTANTS
# ------------------------------------------------------------------
DWG_PURPLE = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0xB8D9B0)
DWG_YELLOW = discord.Color(0xF7C898)
DWG_PINK   = discord.Color(0xF7CCD8)
DWG_BLUE   = discord.Color(0xB8D8F0)
DWG_GOLD   = discord.Color(0xE8C878)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"
DIVIDER    = "━━━━━━━━━━━━━━━━━━━"

# ------------------------------------------------------------------
# EVENTS
# ------------------------------------------------------------------

@bot.event
async def on_ready():
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    log.info("Connected to %d server(s)", len(bot.guilds))
    try:
        synced = await bot.tree.sync()
        log.info("Synced %d slash command(s)", len(synced))
    except Exception as e:
        log.error("Failed to sync commands: %s", e)

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="the garden bloom 🌸",
        )
    )


@bot.event
async def on_guild_join(guild: discord.Guild):
    log.info("Joined new server: %s (ID: %s)", guild.name, guild.id)
    try:
        owner = guild.owner
        if owner:
            embed = discord.Embed(
                title="🌸 Thanks for adding Dreamweaving Garden!",
                description=(
                    f"Hello! I've just joined **{guild.name}**.\n\n"
                    "Before your members can use any commands, a server admin "
                    "needs to complete the one-time setup.\n\n"
                    "**To get started:**\n"
                    "1. Go to your server\n"
                    "2. Run the `/setup` command\n"
                    "3. Follow the 3-step wizard — it takes about 2 minutes\n\n"
                    "**What `/setup` configures:**\n"
                    "• The role new players receive\n"
                    "• The role players get after `/register`\n"
                    "• Which role(s) have leader permissions\n"
                    "• The channel for public log posts\n\n"
                    "Once setup is complete, members can use `/register` to join.\n\n"
                    "Need help? Use `/help` inside your server at any time."
                ),
                color=DWG_PURPLE,
            )
            await owner.send(embed=embed)
    except discord.Forbidden:
        log.warning("Could not DM owner of %s — DMs disabled.", guild.name)
    except Exception as e:
        log.error("on_guild_join error: %s", e)


@bot.event
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    log.error("Slash command error: %s", error)
    msg = "Something went wrong. Please try again."
    if isinstance(error, app_commands.CommandOnCooldown):
        msg = f"Slow down! Try again in {error.retry_after:.1f}s."
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)
    except Exception:
        pass


# ------------------------------------------------------------------
# REGISTER ALL COMMANDS
# ------------------------------------------------------------------
register_setup(bot.tree)
register_register(bot.tree)
register_track(bot.tree)
register_lookup(bot.tree)
register_add(bot.tree)
register_league(bot.tree)
register_admin(bot.tree)

# ------------------------------------------------------------------
# INIT + RUN
# ------------------------------------------------------------------
init_db()
start_admin_dashboard()
bot.run(TOKEN)
