"""
commands/admin.py
Dreamweaving Garden Bot — /admin command group (leader-only)
Everything that isn't for regular members.

Subgroups & subcommands:
  /admin member add | remove | updateign | list
  /admin flower add | remove                 (override any player's flowers)
  /admin vase   add | remove                 (override any player's vases)
  /admin contribution log | leaderboard
  /admin league log | standings | unlock | remaining | resetweek
  /admin config leaderroles | newrole | memberrole
  /admin guide post [channel]
"""

import datetime
import discord
from discord import app_commands
from db.queries import (
    register_player, remove_player, update_player_ign, get_all_players, find_player, find_player_by_ign,
    add_player_flower, remove_player_flower,
    add_player_vase,   remove_player_vase,
    find_flower_match, find_vase_match,
    get_flower_names_for_autocomplete, get_vase_names_for_autocomplete,
    log_contribution, get_guild_contribution_totals,
    log_league_entry, get_guild_league_standings,
    set_league_lock, get_guild_league_state, reset_league_week,
)
from db.schema import upsert_guild_config, get_guild_config
from utils.guards import reject_if_not_setup, reject_if_not_leader

DWG_PURPLE = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0xB8D9B0)
DWG_PINK   = discord.Color(0xF7CCD8)
DWG_BLUE   = discord.Color(0xB8D8F0)
DWG_YELLOW = discord.Color(0xF7C898)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"


# ------------------------------------------------------------------
# AUTOCOMPLETES
# ------------------------------------------------------------------

async def flower_name_autocomplete(
    interaction: discord.Interaction, current: str,
) -> list[app_commands.Choice[str]]:
    names = get_flower_names_for_autocomplete()
    q = (current or "").lower()
    return [app_commands.Choice(name=n, value=n) for n in names if q in n.lower()][:25]


async def vase_name_autocomplete(
    interaction: discord.Interaction, current: str,
) -> list[app_commands.Choice[str]]:
    names = get_vase_names_for_autocomplete()
    q = (current or "").lower()
    return [app_commands.Choice(name=n, value=n) for n in names if q in n.lower()][:25]


def _current_week_start() -> str:
    today = datetime.datetime.utcnow().date()
    monday = today - datetime.timedelta(days=today.weekday())
    return monday.isoformat()


def _resolve_target(interaction: discord.Interaction,
                    member: discord.Member | None, ign: str | None) -> dict | None:
    """Find a player row by Discord member OR by IGN. Returns dict or None."""
    if member:
        return find_player(str(interaction.guild_id), str(member.id))
    if ign:
        return find_player_by_ign(str(interaction.guild_id), ign)
    return None


# ------------------------------------------------------------------
# GUIDE EMBEDS — posted by /admin guide post
# ------------------------------------------------------------------

def _guide_embeds() -> list[discord.Embed]:
    welcome = discord.Embed(
        title="🌸 Welcome to Dreamweaving Garden",
        description=(
            "A friendly guild bot for tracking flowers, vases, league, and contributions.\n\n"
            "**First step for everyone:** run `/register` and enter your in-game name. "
            "That swaps your role and unlocks the rest of the bot.\n\n"
            "Below you'll find a quick guide for each command group. "
            "Use `/help` anytime for a private version of this."
        ),
        color=DWG_PURPLE,
    )
    welcome.set_footer(text=FOOTER)

    my_embed = discord.Embed(
        title="🌷 /my — your personal collection",
        description=(
            "**Everyone** — track what flowers and vases you've got.\n\n"
            "• `/my flowers` — see your flower collection\n"
            "• `/my vases` — see your vase collection\n"
            "• `/my add flower [name]` — add a flower (autocomplete works)\n"
            "• `/my add vase [name]` — add a vase\n"
            "• `/my remove flower [name]` — remove one\n"
            "• `/my remove vase [name]` — remove one\n"
            "• `/my missing flowers` — what flowers you still need\n"
            "• `/my missing vases` — what vases you still need"
        ),
        color=DWG_PINK,
    )
    my_embed.set_footer(text=FOOTER)

    lookup_embed = discord.Embed(
        title="🔍 /lookup — find things across the guild",
        description=(
            "**Everyone** — see who has what, and what's missing entirely.\n\n"
            "• `/lookup flower [name]` — who has this flower\n"
            "• `/lookup vase [name]` — who has this vase\n"
            "• `/lookup missing flowers` — flowers nobody in the guild has\n"
            "• `/lookup missing vases` — vases nobody in the guild has"
        ),
        color=DWG_BLUE,
    )
    lookup_embed.set_footer(text=FOOTER)

    league_embed = discord.Embed(
        title="🌟 /league — weekly league",
        description=(
            "**Everyone** — coordinate your weekly runs.\n\n"
            "• `/league call` — rally the guild that league is starting\n"
            "• `/league lock` — mark yourself done for the week\n"
            "• `/league preview` — see who's locked in this week"
        ),
        color=DWG_YELLOW,
    )
    league_embed.set_footer(text=FOOTER)

    admin_embed = discord.Embed(
        title="⚙️ /admin — leaders only",
        description=(
            "**Leader role required** — everything operational lives here.\n\n"
            "**Members:** `/admin member add|remove|updateign|list`\n"
            "**Overrides:** `/admin flower add|remove`, `/admin vase add|remove`\n"
            "**Contributions:** `/admin contribution log`, `/admin contribution leaderboard`\n"
            "**League ops:** `/admin league log|standings|unlock|remaining|resetweek`\n"
            "**Config:** `/admin config leaderroles|newrole|memberrole`\n"
            "**Guide:** `/admin guide post [channel]` — re-post this guide"
        ),
        color=DWG_MINT,
    )
    admin_embed.set_footer(text=FOOTER)

    return [welcome, my_embed, lookup_embed, league_embed, admin_embed]


