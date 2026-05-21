"""
utils/guards.py
Dreamweaving Garden Bot — Interaction guards
Reusable checks for leader roles, server setup, and registration status.
"""

import discord
from db.schema import get_guild_config, get_leader_role_ids


# ------------------------------------------------------------------
# SETUP GUARD
# Blocks commands in servers that haven't run /setup yet.
# A guild is considered set up when it has a log_channel_id saved,
# which is only written at the end of the 3-step /setup wizard.
# ------------------------------------------------------------------

async def reject_if_not_setup(interaction: discord.Interaction) -> bool:
    """Returns True (and sends an error) if the guild hasn't completed /setup."""
    if not interaction.guild:
        await interaction.response.send_message(
            "❌ This command can only be used inside a server.",
            ephemeral=True,
        )
        return True

    cfg = get_guild_config(str(interaction.guild_id))
    # Treat as set up if we have a log channel (written last in the wizard)
    # or if setup_complete flag is set (legacy)
    is_configured = cfg and (cfg.get("log_channel_id") or cfg.get("setup_complete"))

    if not is_configured:
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚙️ Server Not Configured",
                description=(
                    "This server hasn't finished bot setup yet.\n\n"
                    "A server admin needs to run `/setup` first to configure roles and channels.\n"
                    "The wizard will walk through everything step by step."
                ),
                color=discord.Color(0xFFB3C1),
            ),
            ephemeral=True,
        )
        return True

    return False


async def reject_if_not_in_server(interaction: discord.Interaction) -> bool:
    """Returns True (and sends an error) if the command is run outside a server."""
    if not interaction.guild:
        await interaction.response.send_message(
            "❌ This command can only be used inside a server.",
            ephemeral=True,
        )
        return True
    return False


# ------------------------------------------------------------------
# LEADER GUARD
# ------------------------------------------------------------------

def is_leader(interaction: discord.Interaction) -> bool:
    """
    Returns True if the user holds at least one configured leader role.
    Falls back to server administrator permission if no roles are configured yet.
    """
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False

    # Server admins always pass
    if interaction.user.guild_permissions.administrator:
        return True

    leader_ids = get_leader_role_ids(str(interaction.guild_id))
    if not leader_ids:
        return False

    user_role_ids = {role.id for role in interaction.user.roles}
    return bool(user_role_ids & set(leader_ids))


async def reject_if_not_leader(interaction: discord.Interaction) -> bool:
    """Returns True (and sends an error) if the user is not a leader."""
    if not is_leader(interaction):
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🔒 Leader Only",
                description="You need a leader role to use this command.",
                color=discord.Color(0xFFB3C1),
            ),
            ephemeral=True,
        )
        return True
    return False


# ------------------------------------------------------------------
# REGISTRATION GUARD
# ------------------------------------------------------------------

async def reject_if_not_registered(interaction: discord.Interaction) -> bool:
    """Returns True (and sends an error) if the user isn't registered."""
    from db.queries import find_player
    player = find_player(str(interaction.guild_id), str(interaction.user.id))
    if not player:
        await interaction.response.send_message(
            embed=discord.Embed(
                title="📋 Not Registered",
                description=(
                    "You're not registered in this server yet.\n\n"
                    "Run `/register` to get started — it only takes a moment!"
                ),
                color=discord.Color(0xFFB3C1),
            ),
            ephemeral=True,
        )
        return True
    return False
