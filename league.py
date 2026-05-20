"""
commands/setup.py
Dreamweaving Garden Bot — /setup command
3-step wizard: roles → leader roles → log channel.
Stores results in guild_config via upsert_guild_config().
"""

import json
import discord
from discord import app_commands
from db.queries import get_guild_config, upsert_guild_config

DWG_PINK   = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0x9ECFA8)
DWG_PURPLE = discord.Color(0xD0AEE8)
FOOTER     = "Dreamweaving Garden • Grow together, bloom brighter"


def _step_embed(title: str, description: str, step: int, total: int,
                color=DWG_PURPLE) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=f"Step {step}/{total} — {FOOTER}")
    return embed


# ── Step 1 — Seedling + Member roles ──────────────────────────────

class SetupStep1View(discord.ui.View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.seedling_role: discord.Role | None = None
        self.member_role:   discord.Role | None = None

    @discord.ui.role_select(placeholder="Select the Seedling role (new joiners)…", row=0)
    async def seedling_select(self, interaction: discord.Interaction,
                              select: discord.ui.RoleSelect):
        self.seedling_role = select.values[0]
        await interaction.response.defer()

    @discord.ui.role_select(placeholder="Select the Member role (after /register)…", row=1)
    async def member_select(self, interaction: discord.Interaction,
                            select: discord.ui.RoleSelect):
        self.member_role = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Next →", style=discord.ButtonStyle.primary, row=2)
    async def next_btn(self, interaction: discord.Interaction, _):
        if not self.seedling_role or not self.member_role:
            await interaction.response.send_message(
                "Please select both the Seedling and Member roles first.", ephemeral=True)
            return
        upsert_guild_config(
            self.guild_id,
            seedling_role_id=str(self.seedling_role.id),
            member_role_id=str(self.member_role.id),
        )
        view = SetupStep2View(self.guild_id)
        await interaction.response.edit_message(
            embed=_step_embed(
                "⚙️ Step 2 — Leader Roles",
                "Select one or more roles that grant leader permissions "
                "(e.g. guild master, officer).",
                step=2, total=3,
            ),
            view=view,
        )


# ── Step 2 — Leader roles ──────────────────────────────────────────

class SetupStep2View(discord.ui.View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.leader_roles: list[discord.Role] = []

    @discord.ui.role_select(placeholder="Select leader role(s)…",
                            min_values=1, max_values=5, row=0)
    async def leader_select(self, interaction: discord.Interaction,
                             select: discord.ui.RoleSelect):
        self.leader_roles = list(select.values)
        await interaction.response.defer()

    @discord.ui.button(label="Next →", style=discord.ButtonStyle.primary, row=1)
    async def next_btn(self, interaction: discord.Interaction, _):
        if not self.leader_roles:
            await interaction.response.send_message(
                "Please select at least one leader role.", ephemeral=True)
            return
        upsert_guild_config(
            self.guild_id,
            leader_role_ids=json.dumps([str(r.id) for r in self.leader_roles]),
        )
        view = SetupStep3View(self.guild_id)
        await interaction.response.edit_message(
            embed=_step_embed(
                "⚙️ Step 3 — Log Channel",
                "Select the channel where flower/vase/contribution logs will be posted publicly.",
                step=3, total=3,
            ),
            view=view,
        )


# ── Step 3 — Log channel ───────────────────────────────────────────

class SetupStep3View(discord.ui.View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.log_channel: discord.TextChannel | None = None

    @discord.ui.channel_select(
        placeholder="Select the log channel…",
        channel_types=[discord.ChannelType.text],
        row=0,
    )
    async def channel_select(self, interaction: discord.Interaction,
                              select: discord.ui.ChannelSelect):
        self.log_channel = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Finish ✦", style=discord.ButtonStyle.success, row=1)
    async def finish_btn(self, interaction: discord.Interaction, _):
        if not self.log_channel:
            await interaction.response.send_message(
                "Please select a log channel first.", ephemeral=True)
            return
        upsert_guild_config(
            self.guild_id,
            log_channel_id=str(self.log_channel.id),
        )
        cfg = get_guild_config(self.guild_id)
        guild = interaction.guild
        seedling = guild.get_role(int(cfg["seedling_role_id"])) if cfg.get("seedling_role_id") else None
        member   = guild.get_role(int(cfg["member_role_id"]))   if cfg.get("member_role_id")   else None

        embed = discord.Embed(
            title="✅ Setup Complete!",
            description=(
                f"**Seedling role:** {seedling.mention if seedling else '—'}\n"
                f"**Member role:** {member.mention if member else '—'}\n"
                f"**Log channel:** {self.log_channel.mention}\n\n"
                "Players can now run `/register` to join the garden. 🌸"
            ),
            color=DWG_MINT,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.edit_message(embed=embed, view=None)


# ── Command registration ───────────────────────────────────────────

def register_setup(tree: app_commands.CommandTree) -> None:
    @tree.command(name="setup", description="Configure the bot for this server (admin only)")
    @app_commands.default_permissions(administrator=True)
    async def setup(interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        cfg      = get_guild_config(guild_id)

        intro_extra = ""
        if cfg:
            intro_extra = "\n\n⚠️ **This server is already configured.** Running setup again will overwrite existing settings."

        embed = _step_embed(
            "⚙️ Step 1 — Roles",
            (
                "Welcome! Let's get this server configured.\n\n"
                "**Step 1:** Select the **Seedling** role (assigned to new joiners automatically) "
                "and the **Member** role (assigned after `/register`)."
                + intro_extra
            ),
            step=1, total=3,
        )
        await interaction.response.send_message(
            embed=embed, view=SetupStep1View(guild_id), ephemeral=True)
