"""
commands/add.py
Dreamweaving Garden Bot — /add command group
Modal-based manual entry for flowers, vases, league standings, and contributions.
"""

import discord
from discord import app_commands
from db.queries import (
    add_to_collection, find_player,
    log_league_entry, log_contribution,
    get_flower_names_for_autocomplete,
    get_vase_names_for_autocomplete,
)
from utils.guards import reject_if_not_setup, reject_if_not_registered

DWG_PINK   = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0x9ECFA8)
DWG_PURPLE = discord.Color(0xD0AEE8)
DWG_PEACH  = discord.Color(0xF7C898)
DWG_GOLD   = discord.Color(0xE8C878)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"


# ── Modals ─────────────────────────────────────────────────────────

class AddFlowerModal(discord.ui.Modal, title="Add Flower to Your Collection"):
    flower_name = discord.ui.TextInput(
        label="Flower Name",
        placeholder="Must match the master list exactly…",
        min_length=2, max_length=100, required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        name = self.flower_name.value.strip()
        ok, msg = add_to_collection(
            str(interaction.guild_id), str(interaction.user.id), "flower", name
        )
        color = DWG_MINT if ok else DWG_PINK
        await interaction.response.send_message(
            embed=discord.Embed(description=msg, color=color), ephemeral=True)


class AddVaseModal(discord.ui.Modal, title="Add Vase to Your Collection"):
    vase_name = discord.ui.TextInput(
        label="Vase Name",
        placeholder="Must match the master list exactly…",
        min_length=2, max_length=100, required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        name = self.vase_name.value.strip()
        ok, msg = add_to_collection(
            str(interaction.guild_id), str(interaction.user.id), "vase", name
        )
        color = DWG_MINT if ok else DWG_PINK
        await interaction.response.send_message(
            embed=discord.Embed(description=msg, color=color), ephemeral=True)


class AddLeagueModal(discord.ui.Modal, title="Log League Standing"):
    rank   = discord.ui.TextInput(
        label="Rank", placeholder="e.g. 3", required=False, max_length=10)
    points = discord.ui.TextInput(
        label="Points", placeholder="e.g. 4200", required=True, max_length=10)
    season = discord.ui.TextInput(
        label="Season (optional)", placeholder="e.g. Season 5",
        required=False, max_length=50)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id   = str(interaction.guild_id)
        discord_id = str(interaction.user.id)
        try:
            pts  = int(self.points.value.strip().replace(",", ""))
            rank = int(self.rank.value.strip()) if self.rank.value.strip() else None
        except ValueError:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="Rank and Points must be numbers.", color=DWG_PINK),
                ephemeral=True)
            return

        log_league_entry(guild_id, discord_id, rank, pts,
                         self.season.value.strip())
        desc = f"🏆 League standing logged — **{pts:,} pts**"
        if rank:
            desc += f" · Rank **#{rank}**"
        await interaction.response.send_message(
            embed=discord.Embed(description=desc, color=DWG_GOLD), ephemeral=True)


class AddContributionModal(discord.ui.Modal, title="Log Contribution"):
    amount = discord.ui.TextInput(
        label="Amount", placeholder="e.g. 500", required=True, max_length=12)
    note   = discord.ui.TextInput(
        label="Note (optional)", placeholder="e.g. Weekly donation",
        required=False, max_length=200, style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id   = str(interaction.guild_id)
        discord_id = str(interaction.user.id)
        try:
            amt = int(self.amount.value.strip().replace(",", ""))
        except ValueError:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="Amount must be a number.", color=DWG_PINK),
                ephemeral=True)
            return

        log_contribution(guild_id, discord_id, amt, self.note.value.strip())
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"🤝 Contribution of **{amt:,}** logged!",
                color=DWG_MINT,
            ), ephemeral=True)


# ── Command registration ───────────────────────────────────────────

def register_add(tree: app_commands.CommandTree) -> None:
    add = app_commands.Group(name="add", description="Log flowers, vases, league, or contributions")

    @add.command(name="flower", description="Add a flower to your collection")
    async def add_flower(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):    return
        if await reject_if_not_registered(interaction): return
        await interaction.response.send_modal(AddFlowerModal())

    @add.command(name="vase", description="Add a vase to your collection")
    async def add_vase(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):    return
        if await reject_if_not_registered(interaction): return
        await interaction.response.send_modal(AddVaseModal())

    @add.command(name="league", description="Log your league standing")
    async def add_league(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):    return
        if await reject_if_not_registered(interaction): return
        await interaction.response.send_modal(AddLeagueModal())

    @add.command(name="contribution", description="Log a guild contribution")
    async def add_contribution(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):    return
        if await reject_if_not_registered(interaction): return
        await interaction.response.send_modal(AddContributionModal())

    tree.add_command(add)
