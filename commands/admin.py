"""
commands/admin.py
Dreamweaving Garden Bot — /admin command group (leader-only)

Panel-based architecture: 7 entry-point commands, each opens an ephemeral
View with buttons + dropdowns instead of dozens of flat subcommands.

  /admin members        — manage registered players
  /admin flowers        — override player flower lists
  /admin vases          — override player vase lists
  /admin contributions  — log credit, view leaderboard
  /admin league         — standings, locks, weekly reset
  /admin config         — update roles after setup
  /admin guide          — post the member-facing help guide

Visibility (per spec):
  PUBLIC results: add member, remove member, leaderboard, standings,
                  unlock player, remaining, reset week, guide post
  EPHEMERAL:      everything else (logging, member browsing, config tweaks,
                  flower/vase overrides, update ign)
"""

import datetime
import discord
from discord import app_commands

from db.queries import (
    register_player, remove_player, update_player_ign,
    get_all_players, find_player, find_player_by_ign,
    add_player_flower, remove_player_flower, get_player_flowers,
    add_player_vase,   remove_player_vase,   get_player_vases,
    find_flower_match, find_vase_match,
    get_flower_names_for_autocomplete, get_vase_names_for_autocomplete,
    log_contribution, get_guild_contribution_totals,
    log_league_entry, get_guild_league_standings,
    set_league_lock, get_guild_league_state, reset_league_week,
    get_all_flowers, get_all_vases,
)
from db.schema import upsert_guild_config, get_guild_config
from utils.guards import reject_if_not_setup, reject_if_not_leader

# ── Colors & footer ────────────────────────────────────────────────
DWG_PURPLE = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0xB8D9B0)
DWG_PINK   = discord.Color(0xF7CCD8)
DWG_BLUE   = discord.Color(0xB8D8F0)
DWG_YELLOW = discord.Color(0xF7C898)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"

PANEL_TIMEOUT = 600  # 10 minutes


# ════════════════════════════════════════════════════════════════════
# UTILITIES
# ════════════════════════════════════════════════════════════════════

def _current_week_start() -> str:
    today = datetime.datetime.utcnow().date()
    monday = today - datetime.timedelta(days=today.weekday())
    return monday.isoformat()


def _embed(title: str, desc: str = "", color: discord.Color = DWG_PURPLE) -> discord.Embed:
    e = discord.Embed(title=title, description=desc, color=color)
    e.set_footer(text=FOOTER)
    return e


def _chunk_lines(lines: list[str], max_chars: int = 3800) -> list[str]:
    """Split lines into chunks that fit in an embed description."""
    chunks, buf, length = [], [], 0
    for ln in lines:
        ln_len = len(ln) + 1
        if length + ln_len > max_chars and buf:
            chunks.append("\n".join(buf))
            buf, length = [], 0
        buf.append(ln)
        length += ln_len
    if buf:
        chunks.append("\n".join(buf))
    return chunks


async def _send_public(interaction: discord.Interaction, embed: discord.Embed) -> None:
    """Post a public message in the channel where the command was run."""
    try:
        await interaction.channel.send(embed=embed)
    except discord.Forbidden:
        # If we can't post publicly, fall back to ephemeral so the action isn't lost
        await interaction.followup.send(
            embed=_embed(
                "⚠️ Couldn't post publicly",
                f"The action succeeded but I don't have permission to post in {interaction.channel.mention}.",
                DWG_PINK,
            ),
            ephemeral=True,
        )


def _search_members(guild_id: str, query: str) -> list[dict]:
    """Find members by IGN or Discord name (case-insensitive substring). Sorted by IGN."""
    q = (query or "").strip().lower()
    if not q:
        return []
    all_members = get_all_players(guild_id)
    matches = [
        p for p in all_members
        if q in (p.get("ign") or "").lower()
        or q in (p.get("discord_name") or "").lower()
    ]
    matches.sort(key=lambda p: (p.get("ign") or "").lower())
    return matches


# ════════════════════════════════════════════════════════════════════
# GENERIC REUSABLE COMPONENTS
# ════════════════════════════════════════════════════════════════════

