"""
commands/help.py
Dreamweaving Garden Bot — /help command (everyone)
Sends the bot guide privately to whoever asks.
"""

import discord
from discord import app_commands
from utils.guards import reject_if_not_setup
from commands.admin import _guide_embeds


def register_help(tree: app_commands.CommandTree) -> None:

    @tree.command(name="help", description="Show the Dreamweaving Garden command guide")
    async def help_cmd(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return

        embeds = _guide_embeds()
        # Discord caps a single message at 10 embeds — we have 5, well under
        await interaction.response.send_message(embeds=embeds, ephemeral=True)
