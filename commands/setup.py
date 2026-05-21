"""
commands/setup.py
Dreamweaving Garden Bot — /setup wizard
Two-step server configuration. Must be completed before other commands work.
Only server administrators can run this.
"""

import discord
from discord import app_commands
from db.schema import upsert_guild_config, get_guild_config, is_setup_complete

# Pastel DWG color palette
DWG_PURPLE = discord.Color(0xF0A8C0)
DWG_MINT   = discord.Color(0xB8D9B0)
DWG_PINK   = discord.Color(0xF7CCD8)
DWG_YELLOW = discord.Color(0xF7C898)
DWG_BLUE   = discord.Color(0xB8D8F0)


def setup_embed(title: str, description: str, step: int, total: int,
                color: discord.Color = DWG_PURPLE) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=f"Dreamweaving Garden Setup  •  Step {step} of {total}")
    return embed


# ------------------------------------------------------------------
# STEP 2 — Pick leader role(s)
# ------------------------------------------------------------------

class SetupStep2View(discord.ui.View):
    """Step 2 — Pick leader role(s)."""

    def __init__(self, guild_id: str, new_role_id: int, member_role_id: int):
        super().__init__(timeout=300)
        self.guild_id       = guild_id
        self.new_role_id    = new_role_id
        self.member_role_id = member_role_id

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Select leader role(s) — pick up to 5...",
        min_values=1,
        max_values=5,
    )
    async def pick_leader_roles(self, interaction: discord.Interaction,
                                select: discord.ui.RoleSelect):
        leader_role_ids = [role.id for role in select.values]

        # Persist everything to DB
        upsert_guild_config(
            self.guild_id,
            guild_name      = interaction.guild.name,
            new_role_id     = str(self.new_role_id),
            member_role_id  = str(self.member_role_id),
            leader_role_ids = [str(r) for r in leader_role_ids],
        )

        leader_mentions = " ".join(f"<@&{r}>" for r in leader_role_ids)
        embed = setup_embed(
            "✅  Setup Complete!",
            (
                f"**Dreamweaving Garden** is ready to go in **{interaction.guild.name}**.\n\n"
                f"**New member role:** <@&{self.new_role_id}>\n"
                f"**Member role:** <@&{self.member_role_id}>\n"
                f"**Leader role(s):** {leader_mentions}\n\n"
                "Players can now run `/register` to join.\n"
                "Leaders can manage everything via `/admin`.\n\n"
                "💡 **Tip:** Run `/admin guide post` in any channel to drop a "
                "help guide for your members."
            ),
            step=2, total=2,
            color=DWG_MINT,
        )
        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)


# ------------------------------------------------------------------
# STEP 1 — Pick the New and Member roles
# ------------------------------------------------------------------

class SetupStep1View(discord.ui.View):
    """Step 1 — Pick the New and Member roles."""

    def __init__(self, guild_id: str):
        super().__init__(timeout=300)
        self.guild_id    = guild_id
        self.new_role_id = None

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Select the 'New' role (given to players before registration)...",
        min_values=1,
        max_values=1,
        row=0,
    )
    async def pick_new_role(self, interaction: discord.Interaction,
                            select: discord.ui.RoleSelect):
        self.new_role_id = select.values[0].id
        await interaction.response.defer()

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Select the 'Member' role (given after /register)...",
        min_values=1,
        max_values=1,
        row=1,
    )
    async def pick_member_role(self, interaction: discord.Interaction,
                               select: discord.ui.RoleSelect):
        if not self.new_role_id:
            await interaction.response.send_message(
                "⚠️ Please select the **New** role first, then the Member role.",
                ephemeral=True,
            )
            return

        member_role_id = select.values[0].id
        if member_role_id == self.new_role_id:
            await interaction.response.send_message(
                "⚠️ The **New** and **Member** roles must be different.",
                ephemeral=True,
            )
            return

        embed = setup_embed(
            "⚙️  Step 2 of 2 — Leader Roles",
            (
                f"**New role:** <@&{self.new_role_id}>\n"
                f"**Member role:** <@&{member_role_id}>\n\n"
                "Now select the role(s) that should have **leader access**.\n"
                "Leaders can manage members, flowers, vases, league, and contributions.\n\n"
                "You can select **up to 5 roles** — for example both "
                "`Leader` and `Co-Leader`."
            ),
            step=2, total=2,
            color=DWG_YELLOW,
        )
        view = SetupStep2View(self.guild_id, self.new_role_id, member_role_id)
        self.stop()
        await interaction.response.edit_message(embed=embed, view=view)


# ------------------------------------------------------------------
# /setup COMMAND
# ------------------------------------------------------------------

def register_setup(tree: app_commands.CommandTree) -> None:

    @tree.command(
        name="setup",
        description="Configure Dreamweaving Garden for this server (admin only)",
    )
    async def setup(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command must be used inside a server.", ephemeral=True
            )
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🔒 Admin Only",
                    description="Only server administrators can run `/setup`.",
                    color=DWG_PINK,
                ),
                ephemeral=True,
            )
            return

        guild_id = str(interaction.guild_id)
        already_done = is_setup_complete(guild_id)
        intro_extra  = (
            "\n\n⚠️ **This server is already configured.** "
            "Running setup again will overwrite your current settings."
            if already_done else ""
        )

        embed = setup_embed(
            "⚙️  Dreamweaving Garden Setup  —  Step 1 of 2",
            (
                "Welcome! Let's get this server configured.\n"
                "This will only take a minute.\n\n"
                "**What you'll set up:**\n"
                "• The role new players receive when they join\n"
                "• The role players receive after running `/register`\n"
                "• Which role(s) have leader permissions\n\n"
                "**Step 1:** Select the **New** role and the **Member** role below."
                + intro_extra
            ),
            step=1, total=2,
            color=DWG_PURPLE,
        )

        view = SetupStep1View(guild_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
