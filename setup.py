"""
commands/lookup.py
Dreamweaving Garden Bot — /lookup command group
Social lookups: who has a flower/vase, missing items, player profile, contributions.
"""

import discord
from discord import app_commands
from db.queries import (
    who_has_item, get_missing_from_master,
    find_player, find_player_by_ign,
    get_player_collection, get_latest_league_entry,
    get_player_contributions, get_guild_contribution_totals,
    get_all_members,
    get_flower_names_for_autocomplete,
    get_vase_names_for_autocomplete,
    RARITY_ORDER,
)
from utils.guards import reject_if_not_setup, reject_if_not_registered

DWG_PINK   = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0x9ECFA8)
DWG_PURPLE = discord.Color(0xD0AEE8)
DWG_GOLD   = discord.Color(0xE8C878)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"

RARITY_ICON = {
    "Shine": "✦", "Star": "★", "Rare": "◆", "Fine": "◇", "Basic": "·",
}


async def flower_ac(interaction, current):
    return [app_commands.Choice(name=n, value=n)
            for n in get_flower_names_for_autocomplete(current)]

async def vase_ac(interaction, current):
    return [app_commands.Choice(name=n, value=n)
            for n in get_vase_names_for_autocomplete(current)]


def register_lookup(tree: app_commands.CommandTree) -> None:
    lookup = app_commands.Group(name="lookup", description="Look up players, flowers, and vases")

    # /lookup flower — who has this flower
    @lookup.command(name="flower", description="See which members have a specific flower")
    @app_commands.describe(flower="Flower name")
    @app_commands.autocomplete(flower=flower_ac)
    async def lookup_flower(interaction: discord.Interaction, flower: str):
        if await reject_if_not_setup(interaction): return
        owners = who_has_item(str(interaction.guild_id), "flower", flower)
        if not owners:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title=f"🌸 {flower}",
                    description="No members have this flower tracked yet.",
                    color=DWG_PINK,
                ), ephemeral=True)
            return
        names = "\n".join(f"· {o['ign']}" for o in owners)
        embed = discord.Embed(
            title=f"🌸 {flower}",
            description=f"**{len(owners)}** member(s) have this flower:\n\n{names}",
            color=DWG_PURPLE,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /lookup vase — who has this vase
    @lookup.command(name="vase", description="See which members have a specific vase")
    @app_commands.describe(vase="Vase name")
    @app_commands.autocomplete(vase=vase_ac)
    async def lookup_vase(interaction: discord.Interaction, vase: str):
        if await reject_if_not_setup(interaction): return
        owners = who_has_item(str(interaction.guild_id), "vase", vase)
        if not owners:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title=f"🏺 {vase}",
                    description="No members have this vase tracked yet.",
                    color=DWG_PINK,
                ), ephemeral=True)
            return
        names = "\n".join(f"· {o['ign']}" for o in owners)
        embed = discord.Embed(
            title=f"🏺 {vase}",
            description=f"**{len(owners)}** member(s) have this vase:\n\n{names}",
            color=DWG_PURPLE,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /lookup mymissing flowers
    @lookup.command(name="mymissing", description="See flowers or vases you don't have yet")
    @app_commands.describe(type="flowers or vases")
    @app_commands.choices(type=[
        app_commands.Choice(name="Flowers", value="flower"),
        app_commands.Choice(name="Vases",   value="vase"),
    ])
    async def lookup_mymissing(interaction: discord.Interaction, type: str):
        if await reject_if_not_setup(interaction):    return
        if await reject_if_not_registered(interaction): return
        missing = get_missing_from_master(
            str(interaction.guild_id), str(interaction.user.id), type)
        label = "flower" if type == "flower" else "vase"
        icon  = "🌸" if type == "flower" else "🏺"
        if not missing:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"You have every {label} in the master list! 🎉",
                    color=DWG_MINT,
                ), ephemeral=True)
            return
        grouped: dict[str, list[str]] = {}
        for item in missing:
            grouped.setdefault(item["rarity"], []).append(item["name"])
        embed = discord.Embed(
            title=f"{icon} Your Missing {label.capitalize()}s",
            description=f"**{len(missing)}** {label}(s) you don't have yet:",
            color=DWG_PURPLE,
        )
        for rarity in sorted(grouped, key=lambda r: RARITY_ORDER.get(r, 99)):
            embed.add_field(
                name=f"{RARITY_ICON.get(rarity,'·')} {rarity}",
                value="\n".join(grouped[rarity]),
                inline=True,
            )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /lookup guildmissing — items nobody has
    @lookup.command(name="guildmissing",
                    description="See flowers or vases nobody in the guild has yet")
    @app_commands.describe(type="flowers or vases")
    @app_commands.choices(type=[
        app_commands.Choice(name="Flowers", value="flower"),
        app_commands.Choice(name="Vases",   value="vase"),
    ])
    async def lookup_guildmissing(interaction: discord.Interaction, type: str):
        if await reject_if_not_setup(interaction): return
        guild_id = str(interaction.guild_id)
        members  = get_all_members(guild_id)
        label    = "flower" if type == "flower" else "vase"
        icon     = "🌸" if type == "flower" else "🏺"

        # Collect all items anyone has
        owned: set[str] = set()
        for m in members:
            for item in get_player_collection(guild_id, m["discord_id"], type):
                owned.add(item["item_name"].lower())

        from db.queries import get_all_flowers, get_all_vases
        master = get_all_flowers() if type == "flower" else get_all_vases()
        missing = [f for f in master if f["name"].lower() not in owned]

        if not missing:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"Every {label} in the master list is owned by at least one member! 🎉",
                    color=DWG_MINT,
                ), ephemeral=True)
            return

        grouped: dict[str, list[str]] = {}
        for item in missing:
            grouped.setdefault(item["rarity"], []).append(item["name"])

        embed = discord.Embed(
            title=f"{icon} Guild Missing {label.capitalize()}s",
            description=f"**{len(missing)}** {label}(s) nobody has yet:",
            color=DWG_PURPLE,
        )
        for rarity in sorted(grouped, key=lambda r: RARITY_ORDER.get(r, 99)):
            embed.add_field(
                name=f"{RARITY_ICON.get(rarity,'·')} {rarity}",
                value="\n".join(grouped[rarity]),
                inline=True,
            )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /lookup whois — full player profile
    @lookup.command(name="whois", description="View a player's full profile")
    @app_commands.describe(member="Discord mention (optional)", ign="In-game name (optional)")
    async def lookup_whois(interaction: discord.Interaction,
                           member: discord.Member | None = None,
                           ign: str | None = None):
        if await reject_if_not_setup(interaction): return
        guild_id = str(interaction.guild_id)

        if member:
            player = find_player(guild_id, str(member.id))
            display_member = member
        elif ign:
            player = find_player_by_ign(guild_id, ign)
            display_member = None
            if player:
                display_member = interaction.guild.get_member(int(player["discord_id"]))
        else:
            player = find_player(guild_id, str(interaction.user.id))
            display_member = interaction.user

        if not player:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="Player not found. They may not be registered.",
                    color=DWG_PINK,
                ), ephemeral=True)
            return

        discord_id   = player["discord_id"]
        flowers      = get_player_collection(guild_id, discord_id, "flower")
        vases        = get_player_collection(guild_id, discord_id, "vase")
        league       = get_latest_league_entry(guild_id, discord_id)
        contributions = get_player_contributions(guild_id, discord_id)
        total_contrib = sum(c["amount"] for c in contributions)

        embed = discord.Embed(title=f"🌸 {player['ign']}", color=DWG_PURPLE)
        if display_member:
            embed.set_thumbnail(url=display_member.display_avatar.url)

        embed.add_field(name="Discord",    value=f"<@{discord_id}>",          inline=True)
        embed.add_field(name="IGN",        value=player["ign"],                inline=True)
        embed.add_field(name="Registered", value=player["registered_at"][:10], inline=True)
        embed.add_field(name="🌸 Flowers", value=str(len(flowers)),            inline=True)
        embed.add_field(name="🏺 Vases",   value=str(len(vases)),              inline=True)
        embed.add_field(name="🤝 Contributions", value=f"{total_contrib:,}",   inline=True)

        if league:
            val = f"**{league['points']:,} pts**"
            if league.get("rank"):
                val += f" · Rank #{league['rank']}"
            if league.get("season"):
                val += f"\n{league['season']}"
            embed.add_field(name="🏆 Latest League", value=val, inline=False)

        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /lookup contributions — guild leaderboard
    @lookup.command(name="contributions", description="View the guild contribution leaderboard")
    async def lookup_contributions(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        totals = get_guild_contribution_totals(str(interaction.guild_id))
        if not totals:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="No contributions logged yet. Use `/add contribution` to start!",
                    color=DWG_PINK,
                ), ephemeral=True)
            return
        medals = ["🥇", "🥈", "🥉"]
        lines  = []
        for i, row in enumerate(totals):
            prefix = medals[i] if i < 3 else f"`{i+1}.`"
            lines.append(f"{prefix} **{row['ign']}** — {row['total']:,}")
        embed = discord.Embed(
            title="🤝 Guild Contributions",
            description="\n".join(lines),
            color=DWG_GOLD,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    tree.add_command(lookup)
