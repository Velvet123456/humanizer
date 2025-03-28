import discord
from flask import Flask
from threading import Thread
from discord.ext import commands
import firebase_admin
from firebase_admin import credentials, db
import random
import os
from dotenv import load_dotenv
import time

# --- Flask Uptime Server ---
app = Flask(__name__)
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("Error: DISCORD_TOKEN is not set in .env file")
    exit(1)

@app.route('/')
def home():
    return "Self-bot is running!"

# --- Firebase Setup ---
BLACKLISTED_IDS = ["1317890350471319633", "909446748613779486","1354087903126487120"]

cred = credentials.Certificate("rohackersz-firebase-adminsdk-fbsvc-ef11a7abad.json")
firebase_admin.initialize_app(cred, {
    "databaseURL": "https://rohackersz-default-rtdb.firebaseio.com/"
})

ban_ref = db.reference("economyban")

def is_banned(user_id: int) -> bool:
    banned_users = ban_ref.get() or {}
    return str(user_id) in banned_users

# --- Utility Functions ---
def get_balance(user_id):
    ref = db.reference(f"users/{user_id}/balance")
    balance = ref.get()
    if balance is None:
        ref.set(0)
        return 0
    return balance

def update_balance(user_id, amount):
    user_ref = db.reference(f"users/{user_id}")
    current_data = user_ref.get()
    if current_data is None or not isinstance(current_data, dict):
        current_balance = 0
    else:
        current_balance = current_data.get("balance", 0)
    user_ref.update({"balance": current_balance + amount})

def get_last_claim(user_id):
    ref = db.reference(f"users/{user_id}/last_daily")
    return ref.get() or 0

def set_last_claim(user_id, timestamp):
    ref = db.reference(f"users/{user_id}/last_daily")
    ref.set(timestamp)

def redeem_code(user_id, code):
    code = code.lower()
    ref = db.reference("codes")
    all_codes = ref.get() or {}
    matched_code = next((c for c in all_codes if c.lower() == code), None)
    if matched_code is None:
        return None
    reward = db.reference(f"codes/{matched_code}").get()
    if reward and not db.reference(f"redeemed/{matched_code}/{user_id}").get():
        update_balance(user_id, reward)
        db.reference(f"redeemed/{matched_code}/{user_id}").set(True)
        return reward
    return None

def rob_user(robber_id, victim_id):
    victim_ref = db.reference(f"users/{victim_id}")
    robber_ref = db.reference(f"users/{robber_id}")
    victim_data = victim_ref.get()
    robber_data = robber_ref.get()
    if not victim_data or not robber_data:
        return "❌ User never used the bot (Doesn't have any money)"
    victim_balance = victim_data.get("balance", 0)
    robber_balance = robber_data.get("balance", 0)
    last_rob_time = robber_data.get("last_rob_time", 0)
    current_time = int(time.time())
    if current_time - last_rob_time < 600:
        remaining_time = 600 - (current_time - last_rob_time)
        return f"❌ You can rob again in {remaining_time // 60} minutes and {remaining_time % 60} seconds."
    robber_ref.update({"last_rob_time": current_time})
    if victim_balance < 100:
        return "❌ This user is too poor to rob!"
    if random.randint(1, 100) <= 28:
        stolen_amount = int(victim_balance * 0.28)
        update_balance(robber_id, stolen_amount)
        update_balance(victim_id, -stolen_amount)
        return f"💰 You successfully robbed {stolen_amount} coins from <@{victim_id}>!"
    lost_amount = int(robber_balance * 0.20)
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
        [(m.name, get_balance(str(m.id)) or 0) for m in guild.members if not m.bot and str(m.id) not in BLACKLISTED_IDS],
        key=lambda x: x[1], reverse=True
    )[:5]
    return leaderboard


