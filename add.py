"""
commands/track.py
Dreamweaving Garden Bot — /track command group
Players add or remove flowers/vases from their own collection.
Uses player_collection table with item_type 'flower' or 'vase'.
"""

import discord
from discord import app_commands
from db.queries import (
    get_flower_names_for_autocomplete,
    get_vase_names_for_autocomplete,
    get_collection_item_names,
    add_to_collection,
    remove_from_collection,
    get_player_collection,
    find_player,
    RARITY_ORDER,
)
from utils.guards import reject_if_not_setup, reject_if_not_registered

DWG_PINK   = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0x9ECFA8)
DWG_PURPLE = discord.Color(0xD0AEE8)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"

RARITY_ICON = {
    "Shine": "✦",
    "Star":  "★",
    "Rare":  "◆",
    "Fine":  "◇",
    "Basic": "·",
}


# ── Autocomplete helpers ───────────────────────────────────────────

async def flower_master_ac(interaction: discord.Interaction,
                            current: str) -> list[app_commands.Choice[str]]:
    names = get_flower_names_for_autocomplete(current)
    return [app_commands.Choice(name=n, value=n) for n in names]


async def vase_master_ac(interaction: discord.Interaction,
                          current: str) -> list[app_commands.Choice[str]]:
    names = get_vase_names_for_autocomplete(current)
    return [app_commands.Choice(name=n, value=n) for n in names]


async def player_flower_ac(interaction: discord.Interaction,
                            current: str) -> list[app_commands.Choice[str]]:
    names = get_collection_item_names(
        str(interaction.guild_id), str(interaction.user.id), "flower"
    )
    return [app_commands.Choice(name=n, value=n)
            for n in names if current.lower() in n.lower()][:25]


async def player_vase_ac(interaction: discord.Interaction,
                          current: str) -> list[app_commands.Choice[str]]:
    names = get_collection_item_names(
        str(interaction.guild_id), str(interaction.user.id), "vase"
    )
    return [app_commands.Choice(name=n, value=n)
            for n in names if current.lower() in n.lower()][:25]


# ── Command registration ───────────────────────────────────────────

def register_track(tree: app_commands.CommandTree) -> None:
    track = app_commands.Group(name="track", description="Manage your flower and vase collection")

    # /track flower add
    flower_group = app_commands.Group(name="flower", description="Track your flowers",
                                       parent=track)

    @flower_group.command(name="add", description="Add a flower to your collection")
    @app_commands.describe(flower="Flower name")
    @app_commands.autocomplete(flower=flower_master_ac)
    async def flower_add(interaction: discord.Interaction, flower: str):
        if await reject_if_not_setup(interaction):    return
        if await reject_if_not_registered(interaction): return
        ok, msg = add_to_collection(
            str(interaction.guild_id), str(interaction.user.id), "flower", flower
        )
        color = DWG_MINT if ok else DWG_PINK
        await interaction.response.send_message(
            embed=discord.Embed(description=msg, color=color), ephemeral=True)

    @flower_group.command(name="remove", description="Remove a flower from your collection")
    @app_commands.describe(flower="Flower name")
    @app_commands.autocomplete(flower=player_flower_ac)
    async def flower_remove(interaction: discord.Interaction, flower: str):
        if await reject_if_not_setup(interaction):    return
        if await reject_if_not_registered(interaction): return
        removed = remove_from_collection(
            str(interaction.guild_id), str(interaction.user.id), "flower", flower
        )
        if removed:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"🌿 **{flower}** removed from your collection.",
                    color=DWG_MINT,
                ), ephemeral=True)
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"You don't have **{flower}** in your collection.",
                    color=DWG_PINK,
                ), ephemeral=True)

    @flower_group.command(name="list", description="View your flower collection")
    async def flower_list(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):    return
        if await reject_if_not_registered(interaction): return
        items = get_player_collection(
            str(interaction.guild_id), str(interaction.user.id), "flower"
        )
        if not items:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="You haven't tracked any flowers yet. Use `/track flower add` to start!",
                    color=DWG_PINK,
                ), ephemeral=True)
            return

        # Group by rarity
        grouped: dict[str, list[str]] = {}
        for item in items:
            r = item.get("rarity") or "Unknown"
            grouped.setdefault(r, []).append(item["item_name"])

        embed = discord.Embed(
            title=f"🌸 {interaction.user.display_name}'s Flowers",
            description=f"**{len(items)}** flower(s) tracked",
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

    # /track vase add / remove / list
    vase_group = app_commands.Group(name="vase", description="Track your vases", parent=track)

    @vase_group.command(name="add", description="Add a vase to your collection")
    @app_commands.describe(vase="Vase name")
    @app_commands.autocomplete(vase=vase_master_ac)
    async def vase_add(interaction: discord.Interaction, vase: str):
        if await reject_if_not_setup(interaction):    return
        if await reject_if_not_registered(interaction): return
        ok, msg = add_to_collection(
            str(interaction.guild_id), str(interaction.user.id), "vase", vase
        )
        color = DWG_MINT if ok else DWG_PINK
        await interaction.response.send_message(
            embed=discord.Embed(description=msg, color=color), ephemeral=True)

    @vase_group.command(name="remove", description="Remove a vase from your collection")
    @app_commands.describe(vase="Vase name")
    @app_commands.autocomplete(vase=player_vase_ac)
    async def vase_remove(interaction: discord.Interaction, vase: str):
        if await reject_if_not_setup(interaction):    return
        if await reject_if_not_registered(interaction): return
        removed = remove_from_collection(
            str(interaction.guild_id), str(interaction.user.id), "vase", vase
        )
        if removed:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"🏺 **{vase}** removed from your collection.",
                    color=DWG_MINT,
                ), ephemeral=True)
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"You don't have **{vase}** in your collection.",
                    color=DWG_PINK,
                ), ephemeral=True)

    @vase_group.command(name="list", description="View your vase collection")
    async def vase_list(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):    return
        if await reject_if_not_registered(interaction): return
        items = get_player_collection(
            str(interaction.guild_id), str(interaction.user.id), "vase"
        )
        if not items:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="You haven't tracked any vases yet. Use `/track vase add` to start!",
                    color=DWG_PINK,
                ), ephemeral=True)
            return

        grouped: dict[str, list[str]] = {}
        for item in items:
            r = item.get("rarity") or "Unknown"
            grouped.setdefault(r, []).append(item["item_name"])

        embed = discord.Embed(
            title=f"🏺 {interaction.user.display_name}'s Vases",
            description=f"**{len(items)}** vase(s) tracked",
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
