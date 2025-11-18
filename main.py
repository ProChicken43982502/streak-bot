import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
import json
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = os.path.join(os.getcwd(), "bump_data.json")

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

bump_data = load_data()

# --------------------------------------------
# ROLE UPDATE FUNCTION
# --------------------------------------------

async def update_roles(member, streak):
    if not member or not member.guild:
        return

    guild = member.guild
    super_role = discord.utils.get(guild.roles, name="Super Bumper")
    master_role = discord.utils.get(guild.roles, name="Master Bumper")

    if streak >= 25 and master_role:
        if super_role in member.roles:
            await member.remove_roles(super_role)
        if master_role not in member.roles:
            await member.add_roles(master_role)

    elif streak >= 10 and super_role:
        if super_role not in member.roles:
            await member.add_roles(super_role)

# --------------------------------------------
# BOT READY
# --------------------------------------------

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {bot.user}")
    print("Slash commands synced.")

# --------------------------------------------
# NEW SYSTEM: DETECT BUMP-BOT CONFIRMATION
# --------------------------------------------

BUMP_BOT_ID = 735147814878969968

@bot.event
async def on_message(message: discord.Message):

    # Make sure slash commands still work
    await bot.process_commands(message)

    # Only listen to bump-bot messages
    if message.author.id != BUMP_BOT_ID:
        return

    # Detect the confirmation message
    if "Thx for bumping our Server!" not in message.content:
        return

    # Extract the mentioned bumper
    if len(message.mentions) == 0:
        await message.channel.send("❌ Could not find the user who bumped.")
        return

    bumper = message.mentions[0]

    # --------------------------------------------
    # UPDATE STREAK
    # --------------------------------------------

    user_id = str(bumper.id)
    today = datetime.utcnow().date()

    user_data = bump_data.get(user_id, {"bump_streak": 0, "last_bump_date": None})
    last_date = (
        datetime.fromisoformat(user_data["last_bump_date"]).date()
        if user_data["last_bump_date"]
        else None
    )

    # same day bump
    if last_date == today:
        await message.channel.send(
            f"🎉 {bumper.mention} bumped again today! "
            f"Streak: **{user_data['bump_streak']} days**"
        )
        return

    # continuing streak
    elif last_date == today - timedelta(days=1):
        user_data["bump_streak"] += 1

    # streak reset
    else:
        user_data["bump_streak"] = 1

    user_data["last_bump_date"] = today.isoformat()
    bump_data[user_id] = user_data
    save_data(bump_data)

    await update_roles(bumper, user_data["bump_streak"])

    await message.channel.send(
        f"🔥 {bumper.mention}'s Streak is now *{user_data['bump_streak']} days!*"
    )

# --------------------------------------------
# ADMIN: /editstreak
# --------------------------------------------

@tree.command(name="editstreak", description="[ADMIN] Adjust a user's bump streak.")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(
    member="User to modify.",
    days="Number of days.",
    operation_add="True = add, False = subtract."
)
async def editstreak_cmd(interaction: discord.Interaction, member: discord.Member, days: int, operation_add: bool):

    user_id = str(member.id)
    today = datetime.utcnow().date()

    user_data = bump_data.get(user_id, {"bump_streak": 0, "last_bump_date": None})
    user_data["last_bump_date"] = today.isoformat()

    if operation_add:
        user_data["bump_streak"] += days
        msg = f"Added **{days} days**"
    else:
        user_data["bump_streak"] = max(0, user_data["bump_streak"] - days)
        msg = f"Subtracted **{days} days**"

    bump_data[user_id] = user_data
    save_data(bump_data)

    await update_roles(member, user_data["bump_streak"])

    await interaction.response.send_message(
        f"✅ {msg} for {member.mention}. New streak: **{user_data['bump_streak']} days**",
        ephemeral=True
    )

@editstreak_cmd.error
async def editstreak_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        return await interaction.response.send_message(
            "❌ You need **Manage Server** permission.",
            ephemeral=True
        )
    raise error

# --------------------------------------------
# USER: /bumpstreak
# --------------------------------------------

@tree.command(name="bumpstreak", description="Check your bump streak.")
async def bumpstreak_cmd(interaction: discord.Interaction):

    user_id = str(interaction.user.id)

    if user_id not in bump_data:
        return await interaction.response.send_message(
            "You don't have a streak yet!",
            ephemeral=True
        )

    streak = bump_data[user_id]["bump_streak"]

    await interaction.response.send_message(
        f"🔥 {interaction.user.display_name}, your streak is **{streak} days!**"
    )

# --------------------------------------------
# USER: /bumpleaderboard
# --------------------------------------------

@tree.command(name="bumpleaderboard", description="Top 5 bump streaks.")
async def bumpleaderboard_cmd(interaction: discord.Interaction):

    if not bump_data:
        return await interaction.response.send_message("Nobody has a streak yet!")

    top = sorted(
        bump_data.items(),
        key=lambda x: x[1]["bump_streak"],
        reverse=True
    )[:5]

    msg = "🏆 **Top 5 Bump Streaks**:\n\n"

    for i, (uid, info) in enumerate(top, start=1):
        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else f"Unknown ({uid})"
        msg += f"**{i}. {name} — {info['bump_streak']} days**\n"

    await interaction.response.send_message(msg)

# --------------------------------------------
# RUN BOT
# --------------------------------------------

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable not set.")

bot.run(DISCORD_TOKEN)
