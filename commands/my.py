"""
commands/my.py
Dreamweaving Garden Bot — /my command group (everyone)
Personal collection management: flowers, vases, missing items.

Subcommands:
  /my flowers              — show your flower collection
  /my vases                — show your vase collection
  /my add flower [name]    — add a flower to your collection
  /my add vase [name]      — add a vase to your collection
  /my remove flower [name] — remove a flower from your collection
  /my remove vase [name]   — remove a vase from your collection
  /my missing flowers      — flowers from the master list you don't have
  /my missing vases        — vases from the master list you don't have
"""

import discord
from discord import app_commands
from db.queries import (
    get_player_flowers, add_player_flower, remove_player_flower,
    get_player_vases, add_player_vase, remove_player_vase,
    get_player_missing_flowers, get_player_missing_vases,
    get_flower_names_for_autocomplete, get_vase_names_for_autocomplete,
    find_flower_match, find_vase_match,
)
from utils.guards import reject_if_not_setup, reject_if_not_registered

DWG_PURPLE = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0xB8D9B0)
DWG_PINK   = discord.Color(0xF7CCD8)
DWG_BLUE   = discord.Color(0xB8D8F0)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"


# ------------------------------------------------------------------
# AUTOCOMPLETE HELPERS
# ------------------------------------------------------------------

async def flower_name_autocomplete(
    interaction: discord.Interaction, current: str,
) -> list[app_commands.Choice[str]]:
    names = get_flower_names_for_autocomplete()
    q = (current or "").lower()
    matches = [n for n in names if q in n.lower()][:25]
    return [app_commands.Choice(name=n, value=n) for n in matches]


async def vase_name_autocomplete(
    interaction: discord.Interaction, current: str,
) -> list[app_commands.Choice[str]]:
    names = get_vase_names_for_autocomplete()
    q = (current or "").lower()
    matches = [n for n in names if q in n.lower()][:25]
    return [app_commands.Choice(name=n, value=n) for n in matches]


# ------------------------------------------------------------------
# HELPER — paginated list display
# ------------------------------------------------------------------

def _items_embed(title: str, items: list[str], color: discord.Color,
                 empty_msg: str = "Nothing here yet.") -> discord.Embed:
    if not items:
        embed = discord.Embed(title=title, description=empty_msg, color=color)
    else:
        # Chunk into columns for readability
        body = "\n".join(f"• {n}" for n in items[:50])
        if len(items) > 50:
            body += f"\n\n_… and {len(items) - 50} more._"
        embed = discord.Embed(
            title=f"{title}  ({len(items)})",
            description=body,
            color=color,
        )
    embed.set_footer(text=FOOTER)
    return embed


# ------------------------------------------------------------------
# REGISTRATION
# ------------------------------------------------------------------

