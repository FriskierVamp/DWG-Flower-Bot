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
    get_top_flowers_for_league_call,
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

        guild_id = str(interaction.guild_id)
        top = get_top_flowers_for_league_call(guild_id, top_n=2)

        # ── Build the ping line and embed body ─────────────────────
        ping_ids:  list[str] = []   # discord IDs to hard-ping (first holder of each tier)
        body_lines: list[str] = []

        tier_labels = ["🌸 **Best flower**", "🌼 **Second-best flower**"]

        for i, entry in enumerate(top):
            flower   = entry["flower_name"]
            pts      = entry["effective_pts"]
            upgraded = entry["is_upgraded"]
            holders  = entry["holders"]

            label    = tier_labels[i] if i < len(tier_labels) else f"**#{i+1} flower**"
            upgrade_tag = "✨ *Upgraded*" if upgraded else "🌱 *Regular*"
            pt_str   = f"{pts} pts" + (" (×2)" if upgraded else "")

            # First holder gets a hard ping; the rest are mentioned by IGN only
            first    = holders[0]
            rest     = holders[1:]

            ping_ids.append(first["discord_id"])

            mention_first = f"<@{first['discord_id']}>"
            rest_names    = ", ".join(h["ign"] for h in rest)

            line = f"{label} — **{flower}** ({pt_str}) {upgrade_tag}\n  → {mention_first}"
            if rest_names:
                line += f"  *(also held by: {rest_names})*"
            body_lines.append(line)

        if not body_lines:
            body_lines = ["_No flower data found yet — get registering!_"]

        ping_content = " ".join(f"<@{did}>" for did in ping_ids) if ping_ids else "@here"

        desc = (
            f"{interaction.user.mention} is calling the guild \u2014 **league time!**\n\n"
            + "\n\n".join(body_lines)
            + "\n\nLock in your runs with `/league lock` once you're done. \U0001f338"
        )

        embed = discord.Embed(
            title="🌟 League Call!",
            description=desc,
            color=DWG_YELLOW,
        )
        embed.set_footer(text=FOOTER)

        await interaction.response.send_message(
            content=ping_content,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=True),
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
