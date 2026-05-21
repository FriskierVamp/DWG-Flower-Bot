"""
commands/league.py
Dreamweaving Garden Bot — /league command group (everyone)
Member-facing league interactions.

Subcommands:
  /league lock              — mark yourself done for the week
  /league call              — announce that the league is starting (anyone can call)
  /league preview           — see the current week's locked players
"""

import datetime
import discord
from discord import app_commands
from db.queries import (
    set_league_lock, get_guild_league_state, get_league_state,
)
from utils.guards import reject_if_not_setup, reject_if_not_registered

DWG_PURPLE = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0xB8D9B0)
DWG_PINK   = discord.Color(0xF7CCD8)
DWG_YELLOW = discord.Color(0xF7C898)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"


def _current_week_start() -> str:
    """ISO date of the most recent Monday (UTC)."""
    today = datetime.datetime.utcnow().date()
    monday = today - datetime.timedelta(days=today.weekday())
    return monday.isoformat()


def register_league(tree: app_commands.CommandTree) -> None:

    league = app_commands.Group(name="league", description="Weekly league interactions")

    # ── /league lock ───────────────────────────────────────────────
    @league.command(name="lock", description="Mark yourself as done for the current league week")
    async def league_lock(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        week = _current_week_start()
        existing = get_league_state(
            str(interaction.guild_id), str(interaction.user.id), week,
        )
        if existing and existing.get("is_locked"):
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="🔒 You're already locked in for this week.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        set_league_lock(
            str(interaction.guild_id), str(interaction.user.id), week, locked=True,
        )
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🔒 Locked In",
                description=(
                    f"{interaction.user.mention} is **done for week of {week}**.\n"
                    "Good luck! 🌸"
                ),
                color=DWG_MINT,
            ),
            ephemeral=False,
        )

    # ── /league call ───────────────────────────────────────────────
    @league.command(name="call", description="Announce that league has started — rally the guild!")
    async def league_call(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        embed = discord.Embed(
            title="🌟 League Call!",
            description=(
                f"{interaction.user.mention} is calling the guild — **league time!**\n\n"
                "Lock in your runs with `/league lock` once you're done."
            ),
            color=DWG_YELLOW,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(
            content="@here",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(everyone=True),
        )

    # ── /league preview ────────────────────────────────────────────
    @league.command(name="preview", description="See who has locked in for the current week")
    async def league_preview(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        week = _current_week_start()
        rows = get_guild_league_state(str(interaction.guild_id), week)
        locked   = [r for r in rows if r.get("is_locked")]
        unlocked = [r for r in rows if not r.get("is_locked")]

        body_lines = [f"**Week of {week}**\n"]
        if locked:
            body_lines.append(f"🔒 **Locked in ({len(locked)})**")
            body_lines.extend(f"• {r['ign']}" for r in locked[:25])
            if len(locked) > 25:
                body_lines.append(f"_… and {len(locked) - 25} more._")
        else:
            body_lines.append("_No one has locked in yet._")

        if unlocked:
            body_lines.append(f"\n🌱 **Still going ({len(unlocked)})**")
            body_lines.extend(f"• {r['ign']}" for r in unlocked[:25])

        embed = discord.Embed(
            title="🌸 League Preview",
            description="\n".join(body_lines),
            color=DWG_PURPLE,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    tree.add_command(league)
