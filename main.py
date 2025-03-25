import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("Error: DISCORD_TOKEN is not set in .env file")
    exit(1)

# Self-bot setup
client = commands.Bot(command_prefix="!", self_bot=True)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

client.run(TOKEN, bot=False)  # 'bot=False' is required for self-bots