class ConfirmView(discord.ui.View):
    """Generic yes/no confirmation. Calls on_confirm coroutine on Confirm."""

    def __init__(self, on_confirm, danger_label: str = "Confirm"):
        super().__init__(timeout=PANEL_TIMEOUT)
        self.on_confirm = on_confirm
        self.confirm_btn.label = danger_label

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        self.stop()
        await self.on_confirm(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        self.stop()
        await interaction.response.edit_message(
            embed=_embed("Cancelled", "No changes made.", DWG_PINK),
            view=None,
        )


class MemberPickSelect(discord.ui.Select):
    """Dropdown of matching members. Calls on_pick(interaction, discord_id, ign) on selection."""

    def __init__(self, matches: list[dict], on_pick, placeholder: str = "Pick a member…"):
        self.on_pick = on_pick
        options = []
        for m in matches[:25]:
            label = (m.get("ign") or "Unknown")[:100]
            discord_name = m.get("discord_name") or ""
            desc = (f"Discord: {discord_name}" if discord_name else f"ID: {m['discord_id']}")[:100]
            options.append(discord.SelectOption(
                label=label,
                value=m["discord_id"],
                description=desc,
            ))
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        discord_id = self.values[0]
        ign = next(o.label for o in self.options if o.value == discord_id)
        await self.on_pick(interaction, discord_id, ign)


class MemberPickView(discord.ui.View):
    def __init__(self, matches: list[dict], on_pick, placeholder: str = "Pick a member…"):
        super().__init__(timeout=PANEL_TIMEOUT)
        self.add_item(MemberPickSelect(matches, on_pick, placeholder))


class MemberSearchModal(discord.ui.Modal):
    """Text input for member name, then shows disambiguation dropdown."""

    def __init__(self, on_pick, title: str = "Find Member"):
        super().__init__(title=title[:45])
        self.on_pick = on_pick
        self.query_input = discord.ui.TextInput(
            label="Type IGN or partial name",
            placeholder="e.g. alice",
            min_length=1, max_length=50, required=True,
        )
        self.add_item(self.query_input)

    async def on_submit(self, interaction: discord.Interaction):
        matches = _search_members(str(interaction.guild_id), self.query_input.value)
        if not matches:
            await interaction.response.send_message(
                embed=_embed(
                    "🔍 No matches",
                    f"No member found matching **{self.query_input.value}**. Try a different search.",
                    DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        # Always show a dropdown — even for 1 match — so the follow-up callback
        # runs from a select interaction, not a modal submit. (Modal submits
        # can't open another modal, which breaks flows like Update IGN that
        # need a second modal after picking the member.)
        title = (
            f"🔍 Found {len(matches)} matches"
            if len(matches) > 1 else
            "🔍 Found 1 match"
        )
        sub = (
            "Pick the right one from the list below."
            if len(matches) > 1 else
            "Confirm the member to continue."
        )
        if len(matches) > 25:
            sub += "\n_(Showing first 25 — refine your search if needed.)_"

        await interaction.response.send_message(
            embed=_embed(title, sub, DWG_PURPLE),
            view=MemberPickView(matches, self.on_pick),
            ephemeral=True,
        )


class ItemPickSelect(discord.ui.Select):
    """Generic dropdown for picking from a list of item names (flowers/vases)."""

    def __init__(self, names: list[str], on_pick, placeholder: str = "Pick one…"):
        self.on_pick = on_pick
        options = [
            discord.SelectOption(label=n[:100], value=n[:100])
            for n in names[:25]
        ]
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await self.on_pick(interaction, self.values[0])


class ItemPickView(discord.ui.View):
    def __init__(self, names: list[str], on_pick, placeholder: str = "Pick one…"):
        super().__init__(timeout=PANEL_TIMEOUT)
        self.add_item(ItemPickSelect(names, on_pick, placeholder))


class ItemSearchModal(discord.ui.Modal):
    """Search a master item list (flowers or vases). Shows dropdown if multi-match."""

    def __init__(self, names_provider, on_pick,
                 title: str = "Find item", label: str = "Type the name"):
        super().__init__(title=title[:45])
        self.names_provider = names_provider
        self.on_pick = on_pick
        self.query_input = discord.ui.TextInput(
            label=label[:45],
            placeholder="e.g. rose",
            min_length=1, max_length=80, required=True,
        )
        self.add_item(self.query_input)

    async def on_submit(self, interaction: discord.Interaction):
        q = self.query_input.value.strip().lower()
        names = self.names_provider()
        hits = [n for n in names if q in n.lower()]
        hits.sort(key=str.lower)

        if not hits:
            await interaction.response.send_message(
                embed=_embed("❌ No matches", f"Nothing matches **{self.query_input.value}**.", DWG_PINK),
                ephemeral=True,
            )
            return

        if len(hits) == 1:
            await self.on_pick(interaction, hits[0])
            return

        exact = next((n for n in hits if n.lower() == q), None)
        if exact:
            await self.on_pick(interaction, exact)
            return

        await interaction.response.send_message(
            embed=_embed(
                f"🔍 Found {len(hits)} matches",
                "Pick the right one."
                + ("\n_(Showing first 25 — refine your search if needed.)_" if len(hits) > 25 else ""),
                DWG_PURPLE,
            ),
            view=ItemPickView(hits, self.on_pick),
            ephemeral=True,
        )


# ════════════════════════════════════════════════════════════════════
# MEMBERS PANEL
# ════════════════════════════════════════════════════════════════════

class AddMemberModal(discord.ui.Modal, title="Add New Member"):
    discord_id_input = discord.ui.TextInput(
        label="Discord User ID",
        placeholder="Right-click user → Copy ID (Developer Mode on)",
        min_length=5, max_length=25, required=True,
    )
    ign_input = discord.ui.TextInput(
        label="In-Game Name",
        placeholder="Their exact in-game name",
        min_length=2, max_length=50, required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        did = self.discord_id_input.value.strip()
        ign = self.ign_input.value.strip()

        if not did.isdigit():
            await interaction.response.send_message(
                embed=_embed("❌ Invalid Discord ID", "Discord IDs are numeric — right-click a user and Copy ID.", DWG_PINK),
                ephemeral=True,
            )
            return

        member = interaction.guild.get_member(int(did))
        display = member.display_name if member else f"User {did}"

        ok = register_player(str(interaction.guild_id), did, display, ign)
        if not ok:
            await interaction.response.send_message(
                embed=_embed("📋 Already Registered", "That user is already in the roster.", DWG_PINK),
                ephemeral=True,
            )
            return

        # Best-effort role swap
        if member:
            cfg = get_guild_config(str(interaction.guild_id))
            if cfg:
                try:
                    new_role    = interaction.guild.get_role(int(cfg["new_role_id"]))    if cfg.get("new_role_id")    else None
                    member_role = interaction.guild.get_role(int(cfg["member_role_id"])) if cfg.get("member_role_id") else None
                    if new_role and new_role in member.roles:
                        await member.remove_roles(new_role, reason="Admin registration")
                    if member_role:
                        await member.add_roles(member_role, reason="Admin registration")
                except (discord.Forbidden, ValueError, TypeError):
                    pass

        await interaction.response.send_message(
            embed=_embed("✓ Done", f"Registered **{ign}**.", DWG_MINT),
            ephemeral=True,
        )

        # PUBLIC welcome
        mention = member.mention if member else f"<@{did}>"
        await _send_public(interaction, _embed(
            "🌱 New Member Registered",
            f"{mention} has been registered as **{ign}**. Welcome to the garden!",
            DWG_MINT,
        ))


class UpdateIGNModal(discord.ui.Modal, title="Update IGN"):
    def __init__(self, discord_id: str, current_ign: str):
        super().__init__()
        self.discord_id  = discord_id
        self.current_ign = current_ign
        self.new_ign_input = discord.ui.TextInput(
            label=f"New IGN for {current_ign[:30]}",
            placeholder="Their new in-game name",
            min_length=2, max_length=50, required=True,
        )
        self.add_item(self.new_ign_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_ign = self.new_ign_input.value.strip()
        ok = update_player_ign(str(interaction.guild_id), self.discord_id, new_ign)
        if not ok:
            await interaction.response.send_message(
                embed=_embed("❌ Update failed", "Member not found.", DWG_PINK),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=_embed("✏️ IGN Updated", f"**{self.current_ign}** → **{new_ign}**", DWG_MINT),
            ephemeral=True,
        )


class MembersPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT)

    @discord.ui.button(label="+ Add", style=discord.ButtonStyle.success, row=0)
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddMemberModal())

    @discord.ui.button(label="✕ Remove", style=discord.ButtonStyle.danger, row=0)
    async def remove_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async def after_pick(inter: discord.Interaction, discord_id: str, ign: str):
            async def do_remove(confirm_inter: discord.Interaction):
                ok = remove_player(str(confirm_inter.guild_id), discord_id)
                if not ok:
                    await confirm_inter.response.edit_message(
                        embed=_embed("❌ Remove failed", "Member not found.", DWG_PINK),
                        view=None,
                    )
                    return
                await confirm_inter.response.edit_message(
                    embed=_embed("✓ Removed", f"**{ign}** removed from the roster.", DWG_MINT),
                    view=None,
                )
                await _send_public(confirm_inter, _embed(
                    "🗑️ Member Removed",
                    f"**{ign}** has been removed from the guild roster.",
                    DWG_PINK,
                ))

            await inter.response.send_message(
                embed=_embed(
                    "⚠️ Confirm Remove",
                    f"Remove **{ign}** from the roster? This also clears their flower/vase collections.\n\n_This can't be undone._",
                    DWG_PINK,
                ),
                view=ConfirmView(do_remove, danger_label="Remove"),
                ephemeral=True,
            )

        await interaction.response.send_modal(
            MemberSearchModal(after_pick, title="Remove Member")
        )

    @discord.ui.button(label="✏️ Update IGN", style=discord.ButtonStyle.primary, row=0)
    async def update_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async def after_pick(inter: discord.Interaction, discord_id: str, ign: str):
            await inter.response.send_modal(UpdateIGNModal(discord_id, ign))

        await interaction.response.send_modal(
            MemberSearchModal(after_pick, title="Update Member IGN")
        )

    @discord.ui.button(label="📋 List All", style=discord.ButtonStyle.secondary, row=1)
    async def list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        players = get_all_players(str(interaction.guild_id))
        if not players:
            await interaction.response.send_message(
                embed=_embed("📋 Members", "No registered members yet.", DWG_PINK),
                ephemeral=True,
            )
            return

        players.sort(key=lambda p: (p.get("ign") or "").lower())
        lines = [f"• **{p['ign']}** — <@{p['discord_id']}>" for p in players]
        chunks = _chunk_lines(lines)
        first = _embed(f"📋 Registered Members ({len(players)})", chunks[0], DWG_BLUE)
        await interaction.response.send_message(embed=first, ephemeral=True)
        for c in chunks[1:]:
            await interaction.followup.send(embed=_embed("…continued", c, DWG_BLUE), ephemeral=True)


# ════════════════════════════════════════════════════════════════════
# FLOWERS / VASES PANELS (shared structure)
# ════════════════════════════════════════════════════════════════════

class _CollectionPanel(discord.ui.View):
    """Shared base for flower and vase override panels."""

    KIND        = "flower"
    KIND_TITLE  = "Flower"
    KIND_EMOJI  = "🌸"
    NAMES_FN    = staticmethod(get_flower_names_for_autocomplete)
    ADD_FN      = staticmethod(add_player_flower)
    REMOVE_FN   = staticmethod(remove_player_flower)
    GET_OWNED   = staticmethod(get_player_flowers)

    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT)

    @discord.ui.button(label="+ Add to player", style=discord.ButtonStyle.success, row=0)
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cls = self.__class__

        async def after_member_pick(inter: discord.Interaction, discord_id: str, ign: str):
            async def after_item_pick(item_inter: discord.Interaction, item_name: str):
                ok = cls.ADD_FN(
                    str(item_inter.guild_id), discord_id, item_name,
                    source_type="admin", logged_by=str(item_inter.user.id),
                )
                if not ok:
                    msg = f"**{ign}** already has **{item_name}**, or that {cls.KIND} doesn't exist."
                    await item_inter.response.send_message(
                        embed=_embed("⚠️ Not added", msg, DWG_PINK),
                        ephemeral=True,
                    )
                    return
                await item_inter.response.send_message(
                    embed=_embed(
                        f"{cls.KIND_EMOJI} Added",
                        f"Added **{item_name}** to **{ign}**'s collection.",
                        DWG_MINT,
                    ),
                    ephemeral=True,
                )

            await inter.response.send_modal(
                ItemSearchModal(
                    names_provider=cls.NAMES_FN,
                    on_pick=after_item_pick,
                    title=f"Add {cls.KIND_TITLE} to {ign[:20]}",
                    label=f"Type {cls.KIND_TITLE.lower()} name",
                )
            )

        await interaction.response.send_modal(
            MemberSearchModal(after_member_pick, title=f"Add {cls.KIND_TITLE} — pick member")
        )

    @discord.ui.button(label="✕ Remove from player", style=discord.ButtonStyle.danger, row=0)
    async def remove_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cls = self.__class__

        async def after_member_pick(inter: discord.Interaction, discord_id: str, ign: str):
            owned = cls.GET_OWNED(str(inter.guild_id), discord_id)
            if not owned:
                await inter.response.send_message(
                    embed=_embed(
                        f"{cls.KIND_EMOJI} Empty collection",
                        f"**{ign}** doesn't have any {cls.KIND}s tracked.",
                        DWG_PINK,
                    ),
                    ephemeral=True,
                )
                return

            async def after_item_pick(item_inter: discord.Interaction, item_name: str):
                async def do_remove(confirm_inter: discord.Interaction):
                    ok = cls.REMOVE_FN(str(confirm_inter.guild_id), discord_id, item_name)
                    if not ok:
                        await confirm_inter.response.edit_message(
                            embed=_embed("❌ Remove failed", f"They don't have **{item_name}**.", DWG_PINK),
                            view=None,
                        )
                        return
                    await confirm_inter.response.edit_message(
                        embed=_embed(
                            "🗑️ Removed",
                            f"Removed **{item_name}** from **{ign}**'s collection.",
                            DWG_MINT,
                        ),
                        view=None,
                    )

                await item_inter.response.send_message(
                    embed=_embed(
                        "⚠️ Confirm Remove",
                        f"Remove **{item_name}** from **{ign}**'s collection?",
                        DWG_PINK,
                    ),
                    view=ConfirmView(do_remove, danger_label="Remove"),
                    ephemeral=True,
                )

            if len(owned) <= 25:
                await inter.response.send_message(
                    embed=_embed(
                        f"{cls.KIND_EMOJI} {ign}'s {cls.KIND}s ({len(owned)})",
                        f"Pick which {cls.KIND} to remove.",
                        DWG_PURPLE,
                    ),
                    view=ItemPickView(owned, after_item_pick, placeholder=f"Pick a {cls.KIND}…"),
                    ephemeral=True,
                )
            else:
                def owned_names_provider():
                    return owned
                await inter.response.send_modal(
                    ItemSearchModal(
                        names_provider=owned_names_provider,
                        on_pick=after_item_pick,
                        title=f"Remove {cls.KIND_TITLE} — search",
                        label=f"Type {cls.KIND_TITLE.lower()} name",
                    )
                )

        await interaction.response.send_modal(
            MemberSearchModal(after_member_pick, title=f"Remove {cls.KIND_TITLE} — pick member")
        )


class FlowersPanel(_CollectionPanel):
    KIND        = "flower"
    KIND_TITLE  = "Flower"
    KIND_EMOJI  = "🌸"
    NAMES_FN    = staticmethod(get_flower_names_for_autocomplete)
    ADD_FN      = staticmethod(add_player_flower)
    REMOVE_FN   = staticmethod(remove_player_flower)
    GET_OWNED   = staticmethod(get_player_flowers)


class VasesPanel(_CollectionPanel):
    KIND        = "vase"
    KIND_TITLE  = "Vase"
    KIND_EMOJI  = "🏺"
    NAMES_FN    = staticmethod(get_vase_names_for_autocomplete)
    ADD_FN      = staticmethod(add_player_vase)
    REMOVE_FN   = staticmethod(remove_player_vase)
    GET_OWNED   = staticmethod(get_player_vases)


# ════════════════════════════════════════════════════════════════════
# CONTRIBUTIONS PANEL
# ════════════════════════════════════════════════════════════════════

class LogContributionModal(discord.ui.Modal, title="Log Contribution"):
    def __init__(self, discord_id: str, ign: str):
        super().__init__()
        self.discord_id = discord_id
        self.ign        = ign
        self.amount_input = discord.ui.TextInput(
            label=f"Amount for {ign[:30]}",
            placeholder="e.g. 5000",
            min_length=1, max_length=12, required=True,
        )
        self.note_input = discord.ui.TextInput(
            label="Note (optional)",
            placeholder="e.g. Weekly run",
            max_length=200, required=False,
            style=discord.TextStyle.short,
        )
        self.add_item(self.amount_input)
        self.add_item(self.note_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value.replace(",", "").strip())
        except ValueError:
            await interaction.response.send_message(
                embed=_embed("❌ Invalid amount", "Amount must be a whole number.", DWG_PINK),
                ephemeral=True,
            )
            return

        note = (self.note_input.value or "").strip() or None
        log_contribution(
            str(interaction.guild_id), self.discord_id, amount,
            contribution_date=datetime.datetime.utcnow().date().isoformat(),
            note=note, source_type="admin", logged_by=str(interaction.user.id),
        )

        desc = f"Logged **{amount:,}** for **{self.ign}**."
        if note:
            desc += f"\n_Note:_ {note}"
        await interaction.response.send_message(
            embed=_embed("💎 Contribution Logged", desc, DWG_MINT),
            ephemeral=True,
        )


class ContributionsPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT)

    @discord.ui.button(label="📝 Log", style=discord.ButtonStyle.primary, row=0)
    async def log_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async def after_pick(inter: discord.Interaction, discord_id: str, ign: str):
            await inter.response.send_modal(LogContributionModal(discord_id, ign))

        await interaction.response.send_modal(
            MemberSearchModal(after_pick, title="Log Contribution — pick member")
        )

    @discord.ui.button(label="🏆 Leaderboard", style=discord.ButtonStyle.secondary, row=0)
    async def leaderboard_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        rows = get_guild_contribution_totals(str(interaction.guild_id))
        if not rows:
            await interaction.response.send_message(
                embed=_embed("💎 Leaderboard", "No contributions logged yet.", DWG_PINK),
                ephemeral=True,
            )
            return

        lines = [
            f"`{i + 1:>3}.` **{r['ign']}** — {(r['total'] or 0):,}"
            for i, r in enumerate(rows)
        ]
        chunks = _chunk_lines(lines)
        await interaction.response.send_message(
            embed=_embed("✓", "Leaderboard posted in this channel.", DWG_MINT),
            ephemeral=True,
        )
        await _send_public(interaction, _embed(
            f"💎 Contribution Leaderboard ({len(rows)})",
            chunks[0], DWG_BLUE,
        ))
        for c in chunks[1:]:
            await _send_public(interaction, _embed("…continued", c, DWG_BLUE))


# ════════════════════════════════════════════════════════════════════
# LEAGUE PANEL
# ════════════════════════════════════════════════════════════════════

class LogLeagueModal(discord.ui.Modal, title="Log League Entry"):
    def __init__(self, discord_id: str, ign: str):
        super().__init__()
        self.discord_id = discord_id
        self.ign        = ign
        self.rank_input = discord.ui.TextInput(
            label=f"Rank for {ign[:30]}",
            placeholder="e.g. 3",
            min_length=1, max_length=6, required=True,
        )
        self.points_input = discord.ui.TextInput(
            label="Points",
            placeholder="e.g. 12000",
            min_length=1, max_length=12, required=True,
        )
        self.season_input = discord.ui.TextInput(
            label="Season (optional)",
            placeholder="e.g. S26-W21",
            max_length=30, required=False,
        )
        self.add_item(self.rank_input)
        self.add_item(self.points_input)
        self.add_item(self.season_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rank   = int(self.rank_input.value.replace(",", "").strip())
            points = int(self.points_input.value.replace(",", "").strip())
        except ValueError:
            await interaction.response.send_message(
                embed=_embed("❌ Invalid numbers", "Rank and points must be whole numbers.", DWG_PINK),
                ephemeral=True,
            )
            return

        season = (self.season_input.value or "").strip() or None
        log_league_entry(
            str(interaction.guild_id), self.discord_id,
            season=season, rank=rank, points=points,
            source_type="admin", logged_by=str(interaction.user.id),
        )

        desc = f"**{self.ign}** — Rank **{rank}**, **{points:,}** points"
        if season:
            desc += f" (season `{season}`)"
        await interaction.response.send_message(
            embed=_embed("📊 League Entry Logged", desc, DWG_MINT),
            ephemeral=True,
        )


class StandingsSeasonModal(discord.ui.Modal, title="View Standings"):
    season_input = discord.ui.TextInput(
        label="Season filter (leave blank for all)",
        placeholder="e.g. S26-W21",
        max_length=30, required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        season = (self.season_input.value or "").strip() or None
        rows = get_guild_league_standings(str(interaction.guild_id), season=season)
        if not rows:
            await interaction.response.send_message(
                embed=_embed("🏆 Standings", "No league entries logged yet.", DWG_PINK),
                ephemeral=True,
            )
            return

        lines = [
            f"`#{(r.get('rank') or 0):>3}` **{r['ign']}** — {(r.get('points') or 0):,}"
            for r in rows
        ]
        chunks = _chunk_lines(lines)
        title = "🏆 League Standings" + (f" · {season}" if season else "")

        await interaction.response.send_message(
            embed=_embed("✓", "Standings posted in this channel.", DWG_MINT),
            ephemeral=True,
        )
        await _send_public(interaction, _embed(title, chunks[0], DWG_YELLOW))
        for c in chunks[1:]:
            await _send_public(interaction, _embed("…continued", c, DWG_YELLOW))


class LeaguePanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT)

    @discord.ui.button(label="📝 Log entry", style=discord.ButtonStyle.primary, row=0)
    async def log_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async def after_pick(inter: discord.Interaction, discord_id: str, ign: str):
            await inter.response.send_modal(LogLeagueModal(discord_id, ign))

        await interaction.response.send_modal(
            MemberSearchModal(after_pick, title="Log League — pick member")
        )

    @discord.ui.button(label="🏆 Standings", style=discord.ButtonStyle.secondary, row=0)
    async def standings_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StandingsSeasonModal())

    @discord.ui.button(label="🔓 Unlock player", style=discord.ButtonStyle.primary, row=1)
    async def unlock_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        week = _current_week_start()
        state_rows = get_guild_league_state(str(interaction.guild_id), week)
        locked = [r for r in state_rows if r.get("is_locked")]
        if not locked:
            await interaction.response.send_message(
                embed=_embed(
                    "🔒 Nobody Locked",
                    f"No players are currently locked for week of **{week}**.",
                    DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        as_members = [
            {"discord_id": r["discord_id"], "ign": r["ign"], "discord_name": ""}
            for r in locked
        ]
        as_members.sort(key=lambda p: (p["ign"] or "").lower())

        async def after_pick(inter: discord.Interaction, discord_id: str, ign: str):
            async def do_unlock(confirm_inter: discord.Interaction):
                set_league_lock(str(confirm_inter.guild_id), discord_id, week, locked=False)
                await confirm_inter.response.edit_message(
                    embed=_embed("✓", f"Unlocked **{ign}**.", DWG_MINT),
                    view=None,
                )
                await _send_public(confirm_inter, _embed(
                    "🔓 Player Unlocked",
                    f"**{ign}** has been unlocked for week of **{week}** and can run again.",
                    DWG_MINT,
                ))

            await inter.response.send_message(
                embed=_embed(
                    "⚠️ Confirm Unlock",
                    f"Unlock **{ign}** for week of **{week}**?\n\nThey'll be able to run again.",
                    DWG_PURPLE,
                ),
                view=ConfirmView(do_unlock, danger_label="Unlock"),
                ephemeral=True,
            )

        if len(as_members) <= 25:
            await interaction.response.send_message(
                embed=_embed(
                    f"🔒 Locked This Week ({len(locked)})",
                    "Pick a player to unlock.",
                    DWG_PURPLE,
                ),
                view=MemberPickView(as_members, after_pick, placeholder="Pick a locked player…"),
                ephemeral=True,
            )
        else:
            await interaction.response.send_modal(
                MemberSearchModal(after_pick, title="Unlock — search locked players")
            )

    @discord.ui.button(label="⏳ Remaining", style=discord.ButtonStyle.secondary, row=1)
    async def remaining_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        week = _current_week_start()
        all_players = get_all_players(str(interaction.guild_id))
        state_rows  = get_guild_league_state(str(interaction.guild_id), week)
        locked_ids  = {r["discord_id"] for r in state_rows if r.get("is_locked")}
        remaining = [p for p in all_players if p["discord_id"] not in locked_ids]
        remaining.sort(key=lambda p: (p.get("ign") or "").lower())

        if not remaining:
            await interaction.response.send_message(
                embed=_embed("✓", "Posted to channel.", DWG_MINT),
                ephemeral=True,
            )
            await _send_public(interaction, _embed(
                "✅ All Locked In",
                f"Everyone has locked in for week of **{week}**! 🌟",
                DWG_MINT,
            ))
            return

        lines = [f"• **{p['ign']}** — <@{p['discord_id']}>" for p in remaining]
        chunks = _chunk_lines(lines)

        await interaction.response.send_message(
            embed=_embed("✓", "Posted to channel.", DWG_MINT),
            ephemeral=True,
        )
        await _send_public(interaction, _embed(
            f"⏳ Still Going ({len(remaining)})",
            chunks[0] + f"\n\n_Week of {week}_",
            DWG_PURPLE,
        ))
        for c in chunks[1:]:
            await _send_public(interaction, _embed("…continued", c, DWG_PURPLE))

    @discord.ui.button(label="🔄 Reset week", style=discord.ButtonStyle.danger, row=1)
    async def reset_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        week = _current_week_start()

        async def do_reset(confirm_inter: discord.Interaction):
            rows = reset_league_week(str(confirm_inter.guild_id), week)
            await confirm_inter.response.edit_message(
                embed=_embed("✓", f"Cleared {rows} lock entr{'y' if rows == 1 else 'ies'}.", DWG_MINT),
                view=None,
            )
            await _send_public(confirm_inter, _embed(
                "🔄 Week Reset",
                f"All locks for week of **{week}** have been cleared. The week is open again.",
                DWG_YELLOW,
            ))

        await interaction.response.send_message(
            embed=_embed(
                "⚠️ Confirm Reset",
                f"Clear all lock state for week of **{week}**?\n\n_This affects every locked player and can't be undone._",
                DWG_PINK,
            ),
            view=ConfirmView(do_reset, danger_label="Reset"),
            ephemeral=True,
        )


# ════════════════════════════════════════════════════════════════════
# CONFIG PANEL
# ════════════════════════════════════════════════════════════════════

class _LeaderRolesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT)

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Select leader role(s) — up to 5",
        min_values=1, max_values=5,
    )
    async def pick(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        ids = [str(r.id) for r in select.values]
        upsert_guild_config(str(interaction.guild_id), leader_role_ids=ids)
        mentions = " ".join(r.mention for r in select.values)
        await interaction.response.edit_message(
            embed=_embed("⚙️ Leader Roles Updated", f"Leader access: {mentions}", DWG_MINT),
            view=None,
        )


class _SingleRoleView(discord.ui.View):
    def __init__(self, field: str, label: str):
        super().__init__(timeout=PANEL_TIMEOUT)
        self.field = field
        self.label = label

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Select a role",
        min_values=1, max_values=1,
    )
    async def pick(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role = select.values[0]
        upsert_guild_config(str(interaction.guild_id), **{self.field: str(role.id)})
        await interaction.response.edit_message(
            embed=_embed(
                f"⚙️ {self.label} Updated",
                f"{self.label} set to {role.mention}.",
                DWG_MINT,
            ),
            view=None,
        )


class ConfigPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT)

    @discord.ui.button(label="👑 Leader roles", style=discord.ButtonStyle.primary, row=0)
    async def leaders_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_embed("👑 Leader Roles", "Pick the role(s) that should have `/admin` access.", DWG_PURPLE),
            view=_LeaderRolesView(),
            ephemeral=True,
        )

    @discord.ui.button(label="🌱 New role", style=discord.ButtonStyle.secondary, row=0)
    async def newrole_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_embed("🌱 New Role", "Pick the role given to players before `/register`.", DWG_PURPLE),
            view=_SingleRoleView("new_role_id", "New Role"),
            ephemeral=True,
        )

    @discord.ui.button(label="🌷 Member role", style=discord.ButtonStyle.secondary, row=0)
    async def memberrole_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_embed("🌷 Member Role", "Pick the role assigned after `/register`.", DWG_PURPLE),
            view=_SingleRoleView("member_role_id", "Member Role"),
            ephemeral=True,
        )


