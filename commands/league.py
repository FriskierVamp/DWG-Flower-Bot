"""
commands/league.py
Dreamweaving Garden Bot — /league command group
Weekly league event system. Equivalent to TCF's /comp but renamed for DWG.
Handles flower callouts (max/second best tagged), locking, and remaining views.
"""

import json
import datetime
import discord
from discord import app_commands
from db.queries import (
    get_player_flowers, get_players_with_flower, find_flower_match,
    get_flower, get_all_players, get_league_state, set_league_lock,
    get_guild_league_state, get_guild_league_standings,
    get_flower_names_for_autocomplete, find_player, RARITY_ORDER,
)
from utils.guards import (
    reject_if_not_setup, reject_if_not_registered, reject_if_not_leader,
)

DWG_PURPLE = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0xB8D9B0)
DWG_PINK   = discord.Color(0xF7CCD8)
DWG_GOLD   = discord.Color(0xE8C878)
DWG_BLUE   = discord.Color(0xB8D8F0)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"

RARITY_ICON = {
    "Shine": "✦",
    "Star":  "★",
    "Rare":  "◆",
    "Fine":  "◇",
    "Basic": "·",
}


def current_week_start() -> str:
    """Returns the ISO date string of the most recent Monday."""
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    return monday.isoformat()


def build_callout(
    guild_id: str,
    guild: discord.Guild,
    flower_name: str,
    upgraded: bool = False,
) -> tuple[discord.Embed | None, str | None]:
    """
    Build the league callout embed for a flower.
    Returns (embed, error_message).
    Max and second-best owners are tagged by Discord mention.
    Others are listed by IGN only — no tag.
    """
    flower_data = get_flower(flower_name)
    if not flower_data:
        return None, f"**{flower_name}** isn't in the master flower list."

    owners = get_players_with_flower(guild_id, flower_name)
    if not owners:
        return None, f"Nobody in the guild has **{flower_name}** tracked."

    base_pts     = flower_data["base_points"]
    display_pts  = base_pts * 2 if upgraded else base_pts
    icon         = RARITY_ICON.get(flower_data["rarity"], "·")
    upgrade_note = " *(upgraded ×2)*" if upgraded else ""

    # Sort owners by their league points — use latest league entry for scoring
    # For now rank by IGN alphabetically; will refine once league data flows in
    # Max = first in list, second best = second
    tag_count = min(2, len(owners))
    tagged    = owners[:tag_count]
    untagged  = owners[tag_count:]

    lines_tagged   = []
    lines_untagged = []

    for i, p in enumerate(tagged):
        member = guild.get_member(int(p["discord_id"]))
        label  = "🌟 **Max**" if i == 0 else "⭐ **2nd**"
        mention = member.mention if member else f"@{p['ign']}"
        lines_tagged.append(f"{label} {mention} *(IGN: {p['ign']})*")

    for p in untagged:
        lines_untagged.append(f"· {p['ign']}")

    embed = discord.Embed(
        title=f"{icon} League Call — {flower_name}",
        color=DWG_GOLD,
    )
    embed.add_field(name="Rarity",  value=flower_data["rarity"],   inline=True)
    embed.add_field(name="Points",  value=f"{display_pts}{upgrade_note}", inline=True)
    embed.add_field(name="Source",  value=flower_data["source"],   inline=True)

    if lines_tagged:
        embed.add_field(
            name="📣 Tagged Players",
            value="\n".join(lines_tagged),
            inline=False,
        )
    if lines_untagged:
        embed.add_field(
            name="Also Has This Flower",
            value="\n".join(lines_untagged),
            inline=False,
        )

    embed.set_footer(text=f"{FOOTER} • Week of {current_week_start()}")
    return embed, None


