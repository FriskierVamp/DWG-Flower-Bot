"""
commands/lookup.py
Dreamweaving Garden Bot — /lookup command group
Social flower lookup, missing flowers, whois, guild stats.
"""

import discord
from discord import app_commands
from db.queries import (
    get_players_with_flower, find_flower_match, get_flower,
    get_guild_missing_flowers, get_player_flowers,
    get_flower_names_for_autocomplete, find_player, find_player_by_ign,
    get_all_players, RARITY_ORDER,
)
from utils.guards import reject_if_not_setup, reject_if_not_registered

DWG_PURPLE = discord.Color(0xC9A0FF)
DWG_MINT   = discord.Color(0xB8F2D0)
DWG_PINK   = discord.Color(0xFFB3C1)
DWG_GOLD   = discord.Color(0xF4D58D)
DWG_BLUE   = discord.Color(0xBFD7FF)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"

RARITY_ICON = {
    "Shine": "✦",
    "Star":  "★",
    "Rare":  "◆",
    "Fine":  "◇",
    "Basic": "·",
}


def chunk_list(items: list, size: int = 20) -> list[list]:
    return [items[i:i+size] for i in range(0, len(items), size)]


def register_lookup(tree: app_commands.CommandTree) -> None:

    lookup = app_commands.Group(
        name="lookup",
        description="Look up flower owners, missing flowers, and player profiles",
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
    # /lookup flower — who has this flower (social, no tags)
    # ------------------------------------------------------------------

    @lookup.command(
        name="flower",
        description="See who in the guild has a specific flower",
    )
    @app_commands.describe(flower="The flower to look up")
    @app_commands.autocomplete(flower=flower_autocomplete)
    async def lookup_flower(interaction: discord.Interaction, flower: str):
        if await reject_if_not_setup(interaction):
            return

        matched = find_flower_match(flower)
        if not matched:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🌸 Flower Not Found",
                    description=f"**{flower}** isn't in the master list.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        flower_data = get_flower(matched)
        owners      = get_players_with_flower(str(interaction.guild_id), matched)
        icon        = RARITY_ICON.get(flower_data["rarity"], "·") if flower_data else "🌸"

        embed = discord.Embed(
            title=f"{icon} {matched}",
            color=DWG_BLUE,
        )

        if flower_data:
            embed.add_field(name="Rarity",          value=flower_data["rarity"],               inline=True)
            embed.add_field(name="Base Points",     value=str(flower_data["base_points"]),      inline=True)
            embed.add_field(name="Upgraded Points", value=str(flower_data["base_points"] * 2), inline=True)
            embed.add_field(
                name="Upgrade Cost",
                value=f"💎 {flower_data['upgrade_cost']:,} diamonds",
                inline=True,
            )
            embed.add_field(name="Source", value=flower_data["source"], inline=True)

        if not owners:
            embed.description = "Nobody in this guild has this flower yet."
        else:
            # Plain list — no tags, purely social for buy/pick coordination
            names = [p["ign"] for p in owners]
            embed.add_field(
                name=f"🌿 Guild Members Who Have It ({len(owners)})",
                value="\n".join(names),
                inline=False,
            )
            embed.description = (
                "These members have this flower in their garden. "
                "Feel free to reach out to buy or pick!"
            )

        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /lookup mymissing — flowers the calling player doesn't have
    # ------------------------------------------------------------------

    @lookup.command(
        name="mymissing",
        description="See which flowers you haven't tracked yet",
    )
    async def lookup_mymissing(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_registered(interaction):
            return

        guild_id   = str(interaction.guild_id)
        discord_id = str(interaction.user.id)

        from db.queries import get_all_flowers
        all_flowers    = get_all_flowers()
        player_flowers = set(get_player_flowers(guild_id, discord_id))
        missing        = [f for f in all_flowers if f["name"] not in player_flowers]

        if not missing:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🌟 Garden Complete!",
                    description="You have every flower in the master list. Impressive!",
                    color=DWG_GOLD,
                ),
                ephemeral=True,
            )
            return

        # Group by rarity
        grouped: dict[str, list[str]] = {}
        for f in missing:
            grouped.setdefault(f["rarity"], []).append(f["name"])

        embed = discord.Embed(
            title=f"🌱 {interaction.user.display_name}'s Missing Flowers",
            description=f"**{len(missing)}** flower(s) not yet in your profile",
            color=DWG_PURPLE,
        )
        for rarity in sorted(grouped, key=lambda r: RARITY_ORDER.get(r, 99)):
            icon = RARITY_ICON.get(rarity, "·")
            embed.add_field(
                name=f"{icon} {rarity} ({len(grouped[rarity])})",
                value="\n".join(grouped[rarity]),
                inline=True,
            )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /lookup guildmissing — flowers nobody in the guild has
    # ------------------------------------------------------------------

    @lookup.command(
        name="guildmissing",
        description="See which flowers nobody in the guild has",
    )
    async def lookup_guildmissing(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):
            return

        guild_id = str(interaction.guild_id)
        missing  = get_guild_missing_flowers(guild_id)

        if not missing:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🌟 Guild Collection Complete!",
                    description="Every flower in the master list is held by at least one member.",
                    color=DWG_GOLD,
                ),
                ephemeral=True,
            )
            return

        from db.queries import get_flower
        grouped: dict[str, list[str]] = {}
        for name in missing:
            fd     = get_flower(name)
            rarity = fd["rarity"] if fd else "Unknown"
            grouped.setdefault(rarity, []).append(name)

        embed = discord.Embed(
            title="🍂 Guild Missing Flowers",
            description=f"**{len(missing)}** flower(s) not held by anyone in the guild",
            color=DWG_PINK,
        )
        for rarity in sorted(grouped, key=lambda r: RARITY_ORDER.get(r, 99)):
            icon = RARITY_ICON.get(rarity, "·")
            embed.add_field(
                name=f"{icon} {rarity} ({len(grouped[rarity])})",
                value="\n".join(grouped[rarity]),
                inline=True,
            )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /lookup whois — look up a player by Discord mention or IGN
    # ------------------------------------------------------------------

    @lookup.command(
        name="whois",
        description="Look up a player's full profile by Discord user or in-game name",
    )
    @app_commands.describe(
        member="Discord member (optional)",
        ign="In-game name (optional — use one or the other)",
    )
    async def lookup_whois(
        interaction: discord.Interaction,
        member: discord.Member = None,
        ign: str = None,
    ):
        if await reject_if_not_setup(interaction):
            return

        guild_id = str(interaction.guild_id)

        if not member and not ign:
            await interaction.response.send_message(
                "Please provide either a Discord member or an in-game name.",
                ephemeral=True,
            )
            return

        # Find player record
        player = None
        if member:
            player = find_player(guild_id, str(member.id))
        elif ign:
            player = find_player_by_ign(guild_id, ign)
            if player:
                # Resolve the Discord member object
                member = interaction.guild.get_member(int(player["discord_id"]))

        if not player:
            label = member.display_name if member else ign
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❓ Player Not Found",
                    description=(
                        f"**{label}** isn't registered in this server.\n\n"
                        "They may not have run `/register` yet."
                    ),
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        discord_id    = player["discord_id"]
        flowers       = get_player_flowers(guild_id, discord_id)
        flower_count  = len(flowers)

        from db.queries import (
            get_latest_league_entry, get_player_contributions,
            get_player_vases,
        )
        league       = get_latest_league_entry(guild_id, discord_id)
        contributions = get_player_contributions(guild_id, discord_id)
        total_contrib = sum(c["amount"] for c in contributions)
        vases         = get_player_vases(guild_id, discord_id)

        embed = discord.Embed(
            title=f"🌸 {player['ign']}",
            color=DWG_PURPLE,
        )
        if member:
            embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(name="Discord",      value=f"<@{discord_id}>",         inline=True)
        embed.add_field(name="In-Game Name", value=player["ign"],               inline=True)
        embed.add_field(name="Registered",   value=player["registered_at"][:10], inline=True)
        embed.add_field(name="🌸 Flowers",   value=str(flower_count),           inline=True)
        embed.add_field(name="🏺 Vases",     value=str(len(vases)),             inline=True)
        embed.add_field(
            name="🤝 Contributions",
            value=f"{total_contrib:,} total",
            inline=True,
        )

        if league:
            embed.add_field(
                name="🏆 League",
                value=(
                    f"Rank #{league['rank']} — {league['points']:,} pts"
                    + (f"\nSeason {league['season']}" if league.get("season") else "")
                ),
                inline=False,
            )

        if flowers:
            sample = flowers[:10]
            more   = flower_count - len(sample)
            embed.add_field(
                name="Recent Flowers",
                value=", ".join(sample) + (f" +{more} more" if more else ""),
                inline=False,
            )

        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /lookup contributions — guild contribution leaderboard
    # ------------------------------------------------------------------

    @lookup.command(
        name="contributions",
        description="View contribution totals for the guild",
    )
    async def lookup_contributions(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):
            return

        from db.queries import get_guild_contribution_totals
        totals = get_guild_contribution_totals(str(interaction.guild_id))

        if not totals:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🤝 No Contributions Yet",
                    description="No contributions have been logged yet. Use `/add contribution` to get started.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        medals = ["🥇", "🥈", "🥉"]
        lines  = []
        for i, row in enumerate(totals):
            prefix = medals[i] if i < 3 else f"`{i+1}.`"
            lines.append(f"{prefix} **{row['ign']}** — {row['total']:,}")

        embed = discord.Embed(
            title="🤝 Guild Contributions",
            description="\n".join(lines),
            color=DWG_MINT,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    tree.add_command(lookup)
