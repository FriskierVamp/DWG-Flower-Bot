"""
commands/register.py
Dreamweaving Garden Bot — /register command
Modal form → DB insert → role swap (Seedling → Member).
"""

import discord
from discord import app_commands
from db.queries import find_player, upsert_member, get_guild_config
from utils.guards import reject_if_not_setup

DWG_PINK   = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0x9ECFA8)
DWG_PURPLE = discord.Color(0xD0AEE8)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"


class RegisterModal(discord.ui.Modal, title="Join Dreamweaving Garden"):
    ign = discord.ui.TextInput(
        label="In-Game Name",
        placeholder="Enter your exact in-game name…",
        min_length=2,
        max_length=50,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild_id   = str(interaction.guild_id)
        discord_id = str(interaction.user.id)
        ign_value  = self.ign.value.strip()

        # Already registered?
        existing = find_player(guild_id, discord_id)
        if existing:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="📋 Already Registered",
                    description=(
                        f"You're already registered as **{existing['ign']}**.\n"
                        "If your IGN changed, ask a leader to update it."
                    ),
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        # Save to DB
        upsert_member(guild_id, discord_id, ign_value)

        # Role swap: remove Seedling, add Member
        cfg      = get_guild_config(guild_id)
        member   = interaction.user
        guild    = interaction.guild
        messages = []

        if cfg:
            if cfg.get("seedling_role_id"):
                seedling_role = guild.get_role(int(cfg["seedling_role_id"]))
                if seedling_role and seedling_role in member.roles:
                    try:
                        await member.remove_roles(seedling_role, reason="Registered via /register")
                    except discord.Forbidden:
                        messages.append("⚠️ Couldn't remove Seedling role — check bot permissions.")

            if cfg.get("member_role_id"):
                member_role = guild.get_role(int(cfg["member_role_id"]))
                if member_role:
                    try:
                        await member.add_roles(member_role, reason="Registered via /register")
                    except discord.Forbidden:
                        messages.append("⚠️ Couldn't assign Member role — check bot permissions.")

        embed = discord.Embed(
            title="🌸 Welcome to the Garden!",
            description=(
                f"You've been registered as **{ign_value}**.\n\n"
                "You can now use `/track`, `/add`, and `/lookup` commands."
                + ("\n\n" + "\n".join(messages) if messages else "")
            ),
            color=DWG_MINT,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)


def register_register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="register", description="Register your in-game name to join the garden")
    async def register(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):
            return
        await interaction.response.send_modal(RegisterModal())