def register_my(tree: app_commands.CommandTree) -> None:

    my_group     = app_commands.Group(name="my", description="Manage your personal collection")
    add_group    = app_commands.Group(name="add",     description="Add to your collection",      parent=my_group)
    remove_group = app_commands.Group(name="remove",  description="Remove from your collection", parent=my_group)
    missing_grp  = app_commands.Group(name="missing", description="What you're missing",          parent=my_group)

    # ── /my flowers ────────────────────────────────────────────────
    @my_group.command(name="flowers", description="Show your flower collection")
    async def my_flowers(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        items = get_player_flowers(
            str(interaction.guild_id), str(interaction.user.id)
        )
        embed = _items_embed(
            f"🌸 {interaction.user.display_name}'s Flowers",
            items, DWG_PINK,
            empty_msg="You haven't tracked any flowers yet. Use `/my add flower` to get started.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /my vases ──────────────────────────────────────────────────
    @my_group.command(name="vases", description="Show your vase collection")
    async def my_vases(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        items = get_player_vases(
            str(interaction.guild_id), str(interaction.user.id)
        )
        embed = _items_embed(
            f"🏺 {interaction.user.display_name}'s Vases",
            items, DWG_BLUE,
            empty_msg="You haven't tracked any vases yet. Use `/my add vase` to get started.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /my add flower ─────────────────────────────────────────────
    @add_group.command(name="flower", description="Add a flower to your collection")
    @app_commands.describe(name="The flower's name (autocomplete enabled)")
    @app_commands.autocomplete(name=flower_name_autocomplete)
    async def my_add_flower(interaction: discord.Interaction, name: str):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        matched = find_flower_match(name)
        if not matched:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Flower Not Found",
                    description=(
                        f"No flower matches **{name}**.\n\n"
                        "Use the autocomplete or ask a leader to add it via the dashboard."
                    ),
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        ok = add_player_flower(
            str(interaction.guild_id), str(interaction.user.id), matched,
            source_type="manual", logged_by=str(interaction.user.id),
        )
        if not ok:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"You already have **{matched}** in your collection.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🌸 Flower Added",
                description=f"**{matched}** added to your collection.",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    # ── /my add vase ───────────────────────────────────────────────
    @add_group.command(name="vase", description="Add a vase to your collection")
    @app_commands.describe(name="The vase's name (autocomplete enabled)")
    @app_commands.autocomplete(name=vase_name_autocomplete)
    async def my_add_vase(interaction: discord.Interaction, name: str):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        matched = find_vase_match(name)
        if not matched:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Vase Not Found",
                    description=(
                        f"No vase matches **{name}**.\n\n"
                        "Use the autocomplete or ask a leader to add it via the dashboard."
                    ),
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        ok = add_player_vase(
            str(interaction.guild_id), str(interaction.user.id), matched,
            source_type="manual", logged_by=str(interaction.user.id),
        )
        if not ok:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"You already have **{matched}** in your collection.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🏺 Vase Added",
                description=f"**{matched}** added to your collection.",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    # ── /my remove flower ──────────────────────────────────────────
    @remove_group.command(name="flower", description="Remove a flower from your collection")
    @app_commands.describe(name="The flower's name (autocomplete enabled)")
    @app_commands.autocomplete(name=flower_name_autocomplete)
    async def my_remove_flower(interaction: discord.Interaction, name: str):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        matched = find_flower_match(name) or name
        ok = remove_player_flower(
            str(interaction.guild_id), str(interaction.user.id), matched,
        )
        if not ok:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"You don't have **{matched}** in your collection.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🗑️ Flower Removed",
                description=f"**{matched}** removed from your collection.",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    # ── /my remove vase ────────────────────────────────────────────
    @remove_group.command(name="vase", description="Remove a vase from your collection")
    @app_commands.describe(name="The vase's name (autocomplete enabled)")
    @app_commands.autocomplete(name=vase_name_autocomplete)
    async def my_remove_vase(interaction: discord.Interaction, name: str):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        matched = find_vase_match(name) or name
        ok = remove_player_vase(
            str(interaction.guild_id), str(interaction.user.id), matched,
        )
        if not ok:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"You don't have **{matched}** in your collection.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🗑️ Vase Removed",
                description=f"**{matched}** removed from your collection.",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    # ── /my missing flowers ────────────────────────────────────────
    @missing_grp.command(name="flowers", description="Flowers from the master list you don't have yet")
    async def my_missing_flowers(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        items = get_player_missing_flowers(
            str(interaction.guild_id), str(interaction.user.id)
        )
        embed = _items_embed(
            f"🌱 Flowers {interaction.user.display_name} is missing",
            items, DWG_PURPLE,
            empty_msg="You have every flower in the master list! 🌟",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /my missing vases ──────────────────────────────────────────
    @missing_grp.command(name="vases", description="Vases from the master list you don't have yet")
    async def my_missing_vases(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        items = get_player_missing_vases(
            str(interaction.guild_id), str(interaction.user.id)
        )
        embed = _items_embed(
            f"🌱 Vases {interaction.user.display_name} is missing",
            items, DWG_PURPLE,
            empty_msg="You have every vase in the master list! 🌟",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    tree.add_command(my_group)
