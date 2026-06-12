"""
commands/my.py
Dreamweaving Garden Bot — /my command group (everyone)
Personal collection management: flowers, vases, missing items.

Subcommands:
  /my flowers              — collection grouped by rarity, then points desc within each tier
  /my vases                — same for vases
  /my add flower [name]    — add a flower (autocomplete, no modal)
  /my add vase [name]      — add a vase (autocomplete, no modal)
  /my remove flower [name] — remove a flower (autocomplete, no modal)
  /my remove vase [name]   — remove a vase (autocomplete, no modal)
  /my missing flowers      — missing flowers grouped by rarity, then points desc
  /my missing vases        — missing vases grouped by rarity, then points desc
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

RARITY_ORDER = ["Shine", "Star", "Rare", "Fine", "Basic"]
RARITY_EMOJI = {"Shine": "✦", "Star": "★", "Rare": "◆", "Fine": "◇", "Basic": "·"}


# ------------------------------------------------------------------
# AUTOCOMPLETE HELPERS
# ------------------------------------------------------------------

async def flower_name_autocomplete(
    interaction: discord.Interaction, current: str,
) -> list[app_commands.Choice[str]]:
    names = get_flower_names_for_autocomplete()
    q = (current or "").lower()
    return [app_commands.Choice(name=n, value=n) for n in names if q in n.lower()][:25]


async def vase_name_autocomplete(
    interaction: discord.Interaction, current: str,
) -> list[app_commands.Choice[str]]:
    names = get_vase_names_for_autocomplete()
    q = (current or "").lower()
    return [app_commands.Choice(name=n, value=n) for n in names if q in n.lower()][:25]


# ------------------------------------------------------------------
# DISPLAY HELPER — rarity groups, points desc within each group
# ------------------------------------------------------------------

def _grouped_embed(
    title: str,
    items: list[dict],   # each dict: {name, rarity, base_points}
    color: discord.Color,
    empty_msg: str = "Nothing here yet.",
) -> list[discord.Embed]:
    """
    Groups items by rarity tier (Shine → Star → Rare → Fine → Basic).
    Within each tier, sorted by base_points descending then name alphabetically.
    Each item line shows: name · X pts · X×2 upgraded

    Returns a list of embeds (paginated at ~3900 chars each).
    """
    if not items:
        e = discord.Embed(title=title, description=empty_msg, color=color)
        e.set_footer(text=FOOTER)
        return [e]

    from collections import defaultdict
    by_rarity: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        by_rarity[item.get("rarity", "Basic")].append(item)

    lines = []
    for rarity in RARITY_ORDER:
        if rarity not in by_rarity:
            continue
        group = sorted(
            by_rarity[rarity],
            key=lambda f: (-f["base_points"], f["name"].lower())
        )
        emoji = RARITY_EMOJI.get(rarity, "·")
        lines.append(f"**{emoji} {rarity}** — {len(group)}")
        for f in group:
            pts = f["base_points"]
            lines.append(f"  • {f['name']}  ·  {pts} pts  ·  {pts * 2} upgraded")
        lines.append("")

    # Paginate
    embeds    = []
    cur_lines = []
    cur_len   = 0
    first     = True

    for line in lines:
        line_len = len(line) + 1
        if cur_len + line_len > 3900 and cur_lines:
            e = discord.Embed(
                title=title if first else f"{title} (continued)",
                description="\n".join(cur_lines).rstrip(),
                color=color,
            )
            e.set_footer(text=FOOTER)
            embeds.append(e)
            cur_lines = []
            cur_len   = 0
            first     = False
        cur_lines.append(line)
        cur_len += line_len

    if cur_lines:
        e = discord.Embed(
            title=title if first else f"{title} (continued)",
            description="\n".join(cur_lines).rstrip(),
            color=color,
        )
        e.set_footer(text=FOOTER)
        embeds.append(e)

    total         = len(items)
    rarity_groups = len(by_rarity)
    embeds[0].set_footer(
        text=f"{total} total  ·  {rarity_groups} rarit{'ies' if rarity_groups != 1 else 'y'}  ·  {FOOTER}"
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
    @my_group.command(name="flowers", description="Show your flower collection grouped by rarity and points")
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
        )
        await interaction.response.send_message(embeds=embeds[:10], ephemeral=True)

    # ── /my vases ──────────────────────────────────────────────────
    @my_group.command(name="vases", description="Show your vase collection grouped by rarity and points")
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
    @missing_grp.command(name="flowers", description="Flowers you're missing, grouped by rarity and points")
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
        )
        await interaction.response.send_message(embeds=embeds[:10], ephemeral=True)

    # ── /my missing vases ──────────────────────────────────────────
    @missing_grp.command(name="vases", description="Vases you're missing, grouped by rarity and points")
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
        )
        await interaction.response.send_message(embeds=embeds[:10], ephemeral=True)

    tree.add_command(my_group)
