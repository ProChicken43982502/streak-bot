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

# Use an environment variable for the token (so you never commit it)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Make a safe DATA_FILE path (so it works on Railway)
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

# Helper function to apply role rewards
async def update_roles(member, streak):
    if not member or not member.guild:
        return

    guild = member.guild
    super_role = discord.utils.get(guild.roles, name="Super Bumper")
    master_role = discord.utils.get(guild.roles, name="Master Bumper")

    # Check for Master Bumper first (higher requirement)
    if streak >= 25 and master_role:
        # Add Master role and remove Super role if present
        if super_role in member.roles and super_role:
            await member.remove_roles(super_role)
        if master_role not in member.roles:
            await member.add_roles(master_role)
    # Check for Super Bumper second
    elif streak >= 10 and super_role:
        if super_role not in member.roles:
            await member.add_roles(super_role)


# ----------------------
# Bot Ready
# ----------------------

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {bot.user}")
    print("Slash commands synced.")

# ----------------------
# Detect Disboard bump success
# ----------------------

last_bump_attempt = {}  # channel_id : user_id

@bot.event
async def on_message(message):

    # Detect when someone uses /bump
    if message.interaction:
        if message.interaction.name == "bump":
            last_bump_attempt[message.channel.id] = message.author.id

    await bot.process_commands(message)

@bot.event
async def on_message(message):

    # allow prefix and slash commands to work
    await bot.process_commands(message)

    # Only listen to Disboard bot (real bot ID)
    if message.author.id != 302050872383242240:
        return

    await message.channel.send(
        f"Found Disboard"
    )
    
    # Detect bump success from embed text
    bump_success = False

    for embed in message.embeds:
        if embed.description and "bump done" in embed.description.lower():
            bump_success = True
            break

    if not bump_success:
        return

    await message.channel.send(
        f"Found Bump"
    )
    
    # Identify the bumper using mentions
    channel_id = message.channel.id
    bumper_id = last_bump_attempt.get(channel_id)
    bumper = message.guild.get_member(bumper_id)

    user_id = str(bumper.id)
    today = datetime.utcnow().date()

    user_data = bump_data.get(user_id, {"bump_streak": 0, "last_bump_date": None})

    await message.channel.send(
        f"Found {bumper}"
    )
    
    last_date = None
    if user_data["last_bump_date"]:
        last_date = datetime.fromisoformat(user_data["last_bump_date"]).date()

    # Update streak
    if last_date == today:
        await message.channel.send(
        f"🎉 {bumper.mention} bumped the server again! Current streak: **{user_data['bump_streak']} days!**"
    )
        return  # already bumped today

    elif last_date == today - timedelta(days=1):
        user_data["bump_streak"] += 1
    else:
        user_data["bump_streak"] = 1

    user_data["last_bump_date"] = today.isoformat()
    bump_data[user_id] = user_data
    save_data(bump_data)

    # Update roles
    await update_roles(bumper, user_data["bump_streak"])

    # Announce
    await message.channel.send(
        f"🎉 {bumper.mention} bumped the server! Current streak: **{user_data['bump_streak']} days!**"
    )

# ----------------------
# /addstreak (ADMIN COMMAND - NEW)
# ----------------------
@tree.command(name="editstreak", description="[ADMIN] Manually add / subtract days to a user's bump streak.")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(
    member="The member whose streak you want to update.",
    days="The number of days to change from their current streak.",
    operation_add="Use true to add | Use false to subtract"
)
async def add_streak(interaction: discord.Interaction, member: discord.Member, days: int, operation_add: bool):

    user_id = str(member.id)
    today = datetime.utcnow().date()
    
    # Load user data or initialize if new
    user_data = bump_data.get(user_id, {"bump_streak": 0, "last_bump_date": None})

    user_data["last_bump_date"] = today.isoformat()

    if operation_add:
        user_data["bump_streak"] += days
        await interaction.response.send_message(
            f"✅ Successfully added **{days} days** to {member.mention}'s streak. "
            f"New streak: **{user_data['bump_streak']} days!**", 
            ephemeral=True
        )
    else:
        if user_data["bump_streak"] - days < 0:
            user_data["bump_streak"] = 0
            await interaction.response.send_message(
                f"✅ Successfully reset {member.mention}'s streak. "
                f"New streak: **{user_data['bump_streak']} days!**", 
                ephemeral=True
            )
        else:
            user_data["bump_streak"] -= days
            await interaction.response.send_message(
                f"✅ Successfully subtracted **{days} days** to {member.mention}'s streak. "
                f"New streak: **{user_data['bump_streak']} days!**", 
                ephemeral=True
            )

    bump_data[user_id] = user_data
    save_data(bump_data)

    # Apply role rewards
    await update_roles(member, user_data['bump_streak'])

# Handle permission errors for the admin command
@add_streak.error
async def add_streak_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You need the **Manage Server** permission to use this command.", ephemeral=True
        )
    else:
        # Re-raise other errors
        raise error

# ----------------------
# /bumpstreak (slash command)
# ----------------------
@tree.command(name="bumpstreak", description="Check your bump streak.")
async def streak(interaction: discord.Interaction):

    user_id = str(interaction.user.id)

    if user_id not in bump_data:
        return await interaction.response.send_message(
            "You don't have a streak yet! Bump the server to start one."
        )

    streak = bump_data[user_id]["bump_streak"]

    await interaction.response.send_message(
        f"🔥 **{interaction.user.display_name}**, your streak is **{streak} days!**"
    )


# ----------------------
# /bumpleaderboard (slash command)
# ----------------------
@tree.command(name="bumpleaderboard", description="Show the top 5 bump streaks.")
async def bumpleaderboard(interaction: discord.Interaction):

    if not bump_data:
        return await interaction.response.send_message("No streaks yet!")

    # Sort by streak descending
    top = sorted(
        bump_data.items(),
        key=lambda x: x[1]["bump_streak"],
        reverse=True
    )[:5]

    msg = "🏆 **Top 5 Bump Streaks:**\n\n"

    for i, (uid, info) in enumerate(top, start=1):
        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else f"Unknown ({uid})"
        msg += f"**{i}. {name} — {info['bump_streak']} days**\n"

    await interaction.response.send_message(msg)

# ----------------------
# Run bot
# ----------------------

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable not set.")

bot.run(DISCORD_TOKEN)