# ════════════════════════════════════════════════════════════════════
# GUIDE PANEL
# ════════════════════════════════════════════════════════════════════

def _guide_embeds() -> list[discord.Embed]:
    welcome = _embed(
        "🌸 Welcome to Dreamweaving Garden",
        (
            "A friendly guild bot for tracking flowers, vases, league, and contributions.\n\n"
            "**First step for everyone:** run `/register` and enter your in-game name.\n\n"
            "Below you'll find a quick guide for each command group. "
            "Use `/help` anytime for a private copy of these embeds."
        ),
        DWG_PURPLE,
    )

    my_embed = _embed(
        "🌷 /my — your personal collection",
        (
            "**Everyone** — track your flowers and vases.\n\n"
            "• `/my flowers` — see your flowers\n"
            "• `/my vases` — see your vases\n"
            "• `/my add flower [name]` — add a flower (autocomplete)\n"
            "• `/my add vase [name]` — add a vase\n"
            "• `/my remove flower [name]` — remove one\n"
            "• `/my remove vase [name]` — remove one\n"
            "• `/my missing flowers` — what you still need\n"
            "• `/my missing vases` — what you still need"
        ),
        DWG_PINK,
    )

    lookup_embed = _embed(
        "🔍 /lookup — find things in the guild",
        (
            "**Everyone** — see who has what.\n\n"
            "• `/lookup flower [name]` — who has this flower\n"
            "• `/lookup vase [name]` — who has this vase\n"
            "• `/lookup missing flowers` — flowers nobody has\n"
            "• `/lookup missing vases` — vases nobody has"
        ),
        DWG_BLUE,
    )

    league_embed = _embed(
        "🌟 /league — weekly league",
        (
            "**Everyone** — coordinate your weekly runs.\n\n"
            "• `/league call` — rally the guild that league is starting\n"
            "• `/league lock` — mark yourself done for the week\n"
            "• `/league preview` — see who's locked in this week"
        ),
        DWG_YELLOW,
    )

    admin_embed = _embed(
        "⚙️ /admin — leaders only",
        (
            "**Leader role required.** Each command opens an interactive panel.\n\n"
            "• `/admin members` — add, remove, update IGN, list\n"
            "• `/admin flowers` — override player flowers\n"
            "• `/admin vases` — override player vases\n"
            "• `/admin contributions` — log credit + leaderboard\n"
            "• `/admin league` — log entries, standings, locks, reset\n"
            "• `/admin config` — update roles after setup\n"
            "• `/admin guide` — re-post this guide"
        ),
        DWG_MINT,
    )

    return [welcome, my_embed, lookup_embed, league_embed, admin_embed]


