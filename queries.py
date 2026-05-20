"""
commands/league.py
Dreamweaving Garden Bot — /league command group
Standings, weekly lock/unlock, leader callout, reset.
"""

import discord
from discord import app_commands
from db.queries import (
    get_guild_league_standings, log_league_entry,
    lock_player, unlock_player, is_locked,
    get_locked_players, reset_all_locks,
    get_all_members, find_player,
)
from utils.guards import reject_if_not_setup, reject_if_not_registered, reject_if_not_leader

DWG_PINK   = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0x9ECFA8)
DWG_PURPLE = discord.Color(0xD0AEE8)
DWG_GOLD   = discord.Color(0xE8C878)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"


def _standings_embed(guild_id: str, title: str, season: str = "") -> discord.Embed:
    standings = get_guild_league_standings(guild_id, season)
    if not standings:
        return discord.Embed(
            title=title,
            description="No league entries yet. Use `/add league` to log standings.",
            color=DWG_PINK,
        )
    medals = ["🥇", "🥈", "🥉"]
    lines  = []
    for i, row in enumerate(standings):
        prefix = medals[i] if i < 3 else f"`{i+1}.`"
        lock   = " 🔒" if is_locked(guild_id, row["discord_id"]) else ""
        lines.append(f"{prefix} **{row['ign']}** — {row['points']:,} pts{lock}")
    embed = discord.Embed(title=title, description="\n".join(lines), color=DWG_GOLD)
    embed.set_footer(text=FOOTER)
    return embed


def register_league(tree: app_commands.CommandTree) -> None:
    league = app_commands.Group(name="league", description="League standings and weekly tools")

    # /league standings
    @league.command(name="standings", description="View the guild league leaderboard")
    @app_commands.describe(season="Filter by season (optional)")
    async def league_standings(interaction: discord.Interaction, season: str = ""):
        if await reject_if_not_setup(interaction): return
        embed = _standings_embed(str(interaction.guild_id), "🏆 League Standings", season)
        await interaction.response.send_message(embed=embed)

    # /league lock — player marks themselves done
    @league.command(name="lock", description="Mark yourself as done for this week")
    async def league_lock(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):    return
        if await reject_if_not_registered(interaction): return
        guild_id   = str(interaction.guild_id)
        discord_id = str(interaction.user.id)
        if is_locked(guild_id, discord_id):
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="You're already locked in for this week. 🔒",
                    color=DWG_PINK,
                ), ephemeral=True)
            return
        lock_player(guild_id, discord_id)
        await interaction.response.send_message(
            embed=discord.Embed(
                description="🔒 You're locked in for this week! Good work.",
                color=DWG_MINT,
            ), ephemeral=True)

    # /league unlock — leader unlocks a player
    @league.command(name="unlock", description="Unlock a player for this week (leader only)")
    @app_commands.describe(member="The member to unlock")
    async def league_unlock(interaction: discord.Interaction, member: discord.Member):
        if await reject_if_not_setup(interaction):  return
        if await reject_if_not_leader(interaction): return
        guild_id = str(interaction.guild_id)
        unlocked = unlock_player(guild_id, str(member.id))
        if unlocked:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"🔓 {member.mention} has been unlocked.",
                    color=DWG_MINT,
                ), ephemeral=True)
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{member.mention} wasn't locked.",
                    color=DWG_PINK,
                ), ephemeral=True)

    # /league remaining — who still needs to participate
    @league.command(name="remaining", description="See who hasn't locked in yet (leader only)")
    async def league_remaining(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):  return
        if await reject_if_not_leader(interaction): return
        guild_id = str(interaction.guild_id)
        members  = get_all_members(guild_id)
        locked   = set(get_locked_players(guild_id))
        remaining = [m for m in members if m["discord_id"] not in locked]

        if not remaining:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="Everyone has locked in! 🎉",
                    color=DWG_MINT,
                ), ephemeral=True)
            return

        lines = "\n".join(f"· {m['ign']}" for m in remaining)
        embed = discord.Embed(
            title="⏳ Waiting On…",
            description=f"**{len(remaining)}** member(s) haven't locked in yet:\n\n{lines}",
            color=DWG_PURPLE,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /league preview — private standings preview (leader only)
    @league.command(name="preview", description="Preview the standings privately (leader only)")
    async def league_preview(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):  return
        if await reject_if_not_leader(interaction): return
        embed = _standings_embed(str(interaction.guild_id), "🏆 League Preview (Private)")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /league call — post public standings callout
    @league.command(name="call", description="Post the league standings publicly (leader only)")
    async def league_call(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):  return
        if await reject_if_not_leader(interaction): return
        embed = _standings_embed(str(interaction.guild_id), "🏆 League Standings")
        await interaction.response.send_message(embed=embed)

    # /league resetweek — clear all locks
    @league.command(name="resetweek", description="Clear all weekly locks (leader only)")
    async def league_resetweek(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):  return
        if await reject_if_not_leader(interaction): return
        count = reset_all_locks(str(interaction.guild_id))
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"🔄 Weekly reset complete — {count} lock(s) cleared.",
                color=DWG_MINT,
            ), ephemeral=True)

    tree.add_command(league)
