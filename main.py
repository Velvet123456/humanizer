import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get the token from environment variables
TOKEN = os.getenv("DISCORD_TOKEN")

# Check if token is loaded correctly
if not TOKEN:
    print("Error: DISCORD_TOKEN is not set in .env file")
    exit(1)

# Set up the bot (self-bot requires `self_bot=True`)
client = commands.Bot(command_prefix="!", self_bot=True)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

# Run the client with the token
client.run(TOKEN)