def get_global_leaderboard():
    ref = db.reference("users")
    users = ref.get()
    if not users:
        return []
    filtered_users = {uid: data for uid, data in users.items() if uid not in BLACKLISTED_IDS}
    leaderboard = sorted(
        filtered_users.items(),
        key=lambda x: x[1].get("balance", 0),
        reverse=True
    )[:5]
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

# --- Self-Bot Class ---
class SelfBot(discord.Client):
    def __init__(self):
        super().__init__(self_bot=True)
        self.command_prefix = "!"
        
    async def on_ready(self):
        print(f"Logged in as {self.user}")
        
    async def on_message(self, message):
        # Ignore messages from bots
        if message.author.bot:
            return
        
        user_id = str(message.author.id)
        parts = message.content.lower().split()

        if message.content.startswith("!gamble"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return
            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}
            loan_deadline = user_data.get("loan_deadline", 0)
            current_loan = user_data.get("loan", 0)
            loan_paid = user_data.get("loan_paid", 0)
            if loan_deadline > 0 and time.time() > loan_deadline and (current_loan - loan_paid) > 0:
                await message.reply("❌ You failed to repay your loan on time! You cannot use some commands until you **fully repay** your loan.")
                return
            if len(parts) < 2 or (not parts[1].isdigit() and parts[1].lower() != "all"):
                await message.reply("Use !gamble <amount/all>")
                return
            balance = get_balance(user_id)
            bet = balance if parts[1].lower() == "all" else int(parts[1])
            if bet > balance or bet <= 0:
                await message.reply("Invalid Bet Amount!")
                return
            
            # Slot machine emojis
            emojis = ["🍒", "🍊", "🍋", "🍇", "🍉"]
            
            roll = random.random()
            if roll <= 0.10:  # 15% chance for 3x win
                chosen = random.choice(emojis)
                slot_result = [chosen, chosen, chosen]
                winnings = bet * 3
                update_balance(user_id, winnings)
                await message.reply(f"{slot_result[0]} {slot_result[1]} {slot_result[2]} You won **3x! +{winnings}** (Balance: {get_balance(user_id)})")
            elif roll <= 0.35:  # 30% chance for 2x win
                chosen = random.choice(emojis)
                slot_result = [chosen, chosen, random.choice(emojis)]
                winnings = bet * 2
                update_balance(user_id, winnings)
                await message.reply(f"{slot_result[0]} {slot_result[1]} {slot_result[2]} You won **2x! +{winnings}** (Balance: {get_balance(user_id)})")
            else:  # 55% chance to lose
                slot_result = [random.choice(emojis) for _ in range(3)]
                update_balance(user_id, -bet)
                await message.reply(f"{slot_result[0]} {slot_result[1]} {slot_result[2]} You lost **{bet}!** (Balance: {get_balance(user_id)})")


        
        if message.content.startswith("!help"):
            if message.guild is None:
                await message.reply("❌ | This command can only be used in a server!")
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
                "`!loan <amount>` - Take loan from the bank.\n"
                "`!payloan <amount>` - Pay back the loan amount taken.\n"
                "`!redeem <code>` - Redeem a code.\n"
                "`!rob @user` - Steal coins from others.\n"
                "`!transfer @user <amount>` - Transfer coins to someone.\n"
                "`!leaderboard` - Check The Server Leaderboard.\n"
            )
        
        # !profile command
        if message.content.startswith("!profile"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return
            target = message.mentions[0] if message.mentions else message.author
            target_id = str(target.id)
            xp_message = update_xp(user_id, 1)
            balance = get_balance(target_id)
            level = get_level(target_id)
            xp = get_xp(target_id)
            xp_needed = 100 + (level - 1) * 150
            profile_msg = (
                f"{target.name}'s Profile:\n\n"
                f"1. Balance: {balance}\n"
                f"2. Level: {level}\n"
                f"3. XP: {xp}/{xp_needed}"
            )
            await message.reply(profile_msg)
        
        # !work command
        if message.content.startswith("!work"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return
            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}
            loan_deadline = user_data.get("loan_deadline", 0)
            current_loan = user_data.get("loan", 0)
            loan_paid = user_data.get("loan_paid", 0)
            if loan_deadline > 0 and time.time() > loan_deadline and (current_loan - loan_paid) > 0:
                await message.reply("❌ You failed to repay your loan on time! You cannot use some commands until you **fully repay** your loan.")
                return
            last_work_ref = db.reference(f"users/{user_id}/last_work")
            last_work = last_work_ref.get() or 0
            now = int(time.time())
            cooldown = 120
            remaining = cooldown - (now - last_work)
            if remaining > 0:
                minutes = remaining // 60
                seconds = remaining % 60
                await message.reply(f"Please wait {minutes}m {seconds}s before working again!")
                return
            last_work_ref.set(now)
            jobs = [
                "skid", "awp.gg developer", "grass toucher", "farmer", "stripper",
                "discord e-girls server manager", "wave developer", "footballer", "sigma",
                "dancer", "robber", "byfron developer"
            ]
            job = random.choice(jobs)
            earnings = random.randint(50, 200)
            update_balance(user_id, earnings)
            xp_message = update_xp(user_id, 6)
            response = f"You worked as a {job} and earned {earnings} coins! New balance: {get_balance(user_id)} coins."
            if xp_message:
                response += "\n" + xp_message
            await message.reply(response)
        
        # !daily command
        if message.content.startswith("!daily"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return
            if int(time.time()) - get_last_claim(user_id) < 86400:
                await message.reply("Already claimed today!")
            else:
                update_balance(user_id, 500)
                set_last_claim(user_id, int(time.time()))
                xp_message = update_xp(user_id, 30)
                await message.reply(f"👴 | Claimed your daily 500 coins! {xp_message if xp_message else ''}")
        
        # !loan command
        if message.content.startswith("!loan"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return
            args = message.content.split()
            if len(args) < 2 or not args[1].isdigit():
                await message.reply("❌ Usage: `!loan <amount>`")
                return
            amount = int(args[1])
            if amount <= 0 or amount > 2000:
                await message.reply("❌ You can only take a loan between 1 and 2000 coins!")
                return
            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}
            current_loan = user_data.get("loan", 0)
            if current_loan > 0:
                await message.reply(f"❌ You already have an active loan of {current_loan} coins! Repay it first.")
                return
            interest = int(amount * 0.10)
            total_repay = amount + interest
            xp_message = update_xp(user_id, 1)
            deadline = int(time.time()) + 86400  # 24 hours from now
            user_ref.update({
                "loan": total_repay,
                "loan_deadline": deadline,
                "loan_paid": 0
            })
            update_balance(user_id, amount)
            await message.reply(f"✅ You have borrowed {amount} coins. You need to repay {total_repay} coins within 24 hours or you'll be blocked from some commands.")
        
        # !payloan command
        if message.content.startswith("!payloan"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return
            args = message.content.split()
            if len(args) < 2 or not args[1].isdigit():
                await message.reply("❌ Usage: `!payloan <amount>`")
                return
            amount = int(args[1])
            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}
            current_loan = user_data.get("loan", 0)
            loan_paid = user_data.get("loan_paid", 0)
            loan_deadline = user_data.get("loan_deadline", 0)
            if current_loan == 0:
                await message.reply("✅ You have no active loans to repay!")
                return
            balance = get_balance(user_id)
            if amount > balance:
                await message.reply(f"❌ You only have {balance} coins!")
                return
            if amount > current_loan - loan_paid:
                amount = current_loan - loan_paid
            update_balance(user_id, -amount)
            loan_paid += amount
            xp_message = update_xp(user_id, 1)
            remaining_loan = current_loan - loan_paid
            user_ref.update({"loan_paid": loan_paid})
            time_left = max(0, loan_deadline - int(time.time()))
            hours = time_left // 3600
            minutes = (time_left % 3600) // 60
            if remaining_loan == 0:
                user_ref.update({
                    "loan": 0,
                    "loan_deadline": 0,
                    "loan_paid": 0
                })
                await message.reply("✅ You have fully repaid your loan! You can now use all commands again.")
            else:
                await message.reply(f"✅ Paid {loan_paid}/{current_loan}$, Time Left: {hours}h {minutes}m.")
        
        # !rob command
        if message.content.startswith("!rob"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return
            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}
            loan_deadline = user_data.get("loan_deadline", 0)
            current_loan = user_data.get("loan", 0)
            xp_message = update_xp(user_id, 6)
            loan_paid = user_data.get("loan_paid", 0)
            if loan_deadline > 0 and time.time() > loan_deadline and (current_loan - loan_paid) > 0:
                await message.reply("❌ You failed to repay your loan on time! You cannot use some commands until you **fully repay** your loan.")
                return
            if not message.mentions or str(message.mentions[0].id) == user_id:
                await message.reply("Use `!rob @user`")
                return
            result = rob_user(user_id, str(message.mentions[0].id))
            await message.reply(result)
        
        # !redeem command
        if message.content.startswith("!redeem"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return
            if len(parts) < 2:
                await message.reply("Use `!redeem <code>`")
                return
            code = parts[1]
            reward = redeem_code(user_id, code)
            if reward:
                await message.reply(f"🟢 | You redeemed `{code}` and received {reward} coins!")
            else:
                await message.reply("🔴 | This code is either invalid or has been already used!")
        
        # !pay command
        if message.content.startswith("!transfer"):
            if message.guild is None:
                await message.reply("❌ | This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return
            if len(parts) < 3 or not message.mentions or not parts[2].isdigit():
                await message.reply("Use `!pay @user <amount>`")
                return
            result = pay_user(user_id, str(message.mentions[0].id), int(parts[2]))
            xp_message = update_xp(user_id, 6)
            await message.reply(result)
        
        # !coinflip command
        if message.content.startswith(("!coinflip", "!cf")):
            if message.guild is None:
                await message.reply("❌ | This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return
            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}
            loan_deadline = user_data.get("loan_deadline", 0)
            current_loan = user_data.get("loan", 0)
            loan_paid = user_data.get("loan_paid", 0)
            if loan_deadline > 0 and time.time() > loan_deadline and (current_loan - loan_paid) > 0:
                await message.reply("❌ You failed to repay your loan on time! You cannot use some commands until you **fully repay** your loan.")
                return
            if len(parts) < 3:
                await message.reply("Use `!coinflip <amount/all> <heads/tails>`")
                return
            choice = parts[2].lower()
            if choice not in ["heads", "tails"]:
                await message.reply("Use `!coinflip <amount/all> <heads/tails>`")
                return
            balance = get_balance(user_id)
            if parts[1].lower() == "all":
                bet = balance
            elif parts[1].isdigit():
                bet = int(parts[1])
            else:
                await message.reply("Invalid bet amount!")
                return
            if bet > balance or bet <= 0:
                await message.reply("You don't have enough coins!")
                return
            result = random.choice(["heads", "tails"])
            if result == choice:
                update_balance(user_id, bet)
                xp_message = update_xp(user_id, 5)
                await message.reply(f"✅ The coin landed on **{result}**! You won {bet} coins! New balance: {get_balance(user_id)} coins.")
            else:
                update_balance(user_id, -bet)
                await message.reply(f"❌ The coin landed on **{result}**! You lost {bet} coins! New balance: {get_balance(user_id)} coins.")
        
        # !leaderboard command
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



        

# --- Main Execution ---
if __name__ == "__main__":
    def run_flask():
        app.run(host="0.0.0.0", port=8080)
    Thread(target=run_flask).start()
    print("Flask server is running...")
    client = SelfBot()
    client.run(TOKEN)
