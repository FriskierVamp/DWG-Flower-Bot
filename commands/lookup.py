"""
commands/lookup.py
Dreamweaving Garden Bot — /lookup command group (everyone)
Cross-guild discovery: who has what, what's missing entirely.

Subcommands:
  /lookup flower [name]   — who in the guild has this flower
  /lookup vase [name]     — who in the guild has this vase
  /lookup missing flowers — flowers nobody in the guild has
  /lookup missing vases   — vases nobody in the guild has
"""

import discord
from discord import app_commands
from db.queries import (
    get_players_with_flower, get_players_with_vase,
    get_guild_missing_flowers, get_guild_missing_vases,
    find_flower_match, find_vase_match,
    get_flower_names_for_autocomplete, get_vase_names_for_autocomplete,
)
from utils.guards import reject_if_not_setup, reject_if_not_registered

DWG_PURPLE = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0xB8D9B0)
DWG_PINK   = discord.Color(0xF7CCD8)
DWG_BLUE   = discord.Color(0xB8D8F0)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"


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


def _names_embed(title: str, items: list[str], color: discord.Color,
                 empty_msg: str) -> discord.Embed:
    if not items:
        embed = discord.Embed(title=title, description=empty_msg, color=color)
    else:
        body = "\n".join(f"• {n}" for n in items[:75])
        if len(items) > 75:
            body += f"\n\n_… and {len(items) - 75} more._"
        embed = discord.Embed(
            title=f"{title}  ({len(items)})",
            description=body,
            color=color,
        )
    embed.set_footer(text=FOOTER)
    return embed


def register_lookup(tree: app_commands.CommandTree) -> None:

    lookup       = app_commands.Group(name="lookup", description="Find things across the guild")
    missing_grp  = app_commands.Group(name="missing", description="What nobody has yet", parent=lookup)

    # ── /lookup flower [name] ──────────────────────────────────────
    @lookup.command(name="flower", description="See who in the guild has this flower")
    @app_commands.describe(name="The flower's name (autocomplete enabled)")
    @app_commands.autocomplete(name=flower_name_autocomplete)
    async def lookup_flower(interaction: discord.Interaction, name: str):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        matched = find_flower_match(name)
        if not matched:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ No flower matches **{name}**.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        players = get_players_with_flower(str(interaction.guild_id), matched)
        igns = [p["ign"] for p in players]
        embed = _names_embed(
            f"🌸 Who has {matched}",
            igns, DWG_PINK,
            empty_msg=f"Nobody in this guild has **{matched}** yet.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /lookup vase [name] ────────────────────────────────────────
    @lookup.command(name="vase", description="See who in the guild has this vase")
    @app_commands.describe(name="The vase's name (autocomplete enabled)")
    @app_commands.autocomplete(name=vase_name_autocomplete)
    async def lookup_vase(interaction: discord.Interaction, name: str):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        matched = find_vase_match(name)
        if not matched:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"❌ No vase matches **{name}**.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        players = get_players_with_vase(str(interaction.guild_id), matched)
        igns = [p["ign"] for p in players]
        embed = _names_embed(
            f"🏺 Who has {matched}",
            igns, DWG_BLUE,
            empty_msg=f"Nobody in this guild has **{matched}** yet.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /lookup missing flowers ────────────────────────────────────
    @missing_grp.command(name="flowers", description="Flowers nobody in the guild has yet")
    async def lookup_missing_flowers(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        items = get_guild_missing_flowers(str(interaction.guild_id))
        embed = _names_embed(
            "🌱 Flowers nobody has yet",
            items, DWG_PURPLE,
            empty_msg="Every flower in the master list is owned by someone! 🌟",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /lookup missing vases ──────────────────────────────────────
    @missing_grp.command(name="vases", description="Vases nobody in the guild has yet")
    async def lookup_missing_vases(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_registered(interaction): return

        items = get_guild_missing_vases(str(interaction.guild_id))
        embed = _names_embed(
            "🌱 Vases nobody has yet",
            items, DWG_PURPLE,
            empty_msg="Every vase in the master list is owned by someone! 🌟",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    tree.add_command(lookup)
