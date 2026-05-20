"""
commands/add.py
Dreamweaving Garden Bot — /add command group
Modal-based manual entry for flowers, vases, league, and contributions.
"""

import discord
from discord import app_commands
from db.queries import (
    find_flower_match, add_player_flower, upsert_vase,
    log_league_entry, log_contribution, find_player,
    get_flower_names_for_autocomplete,
)
from utils.guards import reject_if_not_setup, reject_if_not_registered

DWG_PURPLE = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0xB8D9B0)
DWG_PINK   = discord.Color(0xF7CCD8)
DWG_GOLD   = discord.Color(0xE8C878)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"


# ------------------------------------------------------------------
# MODALS
# ------------------------------------------------------------------

class AddFlowerModal(discord.ui.Modal, title="Add Flower to Profile"):
    flower_name = discord.ui.TextInput(
        label="Flower Name",
        placeholder="e.g. Moonbloom Rose",
        min_length=2,
        max_length=100,
        required=True,
    )

    def __init__(self, guild_id: str, discord_id: str):
        super().__init__()
        self.guild_id   = guild_id
        self.discord_id = discord_id

    async def on_submit(self, interaction: discord.Interaction):
        name    = self.flower_name.value.strip()
        matched = find_flower_match(name)

        if not matched:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🌸 Flower Not Found",
                    description=(
                        f"**{name}** isn't in the master flower list.\n\n"
                        "Check the spelling or ask a leader to add it to the master list first.\n"
                        "You can also use `/track add` which has autocomplete to help find it."
                    ),
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        added = add_player_flower(
            self.guild_id, self.discord_id, matched,
            source_type="manual",
            logged_by=str(interaction.user.id),
        )

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

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🌸 Flower Added",
                description=f"**{matched}** has been added to your garden profile.",
                color=DWG_MINT,
            ).set_footer(text=FOOTER),
            ephemeral=True,
        )


class AddVaseModal(discord.ui.Modal, title="Add Vase to Profile"):
    vase_type = discord.ui.TextInput(
        label="Vase Type",
        placeholder="e.g. Crystal Vase, Golden Urn…",
        min_length=2,
        max_length=100,
        required=True,
    )
    quantity = discord.ui.TextInput(
        label="Quantity",
        placeholder="How many do you have? (default: 1)",
        max_length=5,
        required=False,
        default="1",
    )

    def __init__(self, guild_id: str, discord_id: str):
        super().__init__()
        self.guild_id   = guild_id
        self.discord_id = discord_id

    async def on_submit(self, interaction: discord.Interaction):
        vase_type = self.vase_type.value.strip()
        try:
            qty = max(1, int(self.quantity.value.strip() or "1"))
        except ValueError:
            qty = 1

        upsert_vase(
            self.guild_id, self.discord_id, vase_type, qty,
            source_type="manual",
            logged_by=str(interaction.user.id),
        )

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🏺 Vase Added",
                description=f"**{vase_type}** × {qty} saved to your profile.",
                color=DWG_MINT,
            ).set_footer(text=FOOTER),
            ephemeral=True,
        )


class AddLeagueModal(discord.ui.Modal, title="Log League Standing"):
    season = discord.ui.TextInput(
        label="Season",
        placeholder="e.g. Season 12, Spring 2026…",
        max_length=50,
        required=False,
    )
    rank = discord.ui.TextInput(
        label="Your Rank",
        placeholder="e.g. 3",
        max_length=6,
        required=True,
    )
    points = discord.ui.TextInput(
        label="Your Points",
        placeholder="e.g. 4250",
        max_length=10,
        required=True,
    )

    def __init__(self, guild_id: str, discord_id: str):
        super().__init__()
        self.guild_id   = guild_id
        self.discord_id = discord_id

    async def on_submit(self, interaction: discord.Interaction):
        season_val = self.season.value.strip() or None
        try:
            rank_val   = int(self.rank.value.strip())
            points_val = int(self.points.value.strip().replace(",", ""))
        except ValueError:
            await interaction.response.send_message(
                "⚠️ Rank and Points must be numbers.", ephemeral=True
            )
            return

        log_league_entry(
            self.guild_id, self.discord_id,
            season=season_val, rank=rank_val, points=points_val,
            source_type="manual",
            logged_by=str(interaction.user.id),
        )

        embed = discord.Embed(
            title="🏆 League Standing Logged",
            color=DWG_GOLD,
        )
        embed.add_field(name="Rank",   value=f"#{rank_val}",         inline=True)
        embed.add_field(name="Points", value=f"{points_val:,}",       inline=True)
        if season_val:
            embed.add_field(name="Season", value=season_val, inline=True)
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AddContributionModal(discord.ui.Modal, title="Log Contribution"):
    amount = discord.ui.TextInput(
        label="Contribution Amount",
        placeholder="e.g. 5000",
        max_length=12,
        required=True,
    )
    contribution_date = discord.ui.TextInput(
        label="Date (optional)",
        placeholder="e.g. 2026-05-19 or May 19",
        max_length=30,
        required=False,
    )
    note = discord.ui.TextInput(
        label="Note (optional)",
        placeholder="e.g. Weekly contribution, event bonus…",
        max_length=200,
        required=False,
        style=discord.TextStyle.short,
    )

    def __init__(self, guild_id: str, discord_id: str):
        super().__init__()
        self.guild_id   = guild_id
        self.discord_id = discord_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount_val = int(self.amount.value.strip().replace(",", ""))
        except ValueError:
            await interaction.response.send_message(
                "⚠️ Amount must be a number.", ephemeral=True
            )
            return

        date_val = self.contribution_date.value.strip() or None
        note_val = self.note.value.strip() or None

        log_contribution(
            self.guild_id, self.discord_id,
            amount=amount_val,
            contribution_date=date_val,
            note=note_val,
            source_type="manual",
            logged_by=str(interaction.user.id),
        )

        embed = discord.Embed(
            title="🤝 Contribution Logged",
            color=DWG_MINT,
        )
        embed.add_field(name="Amount", value=f"{amount_val:,}", inline=True)
        if date_val:
            embed.add_field(name="Date", value=date_val, inline=True)
        if note_val:
            embed.add_field(name="Note", value=note_val, inline=False)
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ------------------------------------------------------------------
# COMMAND GROUP
# ------------------------------------------------------------------

def register_add(tree: app_commands.CommandTree) -> None:

    add = app_commands.Group(
        name="add",
        description="Manually add flowers, vases, league standings, or contributions",
    )

    @add.command(name="flower", description="Add a flower to your garden profile")
    async def add_flower(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_registered(interaction):
            return
        await interaction.response.send_modal(
            AddFlowerModal(str(interaction.guild_id), str(interaction.user.id))
        )

    @add.command(name="vase", description="Add a vase to your profile")
    async def add_vase(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_registered(interaction):
            return
        await interaction.response.send_modal(
            AddVaseModal(str(interaction.guild_id), str(interaction.user.id))
        )

    @add.command(name="league", description="Log your current league standing")
    async def add_league(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_registered(interaction):
            return
        await interaction.response.send_modal(
            AddLeagueModal(str(interaction.guild_id), str(interaction.user.id))
        )

    @add.command(name="contribution", description="Log a contribution amount")
    async def add_contribution(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_registered(interaction):
            return
        await interaction.response.send_modal(
            AddContributionModal(str(interaction.guild_id), str(interaction.user.id))
        )

    tree.add_command(add)
