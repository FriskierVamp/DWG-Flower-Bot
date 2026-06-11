"""
commands/my.py
Dreamweaving Garden Bot — /my command group (everyone)
Personal collection management: flowers, vases, missing items.

Subcommands:
  /my flowers              — show your flower collection grouped by base points (highest first)
  /my vases                — show your vase collection grouped by base points (highest first)
  /my add flower [name]    — add a flower to your collection
  /my add vase [name]      — add a vase to your collection
  /my remove flower [name] — remove a flower from your collection
  /my remove vase [name]   — remove a vase from your collection
  /my missing flowers      — flowers from the master list you don't have, grouped by base points
  /my missing vases        — vases from the master list you don't have, grouped by base points
"""

import discord
from discord import app_commands
from db.queries import (
    add_player_flower, remove_player_flower,
    add_player_vase,   remove_player_vase,
    get_player_flowers_with_points, get_player_missing_flowers_with_points,
    get_player_vases_with_points,   get_player_missing_vases_with_points,
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
# DISPLAY HELPER — grouped by base points, highest first
# ------------------------------------------------------------------

def _grouped_embed(
    title: str,
    items: list[dict],   # each dict has "name" and "base_points"
    color: discord.Color,
    empty_msg: str = "Nothing here yet.",
    show_upgraded: bool = True,
) -> list[discord.Embed]:
    """
    Build one or more embeds displaying items grouped by base_points,
    highest group first.

    Each group header shows the point value (and ×2 upgraded if applicable).
    Items within each group are listed alphabetically.

    Returns a list of embeds (may be >1 if the collection is very large).
    """
    if not items:
        e = discord.Embed(title=title, description=empty_msg, color=color)
        e.set_footer(text=FOOTER)
        return [e]

    # Group by base_points
    from collections import defaultdict
    groups: dict[int, list[str]] = defaultdict(list)
    for item in items:
        groups[item["base_points"]].append(item["name"])

    # Build lines, highest points first
    lines = []
    for pts in sorted(groups.keys(), reverse=True):
        names = groups[pts]
        if show_upgraded:
            header = f"**{pts} pts  ·  {pts * 2} upgraded** — {len(names)} flower{'s' if len(names) != 1 else ''}"
        else:
            header = f"**{pts} pts** — {len(names)} flower{'s' if len(names) != 1 else ''}"
        lines.append(header)
        for name in sorted(names):
            lines.append(f"  • {name}")
        lines.append("")  # blank line between groups

    # Chunk into embeds (Discord embed description cap = 4096 chars)
    embeds = []
    current_lines = []
    current_len   = 0
    first         = True

    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > 3900 and current_lines:
            e = discord.Embed(
                title=title if first else f"{title} (continued)",
                description="\n".join(current_lines).rstrip(),
                color=color,
            )
            e.set_footer(text=FOOTER)
            embeds.append(e)
            current_lines = []
            current_len   = 0
            first         = False
        current_lines.append(line)
        current_len += line_len

    if current_lines:
        e = discord.Embed(
            title=title if first else f"{title} (continued)",
            description="\n".join(current_lines).rstrip(),
            color=color,
        )
        e.set_footer(text=FOOTER)
        embeds.append(e)

    # Add total count to first embed footer
    total = len(items)
    group_count = len(groups)
    embeds[0].set_footer(
        text=f"{total} total  ·  {group_count} point group{'s' if group_count != 1 else ''}  ·  {FOOTER}"
    )

    return embeds


# ------------------------------------------------------------------
# REGISTRATION
# ------------------------------------------------------------------

def register_my(tree: app_commands.CommandTree) -> None:

    my_group     = app_commands.Group(name="my", description="Manage your personal collection")
    add_group    = app_commands.Group(name="add",     description="Add to your collection",      parent=my_group)
    remove_group = app_commands.Group(name="remove",  description="Remove from your collection", parent=my_group)
    missing_grp  = app_commands.Group(name="missing", description="What you're missing",          parent=my_group)

    # ── /my flowers ────────────────────────────────────────────────
    @my_group.command(name="flowers", description="Show your flower collection grouped by points")
    async def my_flowers(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        items = get_player_flowers_with_points(
            str(interaction.guild_id), str(interaction.user.id)
        )
        embeds = _grouped_embed(
            f"🌸 {interaction.user.display_name}'s Flowers",
            items, DWG_PINK,
            empty_msg="You haven't tracked any flowers yet. Use `/my add flower` to get started.",
            show_upgraded=True,
        )
        await interaction.response.send_message(embeds=embeds[:10], ephemeral=True)

    # ── /my vases ──────────────────────────────────────────────────
    @my_group.command(name="vases", description="Show your vase collection grouped by points")
    async def my_vases(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        items = get_player_vases_with_points(
            str(interaction.guild_id), str(interaction.user.id)
        )
        embeds = _grouped_embed(
            f"🏺 {interaction.user.display_name}'s Vases",
            items, DWG_BLUE,
            empty_msg="You haven't tracked any vases yet. Use `/my add vase` to get started.",
            show_upgraded=True,
        )
        await interaction.response.send_message(embeds=embeds[:10], ephemeral=True)

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

        items = get_player_missing_flowers_with_points(
            str(interaction.guild_id), str(interaction.user.id)
        )
        embeds = _grouped_embed(
            f"🌱 Flowers {interaction.user.display_name} is missing",
            items, DWG_PURPLE,
            empty_msg="You have every flower in the master list! 🌟",
            show_upgraded=True,
        )
        await interaction.response.send_message(embeds=embeds[:10], ephemeral=True)

    # ── /my missing vases ──────────────────────────────────────────
    @missing_grp.command(name="vases", description="Vases from the master list you don't have yet")
    async def my_missing_vases(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        items = get_player_missing_vases_with_points(
            str(interaction.guild_id), str(interaction.user.id)
        )
        embeds = _grouped_embed(
            f"🌱 Vases {interaction.user.display_name} is missing",
            items, DWG_PURPLE,
            empty_msg="You have every vase in the master list! 🌟",
            show_upgraded=True,
        )
        await interaction.response.send_message(embeds=embeds[:10], ephemeral=True)

    tree.add_command(my_group)
