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
import asyncio

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

            user_id = str(message.author.id)
            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}
            loan_deadline = user_data.get("loan_deadline", 0)
            current_loan = user_data.get("loan", 0)
            loan_paid = user_data.get("loan_paid", 0)
            is_lucky = user_data.get("lucky", False)  # Check if user has lucky mode enabled

            if loan_deadline > 0 and time.time() > loan_deadline and (current_loan - loan_paid) > 0:
                await message.reply("❌ You failed to repay your loan on time! You cannot use some commands until you **fully repay** your loan.")
                return

            if len(parts) < 2 or (not parts[1].isdigit() and parts[1].lower() != "all"):
                await message.reply("Use !gamble <amount/all>")
                return

            balance = get_balance(user_id)
            if balance <= 0:
                await message.reply("You don't have any money to gamble.")
                return

            if parts[1].lower() == "all":
                bet = balance
            else:
                try:
                    bet = int(parts[1])
                except ValueError:
                    await message.reply("Invalid amount format.")
                    return

            if bet <= 0 or bet > balance:
                await message.reply("Invalid Bet Amount!")
                return

            emojis = ["🍒", "🍊", "🍋", "🍇", "🍉"]

            if is_lucky:
                # Lucky mode - guaranteed win (2x or 3x)
                outcome = random.choice(["2x", "3x"])
                chosen = random.choice(emojis)
                if outcome == "3x":
                    slot_result = [chosen, chosen, chosen]
                    winnings = bet * 3
                    update_balance(user_id, winnings)
                    await message.reply(f"{slot_result[0]} {slot_result[1]} {slot_result[2]} You won **3x +{winnings}** (Balance: {get_balance(user_id)})")
                else:
                    others = [e for e in emojis if e != chosen]
                    third = random.choice(others)
                    pos = random.randint(0, 2)
                    slot_result = [chosen, chosen, chosen]
                    slot_result[pos] = third
                    winnings = bet * 2
                    update_balance(user_id, winnings)
                    await message.reply(f"{slot_result[0]} {slot_result[1]} {slot_result[2]} You won **2x +{winnings}** (Balance: {get_balance(user_id)})")
            else:
                # Regular mode - random chance of winning
                roll = random.random()
                if roll <= 0.10:  # 10% chance to win 3x
                    chosen = random.choice(emojis)
                    slot_result = [chosen, chosen, chosen]
                    winnings = bet * 3
                    update_balance(user_id, winnings)
                    await message.reply(f"{slot_result[0]} {slot_result[1]} {slot_result[2]} You won **3x +{winnings}** (Balance: {get_balance(user_id)})")
                elif roll <= 0.40:  # 30% chance to win 2x
                    chosen = random.choice(emojis)
                    others = [e for e in emojis if e != chosen]
                    third = random.choice(others)
                    pos = random.randint(0, 2)
                    slot_result = [chosen, chosen, chosen]
                    slot_result[pos] = third
                    winnings = bet * 2
                    update_balance(user_id, winnings)
                    await message.reply(f"{slot_result[0]} {slot_result[1]} {slot_result[2]} You won **2x +{winnings}** (Balance: {get_balance(user_id)})")
                else:  # 60% chance to lose
                    while True:
                        slot_result = [random.choice(emojis) for _ in range(3)]
                        if not (slot_result[0] == slot_result[1] == slot_result[2]) and not (
                            slot_result[0] == slot_result[1] != slot_result[2] or
                            slot_result[0] == slot_result[2] != slot_result[1] or
                            slot_result[1] == slot_result[2] != slot_result[0]
                        ):
                            break
                    update_balance(user_id, -bet)
                    await message.reply(f"{slot_result[0]} {slot_result[1]} {slot_result[2]} You lost **{bet}!** (Balance: {get_balance(user_id)})")



        if message.content.startswith("!crime"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return

            user_id = message.author.id

            if is_banned(user_id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return

            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}
            last_crime = user_data.get("last_crime", 0)
            loan_deadline = user_data.get("loan_deadline", 0)
            current_loan = user_data.get("loan", 0)
            loan_paid = user_data.get("loan_paid", 0)

            if loan_deadline > 0 and time.time() > loan_deadline and (current_loan - loan_paid) > 0:
                await message.reply("❌ You failed to repay your loan on time! You cannot use some commands until you **fully repay** your loan.")
                return

            if time.time() - last_crime < 600:
                remaining = int(600 - (time.time() - last_crime))
                mins, secs = divmod(remaining, 60)
                await message.channel.send(f"⏳ You can use `!crime` again in {mins}m {secs}s.")
                return

            # Check Firebase for lucky status
            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}
            lucky = user_data.get("lucky", False)  # Firebase lucky check

            if lucky:
                amount = random.randint(500, 1200)  # Lucky users get a higher range of rewards
                update_balance(user_id, amount)
                await message.channel.send(f"💸 You committed a **crime** and got away with **+{amount}** coins!")
            else:
                chance = random.randint(1, 100)
                if chance <= 65:
                    amount = random.randint(250, 1000)
                    update_balance(user_id, amount)
                    await message.channel.send(f"💸 You committed a **crime** and got away with **+{amount}** coins!")
                else:
                    amount = random.randint(400, 1000)
                    balance = get_balance(user_id)
                    fine = min(amount, balance)
                    update_balance(user_id, -fine)
                    await message.channel.send(f"🚨 You got **caught** committing a crime and paid a **fine of {fine}** coins!")




            user_ref.update({"last_crime": time.time()})
            await asyncio.sleep(1)

        if message.content.startswith("!roulette"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return

            user_id = message.author.id

            if is_banned(user_id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return

            parts = message.content.split()
            if len(parts) != 3 or parts[1] not in ["red", "black", "green"] or (parts[2].lower() != "all" and not parts[2].isdigit()):
                await message.reply("Usage: `!roulette <red/black/green> <amount>` or `!roulette <red/black/green> all`")
                return

            color = parts[1]
            balance = get_balance(user_id)

            if parts[2].lower() == "all":
                bet = balance
            else:
                bet = int(parts[2])

            if bet <= 0 or bet > balance:
                await message.reply("❌ Invalid bet amount.")
                return

            # Check Firebase for lucky status
            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}
            lucky = user_data.get("lucky", False)  # This is where you check the lucky status

            if lucky:
                # If lucky, always win with a multiplier of 2 or 14
                if color == "green":
                    roll = 0  # Always land on green for lucky users
                    multiplier = 14
                elif color == "red":
                    roll = random.choice([1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31, 33, 35])  # Random red number
                    multiplier = 2
                elif color == "black":
                    roll = random.choice([2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36])  # Random black number
                    multiplier = 2
                winnings = bet * multiplier
                update_balance(user_id, winnings - bet)

                await message.reply(f"🎉 It landed on **{roll}**! You won **{winnings}** coins! (Balance: {get_balance(user_id)})")
                return
            else:
                # Regular roulette logic
                roll = random.randint(0, 36)
                win = False
                multiplier = 0

                if color == "green" and roll == 0:
                    win = True
                    multiplier = 14
                elif color == "red" and roll % 2 == 1 and roll != 0:
                    win = True
                    multiplier = 2
                elif color == "black" and roll % 2 == 0 and roll != 0:
                    win = True
                    multiplier = 2

                if win:
                    winnings = bet * multiplier
                    update_balance(user_id, winnings)
                    await message.reply(f"🎉 It landed on **{roll}**! You won **{winnings}** coins! (Balance: {get_balance(user_id)})")
                else:
                    update_balance(user_id, -bet)
                    await message.reply(f"💥 It landed on **{roll}**! You lost **{bet}** coins. (Balance: {get_balance(user_id)})")





        if message.content.startswith("!help"):
            if message.guild is None:
                await message.reply("❌ | This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return
            await message.reply(
                "**ntsbot Commands:**\n"
                "!profile [@user] - Check profile\n"
                "!work - Just Work.\n"
                "!daily - Claim daily rewards.\n"
                "!gamble <amount/all> - Gamble coins.\n"
                "!coinflip <amount> <heads/tails> - Coinflip.\n"
                "!crime - Commit a crime.\n"
                "!roulette <red/black> <amount> - Play roulette.\n"
                "!blackjack <amount> - Play a game of blackjack.\n"
                "!loan <amount> - Take loan from the bank.\n"
                "!payloan <amount> - Pay back the loan amount taken.\n"
                "!dice <amount> <number> - Roll dice for prize.\n"
                "!redeem <code> - Redeem a code.\n"
                "!rob @user - Steal coins from others.\n"
                "!transfer @user <amount> - Transfer coins.\n"
                "!leaderboard - Check The Server Leaderboard.\n"
            )

        if message.content.startswith("!blackjack"):
                if message.guild is None:
                    await message.reply("❌ This command can only be used in a server!")
                    return

                user_id = message.author.id

                if is_banned(user_id):
                    await message.reply("❌ | You are **banned** from using this bot.")
                    return

                parts = message.content.split()
                if len(parts) != 2:
                    await message.reply("Usage: `!blackjack <amount>` or `!blackjack all`")
                    return

                balance = get_balance(user_id)
                if parts[1].lower() == "all":
                    bet = balance
                elif parts[1].isdigit():
                    bet = int(parts[1])
                else:
                    await message.reply("Usage: `!blackjack <amount>` or `!blackjack all`")
                    return

                if bet <= 0:
                    await message.reply("❌ Bet must be greater than 0.")
                    return

                if balance < bet:
                    await message.reply("❌ You don't have enough balance to place that bet.")
                    return

                # Check Firebase for lucky status
                user_ref = db.reference(f"users/{user_id}")
                user_data = user_ref.get() or {}
                lucky = user_data.get("lucky", False)  # This is where you check the lucky status

                if lucky:
                    outcome = random.choice(["2x", "3x"])
                    multiplier = 2 if outcome == "2x" else 3
                    winnings = bet * multiplier
                    update_balance(user_id, winnings - bet)

                    # Disguised lucky message (Realistic results)
                    result_msg = (
                        f"🃏 Your cards: 10,11 (Total: **21**)\n"
                        f"🎲 Dealer's cards: 6,10 (Total: **16**)\n"
                        f"🎉 You won **{winnings - bet}** coins!"
                    )
                    await message.reply(result_msg)
                    return

                # Regular Blackjack game logic
                def draw_card():
                    cards = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11]
                    return random.choice(cards)

                def calculate_hand(hand):
                    total = sum(hand)
                    aces = hand.count(11)
                    while total > 21 and aces:
                        total -= 10
                        aces -= 1
                    return total

                player_hand = [draw_card(), draw_card()]
                dealer_hand = [draw_card(), draw_card()]

                player_total = calculate_hand(player_hand)
                dealer_total = calculate_hand(dealer_hand)

                while dealer_total < 17:
                    dealer_hand.append(draw_card())
                    dealer_total = calculate_hand(dealer_hand)

                result_msg = (
                    f"🃏 Your cards: {player_hand} (Total: {player_total})\n"
                    f"🎲 Dealer's cards: {dealer_hand} (Total: {dealer_total})\n"
                )

                if player_total > 21:
                    update_balance(user_id, -bet)
                    result_msg += f"💥 You busted and lost **{bet}** coins!"
                elif dealer_total > 21 or player_total > dealer_total:
                    update_balance(user_id, bet)
                    result_msg += f"🎉 You won **{bet}** coins!"
                elif player_total < dealer_total:
                    update_balance(user_id, -bet)
                    result_msg += f"😔 You lost **{bet}** coins!"
                else:
                    result_msg += "🤝 It's a tie! Your bet was returned."

                await message.reply(result_msg)






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
                await message.reply("❌ Usage: !loan <amount>")
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
            deadline = int(time.time()) + 86400
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
                await message.reply("❌ Usage: !payloan <amount>")
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
                await message.reply("Use !rob @user")
                return
            result = rob_user(user_id, str(message.mentions[0].id))
            await message.reply(result)


        if message.content.startswith("!redeem"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return
            if len(parts) < 2:
                await message.reply("Use !redeem <code>")
                return
            code = parts[1]
            reward = redeem_code(user_id, code)
            if reward:
                await message.reply(f"🟢 | You redeemed {code} and received {reward} coins!")
            else:
                await message.reply("🔴 | This code is either invalid or has been already used!")


        if message.content.startswith("!transfer"):
            if message.guild is None:
                await message.reply("❌ | This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return
            if len(parts) < 3 or not message.mentions or not parts[2].isdigit():
                await message.reply("Use !transfer @user <amount>")
                return
            result = pay_user(user_id, str(message.mentions[0].id), int(parts[2]))
            xp_message = update_xp(user_id, 6)
            await message.reply(result)

        if message.content.startswith(("!coinflip", "!cf")):
            if message.guild is None:
                await message.reply("❌ | This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return

            user_id = message.author.id
            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}
            loan_deadline = user_data.get("loan_deadline", 0)
            current_loan = user_data.get("loan", 0)
            loan_paid = user_data.get("loan_paid", 0)

            if loan_deadline > 0 and time.time() > loan_deadline and (current_loan - loan_paid) > 0:
                await message.reply("❌ You failed to repay your loan on time! You cannot use some commands until you **fully repay** your loan.")
                return

            parts = message.content.split()
            if len(parts) < 3:
                await message.reply("Usage: !coinflip <amount/all> <heads/tails>")
                return

            choice = parts[2].lower()
            if choice not in ["heads", "tails"]:
                await message.reply("Usage: !coinflip <amount/all> <heads/tails>")
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

            # Check Firebase for lucky status
            lucky = user_data.get("lucky", False)  # Check the lucky status from Firebase

            if lucky:
                result = choice  # Force win if the user is lucky
            else:
                result = random.choice(["heads", "tails"])  # Regular coin flip

            if result == choice:
                update_balance(user_id, bet)
                xp_message = update_xp(user_id, 5)
                await message.reply(f"✅ The coin landed on **{result}**! You won **{bet}** coins! New balance: {get_balance(user_id)} coins.")
            else:
                update_balance(user_id, -bet)
                await message.reply(f"❌ The coin landed on **{result}**! You lost **{bet}** coins! New balance: {get_balance(user_id)} coins.")



        if message.content.startswith("!dice"):
            if message.guild is None:
                await message.reply("❌ | This command can only be used in a server!")
                return

            user_id = message.author.id

            if is_banned(user_id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return

            parts = message.content.split()
            if len(parts) != 3 or (not parts[1].isdigit() and parts[1].lower() != "all") or not parts[2].isdigit():
                await message.reply("Usage: `!dice <amount> <number 1-6>` or `!dice all <number 1-6>`")
                return

            balance = get_balance(user_id)
            if parts[1].lower() == "all":
                bet = balance
            else:
                bet = int(parts[1])

            guess = int(parts[2])

            if bet <= 0 or bet > balance or guess < 1 or guess > 6:
                await message.reply("❌ Invalid bet or number.")
                return

            # Check Firebase for lucky status
            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}
            lucky = user_data.get("lucky", False)  # This is where you check the lucky status

            if lucky:
                roll = guess  # Guaranteed win for lucky users
            else:
                roll = random.randint(1, 6)  # Regular dice roll

            if roll == guess:
                winnings = bet * 6
                update_balance(user_id, winnings)
                await message.reply(f"🎲 The dice rolled **{roll}**! You guessed correctly and won **{winnings}** coins!")
            else:
                update_balance(user_id, -bet)
                await message.reply(f"🎲 The dice rolled **{roll}**. You lost **{bet}** coins!")







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
