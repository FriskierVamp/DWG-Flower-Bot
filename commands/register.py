"""
commands/register.py
Dreamweaving Garden Bot — /register command
Modal form → DB insert → role swap (New → Member).
"""

import discord
from discord import app_commands
from db.queries import find_player, register_player
from db.schema  import get_guild_config
from utils.guards import reject_if_not_setup

DWG_PURPLE = discord.Color(0xC9A0FF)
DWG_MINT   = discord.Color(0xB8F2D0)
DWG_PINK   = discord.Color(0xFFB3C1)


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

        # 3 — Verify member has the New role (safety net)
        member = interaction.user
        has_new_role = any(
            str(r.id) == str(new_role_id) for r in member.roles
        ) if new_role_id else False

        if new_role_id and not has_new_role:
            # They don't have the New role — flag it but still register them
            # Leaders are notified via the log channel
            flag_admin = True
        else:
            flag_admin = False

        # 4 — Write to DB
        success = register_player(
            guild_id, discord_id, interaction.user.display_name, ign_value
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

        # 5 — Role swap: remove New, assign Member
        swap_status = ""
        try:
            new_role    = interaction.guild.get_role(int(new_role_id))    if new_role_id    else None
            member_role = interaction.guild.get_role(int(member_role_id)) if member_role_id else None

            if new_role and new_role in member.roles:
                await member.remove_roles(new_role, reason="DWG registration")
            if member_role:
                await member.add_roles(member_role, reason="DWG registration")
            swap_status = f"✅ Role updated to <@&{member_role_id}>"
        except discord.Forbidden:
            swap_status = "⚠️ Bot lacks permission to manage roles — ask an admin to fix this."
        except Exception as e:
            swap_status = f"⚠️ Role swap failed: {e}"

        # 6 — Confirm to user
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🌸 Welcome to the Garden!",
                description=(
                    f"You're now registered as **{ign_value}**.\n\n"
                    f"{swap_status}\n\n"
                    "You can now track flowers, check league standings, and more.\n"
                    "Use `/help` to see what's available."
                ),
                color=DWG_MINT,
            ),
            ephemeral=False,
        )

        # 7 — Post to log channel + flag admin if needed
        log_channel_id = cfg.get("log_channel_id")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(int(log_channel_id))
            if log_channel:
                log_embed = discord.Embed(
                    title="🌱 New Member Registered",
                    description=(
                        f"**Player:** {member.mention}\n"
                        f"**In-Game Name:** {ign_value}\n"
                        f"**Discord:** {interaction.user.display_name}"
                    ),
                    color=DWG_MINT,
                )
                if flag_admin:
                    log_embed.add_field(
                        name="⚠️ Flag for Leaders",
                        value=(
                            "This player registered without the expected **New** role. "
                            "Please verify their role assignment."
                        ),
                        inline=False,
                    )
                    log_embed.color = DWG_PINK
                await log_channel.send(embed=log_embed)


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
