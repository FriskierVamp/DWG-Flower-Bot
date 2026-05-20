"""
commands/admin.py
Dreamweaving Garden Bot — /admin command group
Member management, collection overrides, config updates. Leader only.
"""

import json
import discord
from discord import app_commands
from db.queries import (
    get_all_members, upsert_member, delete_member,
    add_to_collection, remove_from_collection,
    get_collection_item_names, upsert_guild_config,
    get_flower_names_for_autocomplete,
    get_vase_names_for_autocomplete,
)
from utils.guards import reject_if_not_setup, reject_if_not_leader

DWG_PINK   = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0x9ECFA8)
DWG_PURPLE = discord.Color(0xD0AEE8)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"


async def flower_ac(interaction, current):
    return [app_commands.Choice(name=n, value=n)
            for n in get_flower_names_for_autocomplete(current)]

async def vase_ac(interaction, current):
    return [app_commands.Choice(name=n, value=n)
            for n in get_vase_names_for_autocomplete(current)]


def register_admin(tree: app_commands.CommandTree) -> None:
    admin = app_commands.Group(name="admin", description="Admin tools (leader only)")

    # ── member subgroup ────────────────────────────────────────────
    member_group = app_commands.Group(
        name="member", description="Manage registered members", parent=admin)

    @member_group.command(name="list", description="List all registered members")
    async def member_list(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):  return
        if await reject_if_not_leader(interaction): return
        members = get_all_members(str(interaction.guild_id))
        if not members:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="No members registered yet.",
                    color=DWG_PINK,
                ), ephemeral=True)
            return
        lines = "\n".join(f"· **{m['ign']}** — <@{m['discord_id']}>" for m in members)
        embed = discord.Embed(
            title=f"🌸 Registered Members ({len(members)})",
            description=lines,
            color=DWG_PURPLE,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @member_group.command(name="add", description="Manually register a member")
    @app_commands.describe(member="Discord member", ign="In-game name")
    async def member_add(interaction: discord.Interaction,
                         member: discord.Member, ign: str):
        if await reject_if_not_setup(interaction):  return
        if await reject_if_not_leader(interaction): return
        upsert_member(str(interaction.guild_id), str(member.id), ign.strip())
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"✅ {member.mention} registered as **{ign.strip()}**.",
                color=DWG_MINT,
            ), ephemeral=True)

    @member_group.command(name="remove", description="Remove a member's registration")
    @app_commands.describe(member="Discord member to remove")
    async def member_remove(interaction: discord.Interaction, member: discord.Member):
        if await reject_if_not_setup(interaction):  return
        if await reject_if_not_leader(interaction): return
        deleted = delete_member(str(interaction.guild_id), str(member.id))
        if deleted:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"🗑️ {member.mention} has been unregistered.",
                    color=DWG_MINT,
                ), ephemeral=True)
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{member.mention} isn't registered.",
                    color=DWG_PINK,
                ), ephemeral=True)

    @member_group.command(name="updateign", description="Update a member's in-game name")
    @app_commands.describe(member="Discord member", ign="New in-game name")
    async def member_updateign(interaction: discord.Interaction,
                               member: discord.Member, ign: str):
        if await reject_if_not_setup(interaction):  return
        if await reject_if_not_leader(interaction): return
        upsert_member(str(interaction.guild_id), str(member.id), ign.strip())
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"✅ {member.mention}'s IGN updated to **{ign.strip()}**.",
                color=DWG_MINT,
            ), ephemeral=True)

    # ── flower subgroup ────────────────────────────────────────────
    flower_group = app_commands.Group(
        name="flower", description="Override a player's flower collection", parent=admin)

    @flower_group.command(name="add", description="Add a flower to any player's collection")
    @app_commands.describe(member="Target member", flower="Flower name")
    @app_commands.autocomplete(flower=flower_ac)
    async def admin_flower_add(interaction: discord.Interaction,
                               member: discord.Member, flower: str):
        if await reject_if_not_setup(interaction):  return
        if await reject_if_not_leader(interaction): return
        ok, msg = add_to_collection(
            str(interaction.guild_id), str(member.id), "flower", flower)
        color = DWG_MINT if ok else DWG_PINK
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"{member.mention}: {msg}", color=color),
            ephemeral=True)

    @flower_group.command(name="remove", description="Remove a flower from any player's collection")
    @app_commands.describe(member="Target member", flower="Flower name")
    @app_commands.autocomplete(flower=flower_ac)
    async def admin_flower_remove(interaction: discord.Interaction,
                                  member: discord.Member, flower: str):
        if await reject_if_not_setup(interaction):  return
        if await reject_if_not_leader(interaction): return
        removed = remove_from_collection(
            str(interaction.guild_id), str(member.id), "flower", flower)
        if removed:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"🌿 Removed **{flower}** from {member.mention}'s collection.",
                    color=DWG_MINT,
                ), ephemeral=True)
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{member.mention} doesn't have **{flower}**.",
                    color=DWG_PINK,
                ), ephemeral=True)

    # ── vase subgroup ──────────────────────────────────────────────
    vase_group = app_commands.Group(
        name="vase", description="Override a player's vase collection", parent=admin)

    @vase_group.command(name="add", description="Add a vase to any player's collection")
    @app_commands.describe(member="Target member", vase="Vase name")
    @app_commands.autocomplete(vase=vase_ac)
    async def admin_vase_add(interaction: discord.Interaction,
                             member: discord.Member, vase: str):
        if await reject_if_not_setup(interaction):  return
        if await reject_if_not_leader(interaction): return
        ok, msg = add_to_collection(
            str(interaction.guild_id), str(member.id), "vase", vase)
        color = DWG_MINT if ok else DWG_PINK
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"{member.mention}: {msg}", color=color),
            ephemeral=True)

    @vase_group.command(name="remove", description="Remove a vase from any player's collection")
    @app_commands.describe(member="Target member", vase="Vase name")
    @app_commands.autocomplete(vase=vase_ac)
    async def admin_vase_remove(interaction: discord.Interaction,
                                member: discord.Member, vase: str):
        if await reject_if_not_setup(interaction):  return
        if await reject_if_not_leader(interaction): return
        removed = remove_from_collection(
            str(interaction.guild_id), str(member.id), "vase", vase)
        if removed:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"🏺 Removed **{vase}** from {member.mention}'s collection.",
                    color=DWG_MINT,
                ), ephemeral=True)
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{member.mention} doesn't have **{vase}**.",
                    color=DWG_PINK,
                ), ephemeral=True)

    # ── config subgroup ────────────────────────────────────────────
    config_group = app_commands.Group(
        name="config", description="Update server config", parent=admin)

    @config_group.command(name="logchannel",
                          description="Update the log channel")
    @app_commands.describe(channel="New log channel")
    async def config_logchannel(interaction: discord.Interaction,
                                channel: discord.TextChannel):
        if await reject_if_not_setup(interaction):  return
        if await reject_if_not_leader(interaction): return
        upsert_guild_config(str(interaction.guild_id),
                            log_channel_id=str(channel.id))
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"✅ Log channel updated to {channel.mention}.",
                color=DWG_MINT,
            ), ephemeral=True)

    @config_group.command(name="leaderroles",
                          description="Update the leader roles")
    @app_commands.describe(roles="Space-separated role mentions")
    async def config_leaderroles(interaction: discord.Interaction,
                                 roles: str):
        if await reject_if_not_setup(interaction):  return
        if await reject_if_not_leader(interaction): return
        # Parse role mentions from the string
        import re
        ids = re.findall(r"<@&(\d+)>", roles)
        if not ids:
            await interaction.response.send_message(
                "Please mention at least one role, e.g. `@Officer @Leader`.",
                ephemeral=True)
            return
        upsert_guild_config(str(interaction.guild_id),
                            leader_role_ids=json.dumps(ids))
        mentions = " ".join(f"<@&{i}>" for i in ids)
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"✅ Leader roles updated: {mentions}",
                color=DWG_MINT,
            ), ephemeral=True)

    tree.add_command(admin)
