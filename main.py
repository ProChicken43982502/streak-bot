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

# Track last person who ran /bump in each channel
last_bump_attempt = {}  # channel_id : user_id


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
# DETECT /bump USING on_interaction
# --------------------------------------------

@bot.event
async def on_interaction(interaction: discord.Interaction):
    # Detect if user ran Disboard's /bump
    if interaction.type == discord.InteractionType.application_command:
        cmd = interaction.data.get("name")

        if cmd == "bump":  # Disboard command
            last_bump_attempt[interaction.channel_id] = interaction.user.id
            # Debug log
            print(f"📌 Recorded bumper: {interaction.user} in channel {interaction.channel_id}")

    await bot.process_application_commands(interaction)

@bot.tree.command(name="bump", description="Detects when someone uses Disboard's /bump")
async def get_bump(interaction: discord.Interaction):
    await interaction.response.send_message(f"{interaction.user.mention}")

# --------------------------------------------
# DETECT DISBOARD EMBED IN on_message
# --------------------------------------------

DISBOARD_ID = 302050872383242240  # real bot ID
@bot.event
async def on_message(message):

    # Allow commands to work
    await bot.process_commands(message)

    # 1️⃣ Detect the user doing /bump
    if message.content.strip().lower() == "/bump":
        last_bump_attempt[message.channel.id] = message.author.id
        print(f"Recorded bumper: {message.author} in channel {message.channel.id}")
        return  # do not continue



    # 2️⃣ Only react to Disboard's bump confirmation
    if message.author.id != 302050872383242240:
        return

    await message.channel.send("Found Disboard")

    bump_success = False
    for embed in message.embeds:
        if embed.description and "bump done" in embed.description.lower():
            bump_success = True
            break

    if not bump_success:
        return

    await message.channel.send("Found Bump")

    # 3️⃣ Retrieve the bumper
    bumper_id = last_bump_attempt.get(message.channel.id)

    if not bumper_id:
        return await message.channel.send("❌ Could not determine who bumped.")

    bumper = message.guild.get_member(bumper_id)
    await message.channel.send(f"Found {bumper}")

    # ------------------------------------
    # UPDATE STREAK
    # ------------------------------------

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
        return await message.channel.send(
            f"🎉 {bumper.mention} bumped again today! Streak: **{user_data['bump_streak']} days**"
        )

    # continuing streak
    elif last_date == today - timedelta(days=1):
        user_data["bump_streak"] += 1

    # reset streak
    else:
        user_data["bump_streak"] = 1

    user_data["last_bump_date"] = today.isoformat()
    bump_data[user_id] = user_data
    save_data(bump_data)

    await update_roles(bumper, user_data["bump_streak"])

    await message.channel.send(
        f"🎉 {bumper.mention} bumped the server! Streak: **{user_data['bump_streak']} days!**"
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
            "You don't have a streak yet! Use `/bump` to start.",
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