class _GuideChannelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Pick the channel to post the guide in…",
        min_values=1, max_values=1,
    )
    async def pick(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        channel = interaction.guild.get_channel(select.values[0].id)
        if not channel:
            await interaction.response.edit_message(
                embed=_embed("❌ Channel not found", "Try again.", DWG_PINK), view=None,
            )
            return

        await interaction.response.defer(ephemeral=True)

        embeds = _guide_embeds()
        try:
            for em in embeds:
                await channel.send(embed=em)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=_embed(
                    "❌ Permission Denied",
                    f"I don't have permission to post in {channel.mention}. "
                    "Bot needs **View Channel**, **Send Messages**, and **Embed Links**.",
                    DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=_embed(
                "📖 Guide Posted",
                f"Posted {len(embeds)} embeds in {channel.mention}.\n\n"
                "_Tip: pin them or use a read-only channel so they stay visible._",
                DWG_MINT,
            ),
            ephemeral=True,
        )


class GuidePanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=PANEL_TIMEOUT)

    @discord.ui.button(label="📖 Post guide", style=discord.ButtonStyle.primary, row=0)
    async def post_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_embed(
                "📖 Post Guide — pick channel",
                "Pick the channel where the 5 guide embeds should be posted.",
                DWG_PURPLE,
            ),
            view=_GuideChannelView(),
            ephemeral=True,
        )