def register_league(tree: app_commands.CommandTree) -> None:

    league = app_commands.Group(
        name="league",
        description="League event commands — callouts, locking, standings",
    )

    # ------------------------------------------------------------------
    # AUTOCOMPLETE
    # ------------------------------------------------------------------

    async def flower_autocomplete(
        interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        names = get_flower_names_for_autocomplete()
        return [
            app_commands.Choice(name=n, value=n)
            for n in names if current.lower() in n.lower()
        ][:25]

    # ------------------------------------------------------------------
    # /league call — public callout, tags max + second best
    # ------------------------------------------------------------------

    @league.command(
        name="call",
        description="Call a flower for league — tags max and second best owners (leader only)",
    )
    @app_commands.describe(
        flower="The flower to call",
        upgraded="Use upgraded (×2) point value?",
    )
    @app_commands.autocomplete(flower=flower_autocomplete)
    async def league_call(
        interaction: discord.Interaction,
        flower: str,
        upgraded: bool = False,
    ):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_leader(interaction):
            return

        matched = find_flower_match(flower)
        if not matched:
            await interaction.response.send_message(
                f"❌ **{flower}** not found in the master list.", ephemeral=True
            )
            return

        embed, error = build_callout(
            str(interaction.guild_id), interaction.guild, matched, upgraded
        )
        if error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        # Public post — this is the actual callout players see
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /league preview — private preview before calling
    # ------------------------------------------------------------------

    @league.command(
        name="preview",
        description="Preview who would be tagged for a flower before calling (leader only)",
    )
    @app_commands.describe(
        flower="The flower to preview",
        upgraded="Use upgraded (×2) point value?",
    )
    @app_commands.autocomplete(flower=flower_autocomplete)
    async def league_preview(
        interaction: discord.Interaction,
        flower: str,
        upgraded: bool = False,
    ):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_leader(interaction):
            return

        matched = find_flower_match(flower)
        if not matched:
            await interaction.response.send_message(
                f"❌ **{flower}** not found in the master list.", ephemeral=True
            )
            return

        embed, error = build_callout(
            str(interaction.guild_id), interaction.guild, matched, upgraded
        )
        if error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return

        embed.title = f"👁️ Preview — {embed.title}"
        embed.color = DWG_BLUE
        embed.description = "*This is a private preview. Use `/league call` to post publicly.*"
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /league lock — player marks themselves done for the week
    # ------------------------------------------------------------------

    @league.command(
        name="lock",
        description="Mark yourself as done with league for this week",
    )
    async def league_lock(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_registered(interaction):
            return

        guild_id   = str(interaction.guild_id)
        discord_id = str(interaction.user.id)
        week       = current_week_start()

        state = get_league_state(guild_id, discord_id, week)
        if state and state.get("is_locked"):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🔒 Already Locked",
                    description=f"You already marked yourself done for the week of **{week}**.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        set_league_lock(guild_id, discord_id, week, locked=True)

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🔒 Locked In",
                description=f"You're marked as **done** for league this week ({week}). Good work!",
                color=DWG_MINT,
            ).set_footer(text=FOOTER),
            ephemeral=False,
        )

    # ------------------------------------------------------------------
    # /league unlock — leader unlocks a player (admin correction)
    # ------------------------------------------------------------------

    @league.command(
        name="unlock",
        description="Unlock a player's league lock for this week (leader only)",
    )
    @app_commands.describe(member="The player to unlock")
    async def league_unlock(
        interaction: discord.Interaction, member: discord.Member
    ):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_leader(interaction):
            return

        guild_id   = str(interaction.guild_id)
        discord_id = str(member.id)
        week       = current_week_start()

        set_league_lock(guild_id, discord_id, week, locked=False)

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🔓 Unlocked",
                description=f"{member.mention} has been unlocked for league week **{week}**.",
                color=DWG_PURPLE,
            ).set_footer(text=FOOTER),
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # /league remaining — who still needs to participate
    # ------------------------------------------------------------------

    @league.command(
        name="remaining",
        description="See who hasn't locked in for league this week (leader only)",
    )
    async def league_remaining(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_leader(interaction):
            return

        guild_id = str(interaction.guild_id)
        week     = current_week_start()
        all_players  = get_all_players(guild_id)
        locked_states = get_guild_league_state(guild_id, week)
        locked_ids    = {s["discord_id"] for s in locked_states if s.get("is_locked")}

        done      = [p for p in all_players if p["discord_id"] in locked_ids]
        remaining = [p for p in all_players if p["discord_id"] not in locked_ids]

        embed = discord.Embed(
            title=f"📋 League Remaining — Week of {week}",
            color=DWG_PURPLE,
        )
        embed.add_field(
            name=f"✅ Done ({len(done)})",
            value="\n".join(p["ign"] for p in done) or "Nobody yet",
            inline=True,
        )
        embed.add_field(
            name=f"⏳ Still Needed ({len(remaining)})",
            value="\n".join(p["ign"] for p in remaining) or "Everyone's done!",
            inline=True,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /league standings — guild league leaderboard
    # ------------------------------------------------------------------

    @league.command(
        name="standings",
        description="View current league standings for the guild",
    )
    @app_commands.describe(season="Season name or number (optional — shows latest if blank)")
    async def league_standings(
        interaction: discord.Interaction, season: str = None
    ):
        if await reject_if_not_setup(interaction):
            return

        guild_id  = str(interaction.guild_id)
        standings = get_guild_league_standings(guild_id, season)

        if not standings:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🏆 No League Data Yet",
                    description="No league standings have been logged yet. Use `/add league` to get started.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        medals = ["🥇", "🥈", "🥉"]
        lines  = []
        for i, row in enumerate(standings):
            prefix = medals[i] if i < 3 else f"`{i+1}.`"
            season_tag = f" *(S{row['season']})*" if row.get("season") else ""
            lines.append(
                f"{prefix} **{row['ign']}** — Rank #{row['rank']} · {row['points']:,} pts{season_tag}"
            )

        title = f"🏆 League Standings"
        if season:
            title += f" — {season}"

        embed = discord.Embed(
            title=title,
            description="\n".join(lines),
            color=DWG_GOLD,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=False)

    tree.add_command(league)
