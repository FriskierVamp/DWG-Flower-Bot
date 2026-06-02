"""
commands/register.py
Dreamweaving Garden Bot — /register command
Modal form → DB insert → role swap (New → Member) → welcome post in same channel.
"""

import discord
from discord import app_commands
from db.queries import find_player, register_player
from db.schema  import get_guild_config
from utils.guards import reject_if_not_setup

DWG_PURPLE = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0xB8D9B0)
DWG_PINK   = discord.Color(0xF7CCD8)


# ------------------------------------------------------------------
# MODAL
# ------------------------------------------------------------------

class RegisterModal(discord.ui.Modal, title="Register for Dreamweaving Garden"):

    ign = discord.ui.TextInput(
        label="In-Game Name",
        placeholder="Enter your exact in-game name...",
        min_length=2,
        max_length=50,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild_id   = str(interaction.guild_id)
        discord_id = str(interaction.user.id)
        ign_value  = self.ign.value.strip()

        # 1 — Check if already registered
        existing = find_player(guild_id, discord_id)
        if existing:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="📋 Already Registered",
                    description=(
                        f"You're already registered as **{existing['ign']}**.\n\n"
                        "If your in-game name has changed, ask a leader to update it."
                    ),
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        # 2 — Fetch guild config for role IDs
        cfg = get_guild_config(guild_id)
        if not cfg:
            await interaction.response.send_message(
                "⚠️ Server config not found. Ask an admin to run `/setup` first.",
                ephemeral=True,
            )
            return

        new_role_id    = cfg.get("new_role_id")
        member_role_id = cfg.get("member_role_id")
        member         = interaction.user

        # 3 — Write to DB
        success = register_player(
            guild_id, discord_id, member.display_name, ign_value
        )
        if not success:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="⚠️ Already Registered",
                    description="It looks like you've already been registered. Ask a leader if something seems wrong.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        # 4 — Role swap: remove New, assign Member
        swap_status = ""
        try:
            # Fetch fresh member from Discord so roles aren't stale/cached
            fresh_member = await interaction.guild.fetch_member(int(discord_id))
            new_role    = interaction.guild.get_role(int(new_role_id))    if new_role_id    else None
            member_role = interaction.guild.get_role(int(member_role_id)) if member_role_id else None

            if new_role and new_role in fresh_member.roles:
                await fresh_member.remove_roles(new_role, reason="DWG registration")
            if member_role:
                await fresh_member.add_roles(member_role, reason="DWG registration")
                swap_status = f"\n✅ Role updated to <@&{member_role_id}>"
        except discord.Forbidden:
            swap_status = "\n⚠️ Bot lacks permission to manage roles — ask an admin to fix this."
        except Exception as e:
            swap_status = f"\n⚠️ Role swap failed: {e}"

        # 5 — Public welcome in the channel where /register was used
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🌸 Welcome to the Garden!",
                description=(
                    f"{member.mention} is now registered as **{ign_value}**."
                    f"{swap_status}\n\n"
                    "Use `/help` to see what's available."
                ),
                color=DWG_MINT,
            ),
            ephemeral=False,
        )


# ------------------------------------------------------------------
# /register COMMAND
# ------------------------------------------------------------------

def register_register(tree: app_commands.CommandTree) -> None:

    @tree.command(
        name="register",
        description="Register yourself in Dreamweaving Garden",
    )
    async def register_cmd(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):
            return

        # Already registered? Show status instead of opening modal
        existing = find_player(
            str(interaction.guild_id), str(interaction.user.id)
        )
        if existing:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="📋 Already Registered",
                    description=(
                        f"You're already registered as **{existing['ign']}**.\n\n"
                        "If your in-game name has changed, ask a leader to update it."
                    ),
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(RegisterModal())