# ════════════════════════════════════════════════════════════════════
# COMMAND REGISTRATION
# ════════════════════════════════════════════════════════════════════

def register_admin(tree: app_commands.CommandTree) -> None:
    admin = app_commands.Group(name="admin", description="Leader-only management commands")

    @admin.command(name="members", description="Manage registered members")
    async def cmd_members(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return
        count = len(get_all_players(str(interaction.guild_id)))
        await interaction.response.send_message(
            embed=_embed(
                "👥 Members",
                f"**{count}** registered member{'s' if count != 1 else ''}.\n\nPick an action below:",
                DWG_PINK,
            ),
            view=MembersPanel(),
            ephemeral=True,
        )

    @admin.command(name="flowers", description="Override player flower collections")
    async def cmd_flowers(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return
        await interaction.response.send_message(
            embed=_embed(
                "🌸 Flowers",
                "Add or remove a flower from any member's collection.",
                DWG_PINK,
            ),
            view=FlowersPanel(),
            ephemeral=True,
        )

    @admin.command(name="vases", description="Override player vase collections")
    async def cmd_vases(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return
        await interaction.response.send_message(
            embed=_embed(
                "🏺 Vases",
                "Add or remove a vase from any member's collection.",
                DWG_BLUE,
            ),
            view=VasesPanel(),
            ephemeral=True,
        )

    @admin.command(name="contributions", description="Log credit and view the leaderboard")
    async def cmd_contributions(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return
        await interaction.response.send_message(
            embed=_embed(
                "💎 Contributions",
                "Log an amount for a member or view the leaderboard.",
                DWG_YELLOW,
            ),
            view=ContributionsPanel(),
            ephemeral=True,
        )

    @admin.command(name="league", description="Log entries, view standings, manage locks")
    async def cmd_league(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return
        week = _current_week_start()
        await interaction.response.send_message(
            embed=_embed(
                "🌟 League",
                f"Week of **{week}**. Pick an action below.",
                DWG_PURPLE,
            ),
            view=LeaguePanel(),
            ephemeral=True,
        )

    @admin.command(name="config", description="Update role configuration")
    async def cmd_config(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return

        cfg = get_guild_config(str(interaction.guild_id)) or {}
        import json as _json
        try:
            leader_ids = _json.loads(cfg.get("leader_role_ids") or "[]")
        except Exception:
            leader_ids = []

        leader_str = " ".join(f"<@&{r}>" for r in leader_ids) if leader_ids else "_not set_"
        new_str    = f"<@&{cfg['new_role_id']}>"    if cfg.get("new_role_id")    else "_not set_"
        mem_str    = f"<@&{cfg['member_role_id']}>" if cfg.get("member_role_id") else "_not set_"

        await interaction.response.send_message(
            embed=_embed(
                "⚙️ Configuration",
                (
                    "**Current settings:**\n"
                    f"👑 Leader roles: {leader_str}\n"
                    f"🌱 New role: {new_str}\n"
                    f"🌷 Member role: {mem_str}\n\n"
                    "Pick what you'd like to update:"
                ),
                DWG_PURPLE,
            ),
            view=ConfigPanel(),
            ephemeral=True,
        )

    @admin.command(name="guide", description="Post the member-facing help guide")
    async def cmd_guide(interaction: discord.Interaction):
        if await reject_if_not_setup(interaction): return
        if await reject_if_not_leader(interaction): return
        await interaction.response.send_message(
            embed=_embed(
                "📖 Guide",
                "Post the 5-embed member guide to a channel of your choice.",
                DWG_MINT,
            ),
            view=GuidePanel(),
            ephemeral=True,
        )

    tree.add_command(admin)
