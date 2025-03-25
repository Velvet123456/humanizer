import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask

# Load environment variables from .env file
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

# Create a Flask web server
app = Flask(__name__)

@app.route('/')
def home():
    return "Self-bot is running!"

# Start both Flask and the bot
if __name__ == "__main__":
    from threading import Thread

    # Run the web server on a separate thread
    Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

    # Run the Discord bot
    client.run(TOKEN, bot=False)
