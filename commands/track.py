"""
commands/track.py
Dreamweaving Garden Bot — /track command
Players add or remove flowers from their own profile.
"""

import discord
from discord import app_commands
from db.queries import (
    get_player_flowers, add_player_flower, remove_player_flower,
    find_flower_match, get_flower, get_flower_names_for_autocomplete,
)
from utils.guards import reject_if_not_setup, reject_if_not_registered

DWG_PURPLE = discord.Color(0xC9A0FF)
DWG_MINT   = discord.Color(0xB8F2D0)
DWG_PINK   = discord.Color(0xFFB3C1)
DWG_GOLD   = discord.Color(0xF4D58D)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"

RARITY_ICON = {
    "Shine": "✦",
    "Star":  "★",
    "Rare":  "◆",
    "Fine":  "◇",
    "Basic": "·",
}


def register_track(tree: app_commands.CommandTree) -> None:

    track = app_commands.Group(
        name="track",
        description="Add or remove flowers from your garden profile",
    )

    # ------------------------------------------------------------------
    # AUTOCOMPLETE
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # /track add
    # ------------------------------------------------------------------

    @track.command(name="add", description="Add a flower to your garden profile")
    @app_commands.describe(flower="Start typing to search the flower list")
    @app_commands.autocomplete(flower=flower_autocomplete)
    async def track_add(interaction: discord.Interaction, flower: str):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_registered(interaction):
            return

        guild_id   = str(interaction.guild_id)
        discord_id = str(interaction.user.id)

        # Fuzzy match in case autocomplete wasn't used
        matched = find_flower_match(flower)
        if not matched:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🌸 Flower Not Found",
                    description=(
                        f"**{flower}** isn't in the master flower list.\n\n"
                        "Make sure you're selecting from the autocomplete list, "
                        "or ask a leader to add it to the master list first."
                    ),
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        flower_data = get_flower(matched)
        icon = RARITY_ICON.get(flower_data["rarity"], "·") if flower_data else "🌸"

        added = add_player_flower(guild_id, discord_id, matched, source_type="manual")

        if not added:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Already Tracked",
                    description=f"**{matched}** is already in your garden profile.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"{icon} Flower Added",
            description=f"**{matched}** has been added to your garden profile.",
            color=DWG_MINT,
        )
        if flower_data:
            embed.add_field(name="Rarity",      value=flower_data["rarity"],      inline=True)
            embed.add_field(name="Base Points", value=str(flower_data["base_points"]), inline=True)
            embed.add_field(
                name="Upgraded Points",
                value=f"{flower_data['base_points'] * 2} 💎 {flower_data['upgrade_cost']:,}",
                inline=True,
            )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /track remove
    # ------------------------------------------------------------------

    @track.command(name="remove", description="Remove a flower from your garden profile")
    @app_commands.describe(flower="Start typing to search your tracked flowers")
    async def track_remove(interaction: discord.Interaction, flower: str):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_registered(interaction):
            return

        guild_id   = str(interaction.guild_id)
        discord_id = str(interaction.user.id)

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

        removed = remove_player_flower(guild_id, discord_id, matched)
        if not removed:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Not In Your Profile",
                    description=f"**{matched}** wasn't in your garden profile.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🌿 Flower Removed",
                description=f"**{matched}** has been removed from your garden profile.",
                color=DWG_PURPLE,
            ),
            ephemeral=True,
        )

    @track_remove.autocomplete("flower")
    async def remove_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        flowers = get_player_flowers(
            str(interaction.guild_id), str(interaction.user.id)
        )
        return [
            app_commands.Choice(name=f, value=f)
            for f in flowers
            if current.lower() in f.lower()
        ][:25]

    # ------------------------------------------------------------------
    # /track list
    # ------------------------------------------------------------------

    @track.command(name="list", description="View all flowers in your garden profile")
    async def track_list(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_registered(interaction):
            return

        guild_id   = str(interaction.guild_id)
        discord_id = str(interaction.user.id)
        flowers    = get_player_flowers(guild_id, discord_id)

        if not flowers:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🌱 Your Garden is Empty",
                    description=(
                        "You haven't tracked any flowers yet.\n"
                        "Use `/track add` to start building your profile."
                    ),
                    color=DWG_PURPLE,
                ),
                ephemeral=True,
            )
            return

        # Group by rarity
        from db.queries import get_flower, RARITY_ORDER
        grouped: dict[str, list[str]] = {}
        for name in flowers:
            fd = get_flower(name)
            rarity = fd["rarity"] if fd else "Unknown"
            grouped.setdefault(rarity, []).append(name)

        embed = discord.Embed(
            title=f"🌸 {interaction.user.display_name}'s Garden",
            description=f"**{len(flowers)}** flower(s) tracked",
            color=DWG_PURPLE,
        )

        for rarity in sorted(grouped, key=lambda r: RARITY_ORDER.get(r, 99)):
            icon  = RARITY_ICON.get(rarity, "·")
            names = grouped[rarity]
            embed.add_field(
                name=f"{icon} {rarity} ({len(names)})",
                value="\n".join(names),
                inline=True,
            )

        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    tree.add_command(track)
