"""
commands/league.py
Dreamweaving Garden Bot — /league command group (everyone)
Member-facing league interactions.

Subcommands:
  /league lock    — mark yourself done for the week
  /league call    — announce a flower call to rally holders
  /league preview — privately preview whether a call is worth posting
"""

import datetime
import discord
from discord import app_commands
from db.queries import (
    set_league_lock, get_guild_league_state, get_league_state,
    get_flower_names_for_autocomplete, get_league_call_holders,
    get_player_vip, find_flower_match,
)
from db.schema import get_guild_config
from utils.guards import reject_if_not_setup, reject_if_not_registered

DWG_PURPLE = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0xB8D9B0)
DWG_PINK   = discord.Color(0xF7CCD8)
DWG_YELLOW = discord.Color(0xF7C898)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"


def _current_week_start() -> str:
    today  = datetime.datetime.utcnow().date()
    monday = today - datetime.timedelta(days=today.weekday())
    return monday.isoformat()


def _lock_thresholds(guild_id: str) -> tuple[int, int]:
    """Return (regular_threshold, vip_threshold) for this guild.
    Falls back to (21, 26) if not configured."""
    cfg = get_guild_config(guild_id)
    if not cfg:
        return 21, 26
    try:
        regular = int(cfg.get("lock_threshold") or 21)
    except (TypeError, ValueError):
        regular = 21
    try:
        vip = int(cfg.get("vip_lock_threshold") or 26)
    except (TypeError, ValueError):
        vip = 26
    return regular, vip


def register_league(tree: app_commands.CommandTree) -> None:

    league = app_commands.Group(name="league", description="Weekly league interactions")

    # ── /league lock ───────────────────────────────────────────────
    @league.command(name="lock", description="Mark yourself as done for this league week")
    async def league_lock(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        guild_id   = str(interaction.guild_id)
        discord_id = str(interaction.user.id)
        week       = _current_week_start()

        existing = get_league_state(guild_id, discord_id, week)
        if existing and existing.get("is_locked"):
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="🔒 You're already locked in for this week.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        regular_threshold, vip_threshold = _lock_thresholds(guild_id)
        is_vip     = get_player_vip(guild_id, discord_id)
        lock_tier  = vip_threshold if is_vip else regular_threshold
        vip_note   = " _(VIP)_" if is_vip else ""

        set_league_lock(guild_id, discord_id, week, locked=True)

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🔒 Locked In",
                description=(
                    f"{interaction.user.mention} has locked at **{lock_tier} tasks**{vip_note}.\n"
                    f"You're done for the week — great work! 🌸"
                ),
                color=DWG_MINT,
            ),
            ephemeral=False,
        )

    # ── /league call ───────────────────────────────────────────────
    async def flower_autocomplete(
        interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        names = get_flower_names_for_autocomplete()
        return [
            app_commands.Choice(name=n, value=n)
            for n in names if current.lower() in n.lower()
        ][:25]

    @league.command(name="call", description="Call the league — pick a flower and tier to rally holders")
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
        best        = data["best"]
        second_best = data["second_best"]
        rest        = data["rest"]

        SEP = "─" * 28

        if is_upgraded:
            header = f"🚨 UPGRADED 🚨 **{flower}** · {pts} pts"
            color  = discord.Color(0xFF4500)
        else:
            header = f"🌸 **{flower}** · Regular · {pts} pts"
            color  = DWG_YELLOW

        def mention_list(group):
            return " ".join(f"<@{p['discord_id']}>" for p in group)

        def ign_list(group):
            return ", ".join(p["ign"] for p in group)

        # Build message body — pings live inline on Best/Second Best lines
        lines = [header, SEP]

        if best:
            lines.append(f"🌸 **Best Flower** — {mention_list(best)}")
        else:
            lines.append("🌸 **Best Flower** — _None_")

        if second_best:
            lines.append(f"🌼 **Second Best** — {mention_list(second_best)}")
        else:
            lines.append("🌼 **Second Best** — _None_")

        if rest:
            lines.append(f"🌿 **Also Have It** — {ign_list(rest)}")

        lines.append(SEP)

        # content must carry the mentions so Discord sends notifications
        # No standalone ping line — mentions are embedded in the body lines above
        all_ping_ids = [p["discord_id"] for p in best + second_best]
        hidden_pings = " ".join(f"<@{uid}>" for uid in all_ping_ids) if all_ping_ids else ""

        # Discord requires mention IDs appear in `content` to actually notify.
        # We put them invisibly at the start (zero-width space trick not needed —
        # Discord counts any mention in content, even if it also appears in the body).
        message_body = "\n".join(lines)

        await interaction.response.send_message(
            content=f"{hidden_pings}\n{message_body}" if hidden_pings else message_body,
            allowed_mentions=discord.AllowedMentions(users=True),
        )

    # ── /league preview ────────────────────────────────────────────
    async def preview_flower_autocomplete(
        interaction: discord.Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        names = get_flower_names_for_autocomplete()
        return [
            app_commands.Choice(name=n, value=n)
            for n in names if current.lower() in n.lower()
        ][:25]

    @league.command(name="preview", description="Privately preview whether a league flower call is worth posting")
    @app_commands.describe(flower="The flower you are considering calling")
    @app_commands.autocomplete(flower=preview_flower_autocomplete)
    async def league_preview(interaction: discord.Interaction, flower: str):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        guild_id = str(interaction.guild_id)
        matched  = find_flower_match(flower)
        if not matched:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ Flower **{flower}** not found.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        data = get_league_call_holders(guild_id, matched, is_upgraded=False)
        if not data:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ No data found for **{matched}**.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        best         = data["best"]
        second_best  = data["second_best"]
        rest         = data["rest"]
        base_pts     = data["base_points"]
        upgraded_pts = base_pts * 2
        total_have   = len(best) + len(second_best) + len(rest)

        if total_have == 0:
            recommendation = "Probably not — no one in this guild has this flower."
        elif len(best) + len(second_best) > 0:
            recommendation = "Yes — at least one player would be pinged."
        else:
            recommendation = "Maybe — players have it but it's not their top 2 flower."

        SEP = "─" * 28
        lines = [
            f"**{matched}**",
            f"Regular: {base_pts} pts  |  Upgraded: {upgraded_pts} pts",
            SEP,
            f"🌸 **Best Flower:** {len(best)}",
            f"🌼 **Second Best:** {len(second_best)}",
            f"🌿 **Also Have It:** {len(rest)}",
            "",
            f"**Worth posting?** {recommendation}",
        ]

        if best:
            lines += ["", "🌸 **Best Flower:**", ", ".join(p["ign"] for p in best)]
        if second_best:
            lines += ["", "🌼 **Second Best:**", ", ".join(p["ign"] for p in second_best)]
        if rest:
            lines += ["", "🌿 **Also Have It:**", ", ".join(p["ign"] for p in rest)]

        lines.append(SEP)

        embed = discord.Embed(
            title="👁️ League Preview",
            description="\n".join(lines),
            color=DWG_PURPLE,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    tree.add_command(league)
