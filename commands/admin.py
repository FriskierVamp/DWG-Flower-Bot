"""
commands/admin.py
Dreamweaving Garden Bot — /admin command group
Leader and admin only. Member management, flower overrides, config updates.
"""

import json
import discord
from discord import app_commands
from db.queries import (
    find_player, find_player_by_ign, register_player, remove_player,
    get_all_players, get_player_flowers, add_player_flower,
    remove_player_flower, find_flower_match, get_flower_names_for_autocomplete,
    set_league_lock,
)
from db.schema import upsert_guild_config, get_guild_config
from utils.guards import (
    reject_if_not_setup, reject_if_not_leader, reject_if_not_in_server,
)

DWG_PURPLE = discord.Color(0xC9A0FF)
DWG_MINT   = discord.Color(0xB8F2D0)
DWG_PINK   = discord.Color(0xFFB3C1)
DWG_GOLD   = discord.Color(0xF4D58D)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"


def register_admin(tree: app_commands.CommandTree) -> None:

    admin = app_commands.Group(
        name="admin",
        description="Leader and admin management commands",
    )

    # ── MEMBER SUBGROUP ────────────────────────────────────────────

    member_group = app_commands.Group(
        name="member",
        description="Manage guild member registrations",
        parent=admin,
    )

    @member_group.command(
        name="add",
        description="Manually register a member (leader only)",
    )
    @app_commands.describe(
        member="Discord member to register",
        ign="Their in-game name",
    )
    async def admin_member_add(
        interaction: discord.Interaction,
        member: discord.Member,
        ign: str,
    ):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_leader(interaction):
            return

        guild_id = str(interaction.guild_id)
        existing = find_player(guild_id, str(member.id))
        if existing:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Already Registered",
                    description=f"{member.mention} is already registered as **{existing['ign']}**.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        success = register_player(guild_id, str(member.id), member.display_name, ign.strip())
        if not success:
            await interaction.response.send_message(
                "⚠️ Registration failed — player may already exist.", ephemeral=True
            )
            return

        # Role swap
        cfg = get_guild_config(guild_id)
        swap_note = ""
        if cfg:
            try:
                new_role_id    = cfg.get("new_role_id")
                member_role_id = cfg.get("member_role_id")
                new_role    = interaction.guild.get_role(int(new_role_id))    if new_role_id    else None
                member_role = interaction.guild.get_role(int(member_role_id)) if member_role_id else None
                if new_role and new_role in member.roles:
                    await member.remove_roles(new_role, reason="Admin registration")
                if member_role:
                    await member.add_roles(member_role, reason="Admin registration")
                swap_note = f"\nRole updated to <@&{member_role_id}>."
            except Exception as e:
                swap_note = f"\n⚠️ Role swap failed: {e}"

        await interaction.response.send_message(
            embed=discord.Embed(
                title="✅ Member Registered",
                description=f"{member.mention} registered as **{ign}**.{swap_note}",
                color=DWG_MINT,
            ).set_footer(text=FOOTER),
            ephemeral=True,
        )

    @member_group.command(
        name="remove",
        description="Remove a member's registration (leader only)",
    )
    @app_commands.describe(member="Discord member to remove")
    async def admin_member_remove(
        interaction: discord.Interaction, member: discord.Member
    ):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_leader(interaction):
            return

        guild_id = str(interaction.guild_id)
        removed  = remove_player(guild_id, str(member.id))
        if not removed:
            await interaction.response.send_message(
                f"{member.mention} isn't registered.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🗑️ Member Removed",
                description=f"{member.mention} has been removed from the registry.",
                color=DWG_PURPLE,
            ).set_footer(text=FOOTER),
            ephemeral=True,
        )

    @member_group.command(
        name="updateign",
        description="Update a member's in-game name (leader only)",
    )
    @app_commands.describe(
        member="Discord member",
        new_ign="Their new in-game name",
    )
    async def admin_member_updateign(
        interaction: discord.Interaction,
        member: discord.Member,
        new_ign: str,
    ):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_leader(interaction):
            return

        guild_id = str(interaction.guild_id)
        existing = find_player(guild_id, str(member.id))
        if not existing:
            await interaction.response.send_message(
                f"{member.mention} isn't registered.", ephemeral=True
            )
            return

        from db.schema import get_db
        with get_db() as conn:
            conn.execute(
                "UPDATE players SET ign = ?, discord_name = ? WHERE guild_id = ? AND discord_id = ?",
                (new_ign.strip(), member.display_name, guild_id, str(member.id)),
            )

        await interaction.response.send_message(
            embed=discord.Embed(
                title="✏️ IGN Updated",
                description=f"{member.mention} IGN changed from **{existing['ign']}** → **{new_ign}**.",
                color=DWG_MINT,
            ).set_footer(text=FOOTER),
            ephemeral=True,
        )

    @member_group.command(
        name="list",
        description="List all registered members (leader only)",
    )
    async def admin_member_list(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_leader(interaction):
            return

        players = get_all_players(str(interaction.guild_id))
        if not players:
            await interaction.response.send_message(
                "No members registered yet.", ephemeral=True
            )
            return

        lines = [
            f"**{p['ign']}** — <@{p['discord_id']}> *(registered {p['registered_at'][:10]})*"
            for p in players
        ]
        # Chunk if needed
        chunks = [lines[i:i+20] for i in range(0, len(lines), 20)]
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"👥 Registered Members ({len(players)})" if i == 0 else f"(continued)",
                description="\n".join(chunk),
                color=DWG_PURPLE,
            )
            embed.set_footer(text=FOOTER)
            if i == 0:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)

    # ── FLOWER SUBGROUP ────────────────────────────────────────────

    flower_group = app_commands.Group(
        name="flower",
        description="Manage flowers on a player's profile",
        parent=admin,
    )

    async def flower_autocomplete(
        interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        names = get_flower_names_for_autocomplete()
        return [
            app_commands.Choice(name=n, value=n)
            for n in names if current.lower() in n.lower()
        ][:25]

    @flower_group.command(
        name="add",
        description="Add a flower to a player's profile (leader only)",
    )
    @app_commands.describe(member="The player", flower="The flower to add")
    @app_commands.autocomplete(flower=flower_autocomplete)
    async def admin_flower_add(
        interaction: discord.Interaction,
        member: discord.Member,
        flower: str,
    ):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_leader(interaction):
            return

        guild_id = str(interaction.guild_id)
        player   = find_player(guild_id, str(member.id))
        if not player:
            await interaction.response.send_message(
                f"{member.mention} isn't registered.", ephemeral=True
            )
            return

        matched = find_flower_match(flower)
        if not matched:
            await interaction.response.send_message(
                f"❌ **{flower}** not found in the master list.", ephemeral=True
            )
            return

        added = add_player_flower(
            guild_id, str(member.id), matched,
            source_type="manual",
            logged_by=str(interaction.user.id),
        )

        msg = (
            f"✅ **{matched}** added to **{player['ign']}**'s profile."
            if added else
            f"**{matched}** was already in **{player['ign']}**'s profile."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @flower_group.command(
        name="remove",
        description="Remove a flower from a player's profile (leader only)",
    )
    @app_commands.describe(member="The player", flower="The flower to remove")
    @app_commands.autocomplete(flower=flower_autocomplete)
    async def admin_flower_remove(
        interaction: discord.Interaction,
        member: discord.Member,
        flower: str,
    ):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_leader(interaction):
            return

        guild_id = str(interaction.guild_id)
        player   = find_player(guild_id, str(member.id))
        if not player:
            await interaction.response.send_message(
                f"{member.mention} isn't registered.", ephemeral=True
            )
            return

        matched = find_flower_match(flower)
        if not matched:
            await interaction.response.send_message(
                f"❌ **{flower}** not found in the master list.", ephemeral=True
            )
            return

        removed = remove_player_flower(guild_id, str(member.id), matched)
        msg = (
            f"✅ **{matched}** removed from **{player['ign']}**'s profile."
            if removed else
            f"**{matched}** wasn't in **{player['ign']}**'s profile."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    # ── LEAGUE SUBGROUP ────────────────────────────────────────────

    league_group = app_commands.Group(
        name="league",
        description="Manage league state for the guild",
        parent=admin,
    )

    @league_group.command(
        name="resetweek",
        description="Reset all league locks for the current week (leader only)",
    )
    async def admin_league_resetweek(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction):
            return
        if await reject_if_not_leader(interaction):
            return

        import datetime
        today  = datetime.date.today()
        monday = today - datetime.timedelta(days=today.weekday())
        week   = monday.isoformat()

        guild_id = str(interaction.guild_id)
        players  = get_all_players(guild_id)

        from db.schema import get_db
        with get_db() as conn:
            conn.execute(
                "DELETE FROM league_state WHERE guild_id = ? AND week_start = ?",
                (guild_id, week),
            )

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🔄 Week Reset",
                description=f"All league locks cleared for week of **{week}**. {len(players)} players reset.",
                color=DWG_PURPLE,
            ).set_footer(text=FOOTER),
            ephemeral=True,
        )

    # ── CONFIG SUBGROUP ────────────────────────────────────────────

    config_group = app_commands.Group(
        name="config",
        description="Update server configuration (admin only)",
        parent=admin,
    )

    @config_group.command(
        name="logchannel",
        description="Update the log channel (admin only)",
    )
    @app_commands.describe(channel="The new log channel")
    async def admin_config_logchannel(
        interaction: discord.Interaction, channel: discord.TextChannel
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "🔒 Only server admins can change config.", ephemeral=True
            )
            return

        upsert_guild_config(str(interaction.guild_id), log_channel_id=str(channel.id))
        await interaction.response.send_message(
            f"✅ Log channel updated to {channel.mention}.", ephemeral=True
        )

    @config_group.command(
        name="leaderroles",
        description="Update which roles have leader access (admin only)",
    )
    async def admin_config_leaderroles(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "🔒 Only server admins can change config.", ephemeral=True
            )
            return

        class LeaderRoleView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=120)

            @discord.ui.select(
                cls=discord.ui.RoleSelect,
                placeholder="Select leader role(s)...",
                min_values=1,
                max_values=5,
            )
            async def pick_roles(self, inner: discord.Interaction, select: discord.ui.RoleSelect):
                ids = [str(r.id) for r in select.values]
                upsert_guild_config(str(inner.guild_id), leader_role_ids=ids)
                mentions = " ".join(f"<@&{i}>" for i in ids)
                await inner.response.edit_message(
                    content=f"✅ Leader roles updated to: {mentions}",
                    view=None,
                )

        await interaction.response.send_message(
            "Select the role(s) that should have leader access:",
            view=LeaderRoleView(),
            ephemeral=True,
        )

    tree.add_command(admin)
