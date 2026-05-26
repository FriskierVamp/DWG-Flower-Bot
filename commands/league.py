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
    get_flower_names_for_autocomplete, get_league_call_holders,
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
    async def flower_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        names = get_flower_names_for_autocomplete()
        return [
            app_commands.Choice(name=n, value=n)
            for n in names
            if current.lower() in n.lower()
        ][:25]

    @league.command(name="call", description="Call the league — pick a flower and its tier to rally holders")
    @app_commands.describe(
        flower="The flower being called for this league run",
        upgraded="Is the flower upgraded? Upgraded = double points",
    )
    @app_commands.autocomplete(flower=flower_autocomplete)
    @app_commands.choices(upgraded=[
        app_commands.Choice(name="Regular", value=0),
        app_commands.Choice(name="Upgraded (×2 points)", value=1),
    ])
    async def league_call(
        interaction: discord.Interaction,
        flower: str,
        upgraded: app_commands.Choice[int],
    ):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        is_upgraded = bool(upgraded.value)
        guild_id    = str(interaction.guild_id)

        data = get_league_call_holders(guild_id, flower, is_upgraded)

        if not data:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ Flower **{flower}** not found in the database.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        pts         = data["effective_pts"]
        base_pts    = data["base_points"]
        best        = data["best"]
        second_best = data["second_best"]
        rest        = data["rest"]

        upgrade_label = "✨ Upgraded" if is_upgraded else "🌱 Regular"
        pt_label      = f"{pts} pts" + (" (×2)" if is_upgraded else "")

        # ── Pings: everyone in best + second_best gets tagged ──────
        ping_ids = [p["discord_id"] for p in best + second_best]
        ping_content = " ".join(f"<@{did}>" for did in ping_ids) if ping_ids else ""

        # ── Build embed body ────────────────────────────────────────
        lines = []

        if best:
            mentions = " ".join(f"<@{p['discord_id']}>" for p in best)
            lines.append(f"🌸 **Best flower** — {mentions}")
        else:
            lines.append("🌸 **Best flower** — _no one has this as their top flower_")

        if second_best:
            mentions = " ".join(f"<@{p['discord_id']}>" for p in second_best)
            lines.append(f"🌼 **Second-best flower** — {mentions}")
        else:
            lines.append("🌼 **Second-best flower** — _no one has this as their second flower_")

        if rest:
            names = ", ".join(p["ign"] for p in rest)
            lines.append(f"🌿 **Also have it** — {names}")

        if not (best or second_best or rest):
            lines.append("_No one in the guild has this flower yet._")

        desc = "\n".join(lines)

        embed = discord.Embed(
            title=f"🌟 {flower} — {upgrade_label} · {pt_label}",
            description=desc,
            color=DWG_YELLOW,
        )
        embed.set_footer(text=FOOTER)

        await interaction.response.send_message(
            content=ping_content or None,
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