# ------------------------------------------------------------------
# REGISTRATION
# ------------------------------------------------------------------

def register_admin(tree: app_commands.CommandTree) -> None:

    admin    = app_commands.Group(name="admin", description="Leader-only management commands")
    member_g = app_commands.Group(name="member",       description="Manage registered members",        parent=admin)
    flower_g = app_commands.Group(name="flower",       description="Override player flower lists",      parent=admin)
    vase_g   = app_commands.Group(name="vase",         description="Override player vase lists",        parent=admin)
    contrib  = app_commands.Group(name="contribution", description="Log and view contributions",        parent=admin)
    league_g = app_commands.Group(name="league",       description="League management operations",      parent=admin)
    config_g = app_commands.Group(name="config",       description="Update server configuration",       parent=admin)
    guide_g  = app_commands.Group(name="guide",        description="Post the bot guide to a channel",   parent=admin)

    # ────────────────────────────────────────────────────────────────
    # MEMBER GROUP
    # ────────────────────────────────────────────────────────────────

    @member_g.command(name="add", description="Register a player on their behalf")
    @app_commands.describe(member="Discord member to register", ign="Their in-game name")
    async def admin_member_add(interaction: discord.Interaction,
                               member: discord.Member, ign: str):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        ok = register_player(
            str(interaction.guild_id), str(member.id),
            member.display_name, ign.strip(),
        )
        if not ok:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{member.mention} is already registered.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        # Best-effort role swap if config is present
        cfg = get_guild_config(str(interaction.guild_id))
        if cfg:
            try:
                new_role    = interaction.guild.get_role(int(cfg.get("new_role_id")))    if cfg.get("new_role_id")    else None
                member_role = interaction.guild.get_role(int(cfg.get("member_role_id"))) if cfg.get("member_role_id") else None
                if new_role and new_role in member.roles:
                    await member.remove_roles(new_role, reason="Admin registration")
                if member_role:
                    await member.add_roles(member_role, reason="Admin registration")
            except (discord.Forbidden, ValueError, TypeError):
                pass

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🌱 Member Registered",
                description=f"{member.mention} registered as **{ign.strip()}**.",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    @member_g.command(name="remove", description="Remove a registered member from the guild roster")
    @app_commands.describe(member="The member to remove")
    async def admin_member_remove(interaction: discord.Interaction, member: discord.Member):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        ok = remove_player(str(interaction.guild_id), str(member.id))
        if not ok:
            await interaction.response.send_message(
                embed=discord.Embed(description=f"{member.mention} isn't registered.", color=DWG_PINK),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🗑️ Member Removed",
                description=f"{member.mention} has been removed from the guild roster.",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    @member_g.command(name="updateign", description="Update a member's in-game name")
    @app_commands.describe(member="The member to update", new_ign="Their new in-game name")
    async def admin_member_updateign(interaction: discord.Interaction,
                                     member: discord.Member, new_ign: str):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        ok = update_player_ign(str(interaction.guild_id), str(member.id), new_ign.strip())
        if not ok:
            await interaction.response.send_message(
                embed=discord.Embed(description=f"{member.mention} isn't registered.", color=DWG_PINK),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                title="✏️ IGN Updated",
                description=f"{member.mention} is now **{new_ign.strip()}**.",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    @member_g.command(name="list", description="List every registered member in the guild")
    async def admin_member_list(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        players = get_all_players(str(interaction.guild_id))
        if not players:
            await interaction.response.send_message(
                embed=discord.Embed(description="No registered members yet.", color=DWG_PINK),
                ephemeral=True,
            )
            return

        lines = [f"• **{p['ign']}** — <@{p['discord_id']}>" for p in players[:50]]
        body  = "\n".join(lines)
        if len(players) > 50:
            body += f"\n\n_… and {len(players) - 50} more._"
        embed = discord.Embed(
            title=f"📋 Registered Members  ({len(players)})",
            description=body,
            color=DWG_BLUE,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ────────────────────────────────────────────────────────────────
    # FLOWER OVERRIDE GROUP
    # ────────────────────────────────────────────────────────────────

    @flower_g.command(name="add", description="Add a flower to a member's collection")
    @app_commands.describe(member="The member", name="Flower name")
    @app_commands.autocomplete(name=flower_name_autocomplete)
    async def admin_flower_add(interaction: discord.Interaction,
                               member: discord.Member, name: str):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        if not find_player(str(interaction.guild_id), str(member.id)):
            await interaction.response.send_message(
                embed=discord.Embed(description=f"{member.mention} isn't registered yet.", color=DWG_PINK),
                ephemeral=True,
            )
            return

        matched = find_flower_match(name)
        if not matched:
            await interaction.response.send_message(
                embed=discord.Embed(description=f"❌ No flower matches **{name}**.", color=DWG_PINK),
                ephemeral=True,
            )
            return

        ok = add_player_flower(
            str(interaction.guild_id), str(member.id), matched,
            source_type="admin", logged_by=str(interaction.user.id),
        )
        if not ok:
            await interaction.response.send_message(
                embed=discord.Embed(description=f"{member.mention} already has **{matched}**.", color=DWG_PINK),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🌸 Flower Added",
                description=f"Added **{matched}** to {member.mention}'s collection.",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    @flower_g.command(name="remove", description="Remove a flower from a member's collection")
    @app_commands.describe(member="The member", name="Flower name")
    @app_commands.autocomplete(name=flower_name_autocomplete)
    async def admin_flower_remove(interaction: discord.Interaction,
                                  member: discord.Member, name: str):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        matched = find_flower_match(name) or name
        ok = remove_player_flower(str(interaction.guild_id), str(member.id), matched)
        if not ok:
            await interaction.response.send_message(
                embed=discord.Embed(description=f"{member.mention} doesn't have **{matched}**.", color=DWG_PINK),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🗑️ Flower Removed",
                description=f"Removed **{matched}** from {member.mention}'s collection.",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    # ────────────────────────────────────────────────────────────────
    # VASE OVERRIDE GROUP
    # ────────────────────────────────────────────────────────────────

    @vase_g.command(name="add", description="Add a vase to a member's collection")
    @app_commands.describe(member="The member", name="Vase name")
    @app_commands.autocomplete(name=vase_name_autocomplete)
    async def admin_vase_add(interaction: discord.Interaction,
                             member: discord.Member, name: str):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        if not find_player(str(interaction.guild_id), str(member.id)):
            await interaction.response.send_message(
                embed=discord.Embed(description=f"{member.mention} isn't registered yet.", color=DWG_PINK),
                ephemeral=True,
            )
            return

        matched = find_vase_match(name)
        if not matched:
            await interaction.response.send_message(
                embed=discord.Embed(description=f"❌ No vase matches **{name}**.", color=DWG_PINK),
                ephemeral=True,
            )
            return

        ok = add_player_vase(
            str(interaction.guild_id), str(member.id), matched,
            source_type="admin", logged_by=str(interaction.user.id),
        )
        if not ok:
            await interaction.response.send_message(
                embed=discord.Embed(description=f"{member.mention} already has **{matched}**.", color=DWG_PINK),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🏺 Vase Added",
                description=f"Added **{matched}** to {member.mention}'s collection.",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    @vase_g.command(name="remove", description="Remove a vase from a member's collection")
    @app_commands.describe(member="The member", name="Vase name")
    @app_commands.autocomplete(name=vase_name_autocomplete)
    async def admin_vase_remove(interaction: discord.Interaction,
                                member: discord.Member, name: str):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        matched = find_vase_match(name) or name
        ok = remove_player_vase(str(interaction.guild_id), str(member.id), matched)
        if not ok:
            await interaction.response.send_message(
                embed=discord.Embed(description=f"{member.mention} doesn't have **{matched}**.", color=DWG_PINK),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🗑️ Vase Removed",
                description=f"Removed **{matched}** from {member.mention}'s collection.",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    # ────────────────────────────────────────────────────────────────
    # CONTRIBUTION GROUP
    # ────────────────────────────────────────────────────────────────

    @contrib.command(name="log", description="Record a contribution for a member")
    @app_commands.describe(
        member="The member", amount="Contribution amount", note="Optional note",
    )
    async def admin_contrib_log(interaction: discord.Interaction,
                                member: discord.Member, amount: int, note: str = None):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        if not find_player(str(interaction.guild_id), str(member.id)):
            await interaction.response.send_message(
                embed=discord.Embed(description=f"{member.mention} isn't registered yet.", color=DWG_PINK),
                ephemeral=True,
            )
            return

        log_contribution(
            str(interaction.guild_id), str(member.id), amount,
            contribution_date=datetime.datetime.utcnow().date().isoformat(),
            note=note, source_type="admin", logged_by=str(interaction.user.id),
        )
        desc = f"Logged **{amount}** for {member.mention}."
        if note:
            desc += f"\n_Note:_ {note}"
        await interaction.response.send_message(
            embed=discord.Embed(title="💎 Contribution Logged", description=desc, color=DWG_MINT),
            ephemeral=True,
        )

    @contrib.command(name="leaderboard", description="Show total contributions per member")
    async def admin_contrib_leaderboard(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        rows = get_guild_contribution_totals(str(interaction.guild_id))
        if not rows:
            await interaction.response.send_message(
                embed=discord.Embed(description="No contributions logged yet.", color=DWG_PINK),
                ephemeral=True,
            )
            return

        lines = [f"`{i + 1:2d}.` **{r['ign']}** — {r['total']:,}" for i, r in enumerate(rows[:25])]
        embed = discord.Embed(
            title="💎 Contribution Leaderboard",
            description="\n".join(lines),
            color=DWG_BLUE,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ────────────────────────────────────────────────────────────────
    # LEAGUE GROUP
    # ────────────────────────────────────────────────────────────────

    @league_g.command(name="log", description="Record a league standing for a member")
    @app_commands.describe(member="The member", rank="Rank", points="Points", season="Season identifier (optional)")
    async def admin_league_log(interaction: discord.Interaction,
                               member: discord.Member, rank: int, points: int,
                               season: str = None):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        if not find_player(str(interaction.guild_id), str(member.id)):
            await interaction.response.send_message(
                embed=discord.Embed(description=f"{member.mention} isn't registered yet.", color=DWG_PINK),
                ephemeral=True,
            )
            return

        log_league_entry(
            str(interaction.guild_id), str(member.id),
            season=season, rank=rank, points=points,
            source_type="admin", logged_by=str(interaction.user.id),
        )
        await interaction.response.send_message(
            embed=discord.Embed(
                title="📊 League Entry Logged",
                description=(
                    f"**{member.mention}** — Rank **{rank}**, **{points:,}** points"
                    + (f" (season `{season}`)" if season else "")
                ),
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    @league_g.command(name="standings", description="Show the league standings")
    @app_commands.describe(season="Filter by season (optional)")
    async def admin_league_standings(interaction: discord.Interaction, season: str = None):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        rows = get_guild_league_standings(str(interaction.guild_id), season=season)
        if not rows:
            await interaction.response.send_message(
                embed=discord.Embed(description="No league entries logged yet.", color=DWG_PINK),
                ephemeral=True,
            )
            return

        lines = [
            f"`#{r['rank']:>3}` **{r['ign']}** — {r['points']:,}"
            for r in rows[:25]
        ]
        title = "🏆 League Standings"
        if season:
            title += f"  ·  {season}"
        embed = discord.Embed(title=title, description="\n".join(lines), color=DWG_YELLOW)
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @league_g.command(name="unlock", description="Unlock a player for the current week")
    @app_commands.describe(member="The member to unlock")
    async def admin_league_unlock(interaction: discord.Interaction, member: discord.Member):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        week = _current_week_start()
        set_league_lock(
            str(interaction.guild_id), str(member.id), week, locked=False,
        )
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🔓 Player Unlocked",
                description=f"{member.mention} unlocked for week of **{week}**.",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    @league_g.command(name="remaining", description="See who hasn't locked in this week")
    async def admin_league_remaining(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        week = _current_week_start()
        all_players = get_all_players(str(interaction.guild_id))
        state_rows  = get_guild_league_state(str(interaction.guild_id), week)
        locked_ids  = {r["discord_id"] for r in state_rows if r.get("is_locked")}

        remaining = [p for p in all_players if p["discord_id"] not in locked_ids]
        if not remaining:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="✅ All Locked In",
                    description=f"Everyone has locked in for week of **{week}**.",
                    color=DWG_MINT,
                ),
                ephemeral=True,
            )
            return

        lines = [f"• **{p['ign']}** — <@{p['discord_id']}>" for p in remaining[:25]]
        if len(remaining) > 25:
            lines.append(f"_… and {len(remaining) - 25} more._")
        embed = discord.Embed(
            title=f"⏳ Still Going  ({len(remaining)})",
            description="\n".join(lines) + f"\n\n_Week of {week}_",
            color=DWG_PURPLE,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @league_g.command(name="resetweek", description="Wipe all lock state for the current week")
    async def admin_league_resetweek(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        week = _current_week_start()
        rows = reset_league_week(str(interaction.guild_id), week)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🔄 Week Reset",
                description=f"Cleared **{rows}** lock entr{'y' if rows == 1 else 'ies'} for week of **{week}**.",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    # ────────────────────────────────────────────────────────────────
    # CONFIG GROUP
    # ────────────────────────────────────────────────────────────────

    @config_g.command(name="leaderroles", description="Update which roles have leader access")
    @app_commands.describe(
        role1="A leader role", role2="Optional 2nd role", role3="Optional 3rd role",
        role4="Optional 4th role", role5="Optional 5th role",
    )
    async def admin_config_leaderroles(interaction: discord.Interaction,
                                       role1: discord.Role,
                                       role2: discord.Role = None,
                                       role3: discord.Role = None,
                                       role4: discord.Role = None,
                                       role5: discord.Role = None):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        roles = [r for r in (role1, role2, role3, role4, role5) if r]
        upsert_guild_config(
            str(interaction.guild_id),
            leader_role_ids=[str(r.id) for r in roles],
        )
        mentions = " ".join(r.mention for r in roles)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚙️ Leader Roles Updated",
                description=f"Leader access: {mentions}",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    @config_g.command(name="newrole", description="Update the 'New' role (given before /register)")
    @app_commands.describe(role="The new 'New' role")
    async def admin_config_newrole(interaction: discord.Interaction, role: discord.Role):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        upsert_guild_config(str(interaction.guild_id), new_role_id=str(role.id))
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚙️ New Role Updated",
                description=f"New-player role set to {role.mention}.",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    @config_g.command(name="memberrole", description="Update the 'Member' role (assigned after /register)")
    @app_commands.describe(role="The new 'Member' role")
    async def admin_config_memberrole(interaction: discord.Interaction, role: discord.Role):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        upsert_guild_config(str(interaction.guild_id), member_role_id=str(role.id))
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚙️ Member Role Updated",
                description=f"Registered-member role set to {role.mention}.",
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    # ────────────────────────────────────────────────────────────────
    # GUIDE GROUP
    # ────────────────────────────────────────────────────────────────

    @guide_g.command(name="post", description="Post the bot guide as a series of embeds in a channel")
    @app_commands.describe(channel="Channel to post the guide in")
    async def admin_guide_post(interaction: discord.Interaction,
                               channel: discord.TextChannel):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        # Defer because sending 5 embeds takes a moment and we may hit rate limits
        await interaction.response.defer(ephemeral=True)

        embeds = _guide_embeds()
        try:
            for em in embeds:
                await channel.send(embed=em)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ I don't have permission to post in {channel.mention}.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=discord.Embed(
                title="📖 Guide Posted",
                description=(
                    f"Posted {len(embeds)} guide embeds in {channel.mention}.\n\n"
                    "_Tip: pin them or use a read-only channel so they stay visible._"
                ),
                color=DWG_MINT,
            ),
            ephemeral=True,
        )

    tree.add_command(admin)
