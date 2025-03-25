import discord
from discord import enums  # This is key for selfbot features
from discord.ext import commands
import firebase_admin
from firebase_admin import credentials, db
import random
import os
import time


BLACKLISTED_IDS = ["1317890350471319633","909446748613779486"]

cred = credentials.Certificate("rohackersz-firebase-adminsdk-fbsvc-ef11a7abad.json")
firebase_admin.initialize_app(cred, {
    "databaseURL": "https://rohackersz-default-rtdb.firebaseio.com/"
})

ban_ref = db.reference("economyban")

def is_banned(user_id: int) -> bool:
    """Check if a user is banned from the bot."""
    banned_users = ban_ref.get() or {}
    return str(user_id) in banned_users

class CustomBot(commands.Bot):
    async def invoke(self, ctx):
        """Override invoke to allow all commands without ban checks."""
        await super().invoke(ctx)

async def check_permission(interaction: discord.Interaction) -> bool:
    """Checks if the user has permission to use commands."""
    if is_banned(interaction.user.id):
        embed = discord.Embed(
            title="❌ Access Denied",
            description="You are banned from using this bot.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False

def get_balance(user_id):
    ref = db.reference(f"users/{user_id}/balance")
    balance = ref.get()
    if balance is None:
        ref.set(1000)
        return 1000
    return balance

def update_balance(user_id, amount):
    ref = db.reference(f"users/{user_id}/balance")
    current_balance = ref.get() or 0
    ref.set(current_balance + amount)

def get_last_claim(user_id):
    ref = db.reference(f"users/{user_id}/last_daily")
    return ref.get() or 0

def set_last_claim(user_id, timestamp):
    ref = db.reference(f"users/{user_id}/last_daily")
    ref.set(timestamp)

def redeem_code(user_id, code):
    ref = db.reference(f"codes/{code}")
    reward = ref.get()
    if reward and not db.reference(f"redeemed/{code}/{user_id}").get():
        update_balance(user_id, reward)
        db.reference(f"redeemed/{code}/{user_id}").set(True)
        return reward
    return None

def rob_user(robber_id, victim_id):
    victim_balance = get_balance(victim_id)
    robber_balance = get_balance(robber_id)

    if victim_balance < 100:
        return "❌ This user is too poor to rob!"

    if random.randint(1, 100) <= 45:
        stolen_amount = int(victim_balance * 0.45)
        update_balance(robber_id, stolen_amount)
        update_balance(victim_id, -stolen_amount)
        return f"💰 You successfully robbed {stolen_amount} coins from <@{victim_id}>!"

    lost_amount = int(robber_balance * 0.18)
    update_balance(robber_id, -lost_amount)
    return f"❌ You failed to rob <@{victim_id}> and lost {lost_amount} coins!"

def pay_user(sender_id, receiver_id, amount):
    sender_balance = get_balance(sender_id)
    if amount <= 0 or sender_balance < amount:
        return "❌ Invalid amount!"
    update_balance(sender_id, -amount)
    update_balance(receiver_id, amount)
    return f"✅ You sent {amount} coins to <@{receiver_id}>!"

def get_server_leaderboard(guild):
    leaderboard = sorted(
        [(m.name, get_balance(str(m.id))) for m in guild.members 
         if not m.bot and str(m.id) not in BLACKLISTED_IDS], 
        key=lambda x: x[1], reverse=True)[:5]
    return leaderboard

def get_global_leaderboard():
    ref = db.reference("users")
    users = ref.get()
    if not users:
        return []


    filtered_users = {uid: data for uid, data in users.items() 
                     if uid not in BLACKLISTED_IDS}

    leaderboard = sorted(filtered_users.items(), 
                        key=lambda x: x[1].get("balance", 0), 
                        reverse=True)[:5]
    return leaderboard

def get_xp(user_id):
    ref = db.reference(f"users/{user_id}/xp")
    xp = ref.get()
    if xp is None:
        ref.set(0)
        return 0
    return xp

def get_level(user_id):
    ref = db.reference(f"users/{user_id}/level")
    level = ref.get()
    if level is None:
        ref.set(1)
        return 1
    return level

def update_xp(user_id, amount):
    current_xp = get_xp(user_id)
    current_level = get_level(user_id)
    xp_needed = 100 + (current_level - 1) * 150
    new_xp = current_xp + amount
    if new_xp >= xp_needed:
        new_xp -= xp_needed
        new_level = current_level + 1
        db.reference(f"users/{user_id}/level").set(new_level)
        update_balance(user_id, new_level * 100)
        return f"🎉 You leveled up to {new_level}! You received {new_level * 100} coins!"
    db.reference(f"users/{user_id}/xp").set(new_xp)
    return None

class SelfBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read messages
        intents.members = True  # Needed for user mentions
        super().__init__(
            command_prefix="!",
            self_bot=True,
            intents=intents  # THIS WAS MISSING
        )

    async def on_ready(self):
        print(f"Logged in as {self.user}")

    async def on_message(self, message):
        if message.author.bot:
            return

        user_id = str(message.author.id)
        parts = message.content.lower().split()

        if message.content.startswith("!help"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return

            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.") 
                return
            await message.reply(
                "**Commands:**\n"
                "`!profile [@user]` - Check profile\n"
                "`!work` - Just Work.\n"
                "`!daily` - Claim daily rewards.\n"
                "`!gamble <amount/all>` - Gamble coins.\n"
                "`!coinflip <amount> <heads/tails>` - Coinflip.\n"
                "`!redeem <code>` - Redeem a code.\n"
                "`!rob @user` - Steal coins from others.\n"
                "`!pay @user <amount>` - Transfer coins to someone.\n"
                "`!leaderboard` - Check The Server Leaderboard.\n"
                "`!globalleaderboard` - Check the Global Leaderboard."
            )

        if message.content.startswith("!profile"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return

            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.") 
                return
            target = message.mentions[0] if message.mentions else message.author
            user_id = str(target.id)
            balance = get_balance(user_id)
            level = get_level(user_id)
            xp = get_xp(user_id)
            xp_needed = 100 + (level - 1) * 150
            profile_msg = (
                f"{target.name}'s Profile:\n\n"
                f"1. Balance: {balance}\n"
                f"2. Level: {level}\n"
                f"3. XP: {xp}/{xp_needed}"
            )
            await message.reply(profile_msg)


        if message.content.startswith("!work"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.") 
                return
            last_work_ref = db.reference(f"users/{user_id}/last_work")
            last_work = last_work_ref.get() or 0
            now = int(time.time())

            cooldown = 600
            remaining = cooldown - (now - last_work)

            if remaining > 0:
                minutes = remaining // 60
                seconds = remaining % 60
                await message.reply(f"Please wait {minutes}m {seconds}s before working again!")
                return

            jobs = ["skid","awp.gg developer","grass toucher","farmer","stripper","discord e-girls server manager","wave developer","footballer","sigma","dancer","robber","byfron developer"]
            job = random.choice(jobs)
            earnings = random.randint(50, 200)
            update_balance(user_id, earnings)
            xp_message = update_xp(user_id, 3)
            last_work_ref.set(now)

            response = f"You worked as a {job} and earned {earnings} coins! New balance: {get_balance(user_id)} coins."
            if xp_message:
                response += "\n" + xp_message
            await message.reply(response)





        if message.content.startswith("!daily"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.") 
                return
            if int(time.time()) - get_last_claim(user_id) < 86400:
                await message.reply(f"already claimed today!")
            else:
                update_balance(user_id, 500)
                set_last_claim(user_id, int(time.time()))
                xp_message = update_xp(user_id, 5)
                await message.reply(f"claimed 500 coins!")

        if message.content.startswith(("!leaderboard", "!lb")):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.") 
                return
            leaderboard = get_server_leaderboard(message.guild)
            if not leaderboard:
                await message.reply("❌ | No users found in this server!")
                return
            await message.reply("**🏆 Server Leaderboard**\n" + 
                "\n".join(f"{i+1}. {name} - {bal} coins" for i, (name, bal) in enumerate(leaderboard)))

        if message.content.startswith(("!globalleaderboard", "!glb")):
                if message.guild is None:
                    await message.reply("❌ This command can only be used in a server!")
                    return

                top_players = get_global_leaderboard()
                if not top_players:
                    await message.reply("❌ | No users found globally!")
                    return

                leaderboard_msg = "**🌍 Global Leaderboard**\n"
                for idx, (user_id, data) in enumerate(top_players, 1):
                    user = await self.fetch_user(int(user_id))
                    leaderboard_msg += f"{idx}. {user.name} - {data.get('balance', 0)} coins\n"

                await message.reply(leaderboard_msg)

        if message.content.startswith("!redeem"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.") 
                return
            if len(parts) < 2:
                await message.reply(f"use `!redeem <code>`")
                return
            code = parts[1]
            reward = redeem_code(user_id, code)
            if reward:
                await message.reply(f"you redeemed `{code}` and received {reward} coins!")
            else:
                await message.reply(f"invalid or already used code!")

        if message.content.startswith("!rob"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.") 
                return
            if not message.mentions or str(message.mentions[0].id) == user_id:
                await message.reply(f"use `!rob @user`")
                return
            await message.reply(rob_user(user_id, str(message.mentions[0].id)))

        if message.content.startswith("!pay"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.") 
                return
            if len(parts) < 3 or not message.mentions or not parts[2].isdigit():
                await message.reply(f"use `!pay @user <amount>`")
                return
            await message.reply(pay_user(user_id, str(message.mentions[0].id), int(parts[2])))

        if message.content.startswith(("!coinflip", "!cf")):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.") 
                return
            if len(parts) < 3:
                await message.reply(f"use `!coinflip <amount/all> <heads/tails>`")
                return

            choice = parts[2].lower()
            if choice not in ["heads", "tails"]:
                await message.reply(f"use `!coinflip <amount/all> <heads/tails>`")
                return

            balance = get_balance(user_id)

            if parts[1].lower() == "all":
                bet = balance
            elif parts[1].isdigit():
                bet = int(parts[1])
            else:
                await message.reply(f"invalid bet amount!")
                return

            if bet > balance or bet <= 0:
                await message.reply(f"you don't have enough coins!")
                return

            result = random.choice(["heads", "tails"])
            if result == choice:
                update_balance(user_id, bet)
                xp_message = update_xp(user_id, 3)
                await message.reply(f"✅ The coin landed on **{result}**! You won {bet} coins! New balance: {get_balance(user_id)} coins.")
            else:
                update_balance(user_id, -bet)
                await message.reply(f"❌ The coin landed on **{result}**! You lost {bet} coins! New balance: {get_balance(user_id)} coins.")

        if message.content.startswith("!gamble"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.") 
                return
            if len(parts) < 2 or (not parts[1].isdigit() and parts[1] != "all"):
                await message.reply(f"use `!gamble <amount/all>`")
                return

            balance = get_balance(user_id)
            bet = balance if parts[1] == "all" else int(parts[1])

            if bet > balance or bet <= 0:
                await message.reply(f"invalid bet amount!")
                return

            if random.choice([True, False]):
                update_balance(user_id, bet)
                xp_message = update_xp(user_id, 3)
                await message.reply(f"you won {bet} coins! New balance is {get_balance(user_id)} coins.")
            else:
                update_balance(user_id, -bet)
                await message.reply(f"you lost {bet} coins! New balance is {get_balance(user_id)} coins.")


client = SelfBot()
client.run(os.getenv("DISCORD_TOKEN"))
