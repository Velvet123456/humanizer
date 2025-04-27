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
import string
import asyncio


app = Flask(__name__)
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("Error: DISCORD_TOKEN is not set in .env file")
    exit(1)

@app.route('/')
def home():
    return "ntsbot is successfully running! with no errors."

cred = credentials.Certificate("rohackersz-firebase-adminsdk-fbsvc-ef11a7abad.json")
firebase_admin.initialize_app(cred, {
    "databaseURL": "https://rohackersz-default-rtdb.firebaseio.com/"
})
BLACKLISTED_IDS = []
ban_ref = db.reference("economyban")

def is_banned(user_id: int) -> bool:
    banned_users = ban_ref.get() or {}
    return str(user_id) in banned_users


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

def get_last_weeklyclaim(user_id):
    ref = db.reference(f"users/{user_id}/last_weekly")
    return ref.get() or 0

def set_last_weeklyclaim(user_id, timestamp):
    ref = db.reference(f"users/{user_id}/last_weekly")
    ref.set(timestamp)

def get_bank_limit(user_id):
    level = get_level(user_id)

    bank_limit = 500000 + (level - 1) * 1000000
    return bank_limit

def update_bank_balance(user_id, amount):
    user_ref = db.reference(f"users/{user_id}/bank")


    current_balance = user_ref.get()
    new_balance = current_balance + amount 


    user_ref.set(new_balance)


def format_number(number):
    if number >= 10**27:
        value = number / 10**27
        suffix = "O"  # Octillion
    elif number >= 10**24:
        value = number / 10**24
        suffix = "N"  # Nonillion
    elif number >= 10**21:
        value = number / 10**21
        suffix = "S"  # Septillion
    elif number >= 10**18:
        value = number / 10**18
        suffix = "V"  # Sextillion
    elif number >= 10**15:
        value = number / 10**15
        suffix = "Q"  # Quadrillion
    elif number >= 10**12:
        value = number / 10**12
        suffix = "T"  # Trillion
    elif number >= 10**9:
        value = number / 10**9
        suffix = "B"  # Billion
    elif number >= 10**6:
        value = number / 10**6
        suffix = "M"  # Million
    elif number >= 10**3:
        value = number / 10**3
        suffix = "K"  # Thousand
    else:
        return str(number)

    return f"{int(value) if value.is_integer() else round(value, 1)}{suffix}"







def get_bank_balance(user_id):
    user_ref = db.reference(f"users/{user_id}")
    user_data = user_ref.get()

    if user_data and "bank" in user_data:
        return user_data["bank"]
    return 0 

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
    if random.randint(1, 100) <= 30:
        stolen_amount = int(victim_balance * 0.28)
        update_balance(robber_id, stolen_amount)
        update_balance(victim_id, -stolen_amount)
        return f"💰 You successfully robbed {stolen_amount} coins from <@{victim_id}>!"
    lost_amount = int(robber_balance * 0.20)
    update_balance(robber_id, -lost_amount)
    return f"❌ You failed to rob <@{victim_id}> and lost {lost_amount} coins!"


def add_user_to_lbadd(user_id):
    lbadd_ref = db.reference("lbadd")
    lbadd_ref.child(user_id).set(True)


def update_leaderboard():
    leaderboard_ref = db.reference("leaderboard")
    lbadd_ref = db.reference("lbadd")


    leaderboard_data = leaderboard_ref.get() or {}
    lbadd_data = lbadd_ref.get() or {}


    for user_id in lbadd_data:
        if user_id not in leaderboard_data:
            leaderboard_data[user_id] = 0


    sorted_leaderboard = dict(sorted(leaderboard_data.items(), key=lambda item: item[1], reverse=True))


    leaderboard_ref.set(sorted_leaderboard)

def pay_user(sender_id, receiver_id, amount):
    sender_balance = get_balance(sender_id)
    if amount <= 0 or sender_balance < amount:
        return "❌ Invalid amount!"
    update_balance(sender_id, -amount)
    update_balance(receiver_id, amount)
    return f"✅ You sent {amount} coins to <@{receiver_id}>!"

async def get_server_leaderboard(guild):
    users_ref = db.reference("users")
    lbadd_ref = db.reference("lbadd")
    all_users = users_ref.get() or {}
    lbadd_users = lbadd_ref.get() or {}

    if not all_users and not lbadd_users:
        return []

    leaderboard_data = {}


    for user_id in lbadd_users:
        if str(user_id) not in BLACKLISTED_IDS:
            leaderboard_data[str(user_id)] = 0


    for member in guild.members:
        user_id = str(member.id)
        if not member.bot and user_id not in BLACKLISTED_IDS:
            balance = get_balance(user_id) or 0
            leaderboard_data[user_id] = balance


    sorted_leaderboard = sorted(
        leaderboard_data.items(), key=lambda x: x[1], reverse=True
    )[:7]

    final_result = []
    for user_id, balance in sorted_leaderboard:
        member = guild.get_member(int(user_id))
        if member: 
            final_result.append((member.name, balance))

    return final_result


def get_global_leaderboard():
    users_ref = db.reference("users")
    all_users = users_ref.get()

    if not all_users:
        return []

    leaderboard = []
    for user_id, data in all_users.items():
        if str(user_id) in BLACKLISTED_IDS:
            continue
        balance = data.get("balance", 0)

        leaderboard.append((f"<@{user_id}>", balance))

    return sorted(leaderboard, key=lambda x: x[1], reverse=True)[:7]



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
        return f"\n🎉 You leveled up to {new_level}! You received {new_level * 100} coins!"
    db.reference(f"users/{user_id}/xp").set(new_xp)
    return None

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

        user_ref = db.reference(f"users/{message.author.id}")
        user_data = user_ref.get()

        if not user_data or "bank" not in user_data:
            user_ref.update({"bank": 0})


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
            last_gamble = user_data.get("last_gamble", 0)
            loan_deadline = user_data.get("loan_deadline", 0)
            current_loan = user_data.get("loan", 0)
            loan_paid = user_data.get("loan_paid", 0)
            is_lucky = user_data.get("lucky", False)
            is_unlucky = user_data.get("unlucky", False)

            if loan_deadline > 0 and time.time() > loan_deadline and (current_loan - loan_paid) > 0:
                await message.reply("❌ You failed to repay your loan on time! You cannot use some commands until you **fully repay** your loan.")
                return

            if time.time() - last_gamble < 5:
                remaining = int(5 - (time.time() - last_gamble))
                await message.channel.send(f"⏳ You can use `!gamble` again in {remaining}s.")
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

            if is_unlucky:
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
                user_ref.update({"last_gamble": time.time()})
                return

            if is_lucky:
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
                user_ref.update({"last_gamble": time.time()})
                return

            roll = random.random()
            if roll <= 0.28:
                chosen = random.choice(emojis)
                slot_result = [chosen, chosen, chosen]
                winnings = bet * 3
                update_balance(user_id, winnings)
                await message.reply(f"{slot_result[0]} {slot_result[1]} {slot_result[2]} You won **3x +{winnings}** (Balance: {get_balance(user_id)})")
            elif roll <= 0.40:
                chosen = random.choice(emojis)
                others = [e for e in emojis if e != chosen]
                third = random.choice(others)
                pos = random.randint(0, 2)
                slot_result = [chosen, chosen, chosen]
                slot_result[pos] = third
                winnings = bet * 2
                update_balance(user_id, winnings)
                await message.reply(f"{slot_result[0]} {slot_result[1]} {slot_result[2]} You won **2x +{winnings}** (Balance: {get_balance(user_id)})")
            else:
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

            user_ref.update({"last_gamble": time.time()})


        if message.content.startswith("!withdraw"):
                parts = message.content.split()
                if len(parts) < 2:
                    await message.reply("❌ Please specify an amount to withdraw!")
                    return

                amount_str = parts[1]
                user_id = str(message.author.id)

                bank_balance = get_bank_balance(user_id)
                wallet_balance = get_balance(user_id)

                if amount_str.lower() == "all":
                    amount = bank_balance
                elif amount_str.isdigit():
                    amount = int(amount_str)
                else:
                    await message.reply("❌ Please provide a valid amount!")
                    return

                if amount <= 0:
                    await message.reply("❌ Amount must be greater than zero!")
                    return

                if amount > bank_balance:
                    await message.reply(f"❌ You don't have enough bank balance! You only have {format_number(bank_balance)}.")
                    return


                update_bank_balance(user_id, -amount)
                update_balance(user_id, amount)

                await message.reply(f"✅ Successfully withdrew {format_number(amount)} from your bank into your wallet!")

        if message.content.startswith("!bank remove"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return


            if len(message.content.split()) < 2:
                await message.reply("❌ You must mention the user to remove from your bank. Usage: `!bank remove @user`")
                return


            mentioned_user = message.mentions[0] if message.mentions else None

            if not mentioned_user:
                await message.reply("❌ You must mention a user to remove from your bank.")
                return

            user_id = message.author.id
            bank_ref = db.reference("banks")

            banks = bank_ref.get() or {}
            user_bank = None
            for bank_name, bank_data in banks.items():
                if user_id in bank_data.get("members", []):
                    user_bank = (bank_name, bank_data)
                    break

            if not user_bank:
                await message.reply("❌ You are not part of any bank!")
                return

            bank_name, bank_data = user_bank
            owner_id = bank_data.get("owner")
            members = bank_data.get("members", [])

            if message.author.id != owner_id:
                await message.reply("❌ Only the bank owner can remove members.")
                return

            if mentioned_user.id == owner_id:
                await message.reply("❌ You cannot remove yourself, as you are the bank owner!")
                return

            if mentioned_user.id not in members:
                await message.reply("❌ The mentioned user is not a member of your bank.")
                return

            members.remove(mentioned_user.id)
            bank_ref.child(bank_name).update({
                "members": members
            })

            victim_ref = db.reference(f"users/{mentioned_user.id}")
            victim_ref.update({"isinclan": False})

            await message.reply(f"✅ {mentioned_user.mention} has been removed from the bank.")

        if message.content.startswith("!bank delete"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return

            if len(message.content.split()) < 2:
                await message.reply("❌ You must specify the bank name. Usage: `!bank delete <bank_name>`")
                return

            bank_name = message.content.split("!bank delete ", 1)[1].strip()

            bank_ref = db.reference(f"banks/{bank_name}")
            bank_data = bank_ref.get()

            if not bank_data:
                await message.reply(f"❌ No bank found with the name {bank_name}.")
                return

            owner_id = bank_data.get("owner")
            members = bank_data.get("members", [])

            if message.author.id != owner_id:
                await message.reply("❌ Only the bank owner can delete the bank.")
                return

            owner_ref = db.reference(f"users/{owner_id}")
            owner_ref.update({"isinclan": False})

            for member_id in members:
                member_ref = db.reference(f"users/{member_id}")
                member_ref.update({"isinclan": False})

            bank_ref.delete()
            await message.reply(f"✅ Bank **{bank_name}** has been successfully deleted. All members and the owner have been removed from the bank.")


        if message.content.startswith("!bank create"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return

            if len(message.content.split()) < 2:
                await message.reply("❌ You must provide a bank name! Usage: `!create <bank_name>`")
                return

            user_id = message.author.id
            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get()

            is_in_clan = user_data.get("isinclan", False)

            if is_in_clan:
                await message.reply("❌ You are already in a bank and cannot create another one.")
                return

            user_balance = user_data.get("balance", 0)

            if user_balance >= 100000000000: 
                bank_name = message.content.split("!bank create ", 1)[1].strip()

                bank_ref = db.reference(f"banks/{bank_name}")
                bank_data = bank_ref.get()
                if bank_data:
                    await message.reply(f"❌ A bank with the name {bank_name} already exists!")
                    return

                invite_code = ''.join(random.choices(string.ascii_letters + string.digits, k=7))

                footstamp_code = str(int(time.time()))

                user_ref.update({
                    "balance": user_balance - 100000000000,
                    "isinclan": True
                })


                bank_ref.set({
                    'owner': user_id,
                    'members': [user_id],
                    'name': bank_name,
                    'invitecode': invite_code,
                    'serverpool': "0",
                    'created': footstamp_code
                })

                await message.reply(f"🏦 Bank **{bank_name}** created successfully!\n🔑 Invite Code: `{invite_code}`\n100B has been deducted from your balance.")
            else:
                await message.reply("❌ You don't have enough balance to create a bank. You need 100B.")

            await asyncio.sleep(1)

        if message.content.startswith("!bank deposite"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return

            user_id = message.author.id
            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}

            if not user_data.get("isinclan", False):
                await message.reply("❌ You are not in a bank!")
                return


            banks_ref = db.reference("banks")
            banks = banks_ref.get() or {}
            user_bank = None
            for bank_name, bank_data in banks.items():
                if user_id in bank_data.get("members", []):
                    user_bank = (bank_name, bank_data)
                    break

            if not user_bank:
                await message.reply("❌ Bank not found.")
                return

            bank_name, bank_data = user_bank
            bank_ref = db.reference(f"banks/{bank_name}")

            try:
                amount_str = message.content.split("!bank deposite",1)[1].strip()
            except IndexError:
                await message.reply("❌ You must specify an amount to deposit! Example: `!bank deposite 1000` or `!bank deposite all`")
                return

            user_balance = user_data.get("balance", 0)
            vault = int(bank_data.get("vault", 0))

            if amount_str.lower() == "all":
                amount = user_balance
            else:
                if not amount_str.isdigit():
                    await message.reply("❌ Invalid amount.")
                    return
                amount = int(amount_str)

            if amount <= 0:
                await message.reply("❌ Amount must be greater than 0.")
                return

            if user_balance < amount:
                await message.reply("❌ You don't have enough balance to deposit!")
                return

            user_ref.update({
                "balance": user_balance - amount
            })
            bank_ref.update({
                "vault": vault + amount
            })

            await message.reply(f"🏦 Successfully deposited **{amount}** coins into your bank vault!")
            await asyncio.sleep(1)

        if message.content.startswith("!bank withdraw"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return

            user_id = message.author.id
            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}

            if not user_data.get("isinclan", False):
                await message.reply("❌ You are not in a bank!")
                return

            banks_ref = db.reference("banks")
            banks = banks_ref.get() or {}
            user_bank = None
            for bank_name, bank_data in banks.items():
                if user_id in bank_data.get("members", []):
                    user_bank = (bank_name, bank_data)
                    break

            if not user_bank:
                await message.reply("❌ Bank not found.")
                return

            bank_name, bank_data = user_bank
            bank_ref = db.reference(f"banks/{bank_name}")

            try:
                amount_str = message.content.split("!bank withdraw",1)[1].strip()
            except IndexError:
                await message.reply("❌ You must specify an amount to withdraw! Example: `!bank withdraw 1000` or `!bank withdraw all`")
                return

            user_balance = user_data.get("balance", 0)
            vault = int(bank_data.get("vault", 0))

            if amount_str.lower() == "all":
                amount = vault
            else:
                if not amount_str.isdigit():
                    await message.reply("❌ Invalid amount.")
                    return
                amount = int(amount_str)

            if amount <= 0:
                await message.reply("❌ Amount must be greater than 0.")
                return

            if vault < amount:
                await message.reply("❌ There isn't enough money in the vault!")
                return

            user_ref.update({
                "balance": user_balance + amount
            })
            bank_ref.update({
                "vault": vault - amount
            })

            await message.reply(f"🏦 Successfully withdrew **{amount}** coins from your bank vault!")
            await asyncio.sleep(1)

        if message.content.startswith("!banks"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return

            banks_ref = db.reference("banks")
            banks_data = banks_ref.get() or {}

            bank_vaults = []

            for bank_name, bank_data in banks_data.items():
                vault = bank_data.get("vault", 0)
                bank_vaults.append((bank_name, vault))

            bank_vaults.sort(key=lambda x: x[1], reverse=True)

            top_banks = bank_vaults[:5]

            if not top_banks:
                await message.reply("❌ No banks found.")
                return


            bank_list = "🏦 **Top 5 Banks**\n"
            for idx, (bank_name, vault) in enumerate(top_banks, 1):
                formatted_vault = format_number(vault)
                bank_list += f"{idx}. **{bank_name}** ({formatted_vault})\n"

            await message.reply(bank_list)
            await asyncio.sleep(1)

        if message.content.startswith("!bank info"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return

            user_id = message.author.id
            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get()

            if not user_data or not user_data.get("isinclan", False):
                await message.reply("❌ You are not in a bank!")
                return

            banks_ref = db.reference("banks")
            banks = banks_ref.get() or {}
            user_bank = None
            for bank_name, bank_data in banks.items():
                if user_id in bank_data.get("members", []):
                    user_bank = (bank_name, bank_data)
                    break

            if not user_bank:
                await message.reply("❌ Bank not found.")
                return

            bank_name, bank_data = user_bank
            owner_id = bank_data.get("owner")
            owner_ref = db.reference(f"users/{owner_id}")
            owner_data = owner_ref.get()

            if owner_data is None:
                await message.reply(f"❌ Unable to fetch owner data for bank **{bank_name}**. Owner's profile might not exist. Please check if the owner data exists in Firebase.")
                return

            owner_username = owner_data.get("username", "Unknown")

            footstamp_code = bank_data.get("created", "Unknown")

            vault = bank_data.get("vault", 0)
            members = bank_data.get("members", [])
            member_count = len(members)
            invite_code = bank_data.get("invitecode", "N/A")

            if user_id == owner_id:
                user_role = "Owner"
            else:
                user_role = "Member"

            info_message = f"🏦 **Bank Info for {bank_name}:**\n"
            info_message += f"**Owner:** <@{owner_id}>\n"
            info_message += f"**Role:** {user_role}\n"
            info_message += f"**Vault Balance:** {vault} coins\n"
            info_message += f"**Members:** {member_count} member(s)\n"
            info_message += f"**Invite Code:** `{invite_code}`\n"
            info_message += f"**Bank Created:** <t:{footstamp_code}:f>\n"
            await message.reply(info_message)
            await asyncio.sleep(1)

        if message.content.startswith("!bank leave"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return

            user_id = message.author.id
            bank_ref = db.reference("banks")
            banks = bank_ref.get() or {}

            user_bank = None
            for bank_name, bank_data in banks.items():
                if user_id in bank_data.get("members", []):
                    user_bank = (bank_name, bank_data)
                    break

            if not user_bank:
                await message.reply("❌ You are not part of any bank!")
                return

            bank_name, bank_data = user_bank
            members = bank_data.get("members", [])

            if user_id not in members:
                await message.reply("❌ You are not a member of this bank!")
                return

            members.remove(user_id)
            bank_ref.child(bank_name).update({
                "members": members
            })

            user_ref = db.reference(f"users/{user_id}")
            user_ref.update({"isinclan": False})

            await message.reply(f"✅ You have successfully left the bank **{bank_name}**.")

        if message.content.startswith("!bank join"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return

            parts = message.content.strip().split(maxsplit=2)
            if len(parts) != 3:
                await message.reply("❌ Usage: `!bank join <invitecode>`")
                return

            invite_code = parts[2]
            user_id = message.author.id

            banks_ref = db.reference("banks")
            banks = banks_ref.get() or {}
            bank_name = None
            for name, data in banks.items():
                if data.get("invitecode") == invite_code:
                    bank_name = name
                    break

            if not bank_name:
                await message.reply("❌ Invalid invite code.")
                return

            bank_ref = db.reference(f"banks/{bank_name}")
            bank_data = bank_ref.get()

            if user_id in bank_data.get("members", []):
                await message.reply("❌ You are already a member of this bank.")
                return

            if user_id in bank_data.get("pending_requests", []):
                await message.reply("❌ You have already requested to join this bank.")
                return

            pending = bank_data.get("pending_requests", [])
            pending.append(user_id)
            bank_ref.update({"pending_requests": pending})

            await message.reply(f"✅ Request sent! You have requested to join the bank **{bank_name}**.")

            owner_id = bank_data.get("owner")
            try:
                owner = await client.fetch_user(owner_id)
                dm = await owner.create_dm()
                prompt = await dm.send(
                    f"👤 User {message.author.name}#{message.author.discriminator} wants to join your bank **{bank_name}**.\n"
                    f"React with ✅ to approve."
                )
                await prompt.add_reaction("✅")

                def check(reaction, user):
                    return (
                        user.id == owner_id
                        and str(reaction.emoji) == "✅"
                        and reaction.message.id == prompt.id
                    )

                try:
                    await client.wait_for("reaction_add", timeout=3600.0, check=check)

                    bank_data = bank_ref.get()
                    pending = bank_data.get("pending_requests", [])
                    if user_id in pending:
                        pending.remove(user_id)
                        members = bank_data.get("members", [])
                        members.append(user_id)
                        bank_ref.update({"pending_requests": pending, "members": members})

                        user_ref = db.reference(f"users/{user_id}")
                        user_ref.update({"isinclan": True})

                        await dm.send(f"✅ {message.author.name} has been added to the bank.")
                        try:
                            await message.author.send(f"🎉 Your request to join **{bank_name}** has been approved!")
                        except Exception:
                            pass
                    else:
                        await dm.send("❌ The user is no longer in the pending requests.")
                except asyncio.TimeoutError:
                    await dm.send("⏰ Approval timed out.")
            except Exception as e:
                print(f"Error notifying the owner: {e}")
                try:
                    await message.author.send("⚠️ Could not notify the bank owner. Please try again later.")
                except Exception:
                    pass

            await asyncio.sleep(1)


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


            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}
            lucky = user_data.get("lucky", False) 

            if lucky:
                amount = random.randint(500, 1200) 
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


            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}
            lucky = user_data.get("lucky", False) 

            if lucky:

                if color == "green":
                    roll = 0  
                    multiplier = 14
                elif color == "red":
                    roll = random.choice([1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31, 33, 35])  
                    multiplier = 2
                elif color == "black":
                    roll = random.choice([2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36])  
                    multiplier = 2
                winnings = bet * multiplier
                update_balance(user_id, winnings - bet)

                await message.reply(f"🎉 It landed on **{roll}**! You won **{winnings}** coins! (Balance: {get_balance(user_id)})")
                return
            else:

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
                "1. !profile [@user] - Check profile.\n"
                "2. !rules - View ntsbot's rules.\n"
                "3. !work - Just Work.\n"
                "4. !daily - Claim daily rewards.\n"
                "5. !weekly - Claim weekly rewards.\n"
                "6. !gamble <amount/all> - Gamble coins.\n"
                "7. !coinflip <amount> <heads/tails> - Coinflip.\n"
                "8. !crime - Commit a crime.\n"
                "9. !roulette <red/black> <amount> - Play roulette.\n"
                "10. !blackjack <amount> - Play a game of blackjack.\n"
                "11. !loan <amount> - Take loan from the bank.\n"
                "12. !payloan <amount> - Pay back the loan amount.\n"
                "13. !deposite <amount> - Deposite cash to the bank.\n"
                "14. !withdraw <amount> - Withdraw cash from the bank.\n"
                "15. !dice <amount> <number> - Roll dice for prize.\n"
                "16. !redeem <code> - Redeem a code.\n"
                "17. !rob @user - Steal coins from others.\n"
                "18. !transfer @user <amount> - Transfer coins.\n"
                "19. !leaderboard - Check The Server Leaderboard.\n"
                "**Bank Related Commands**\n"
                "20. !bank create: Creates a new bank for the user.\n"
                "21. !bank delete: Delete the bank (Owner only).\n"
                "22. !bank remove: Removes a user from the Bank (Owner Only)\n"
                "23. !bank join: Request and seek aprooval to join a bank.\n"
                "25. !bank leave: Allows a user to leave the bank.\n"
                "26. !bank info: Find information about the bank.\n"
            )
        if message.content.startswith("!rules"):
            if message.guild is None:
                await message.reply("❌ | This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return
            await message.reply(
                "**ntsbot Rules:**\n"
                "```diff\n"
                "- No spamming commands. (Ban)\n"
                "- Do not abuse the bot in any ways. (Temp/Perm Ban)\n"
                "- No Abusing the Bank feature. (Temp/Perm Ban)\n"
                "- No bad characters allowed in Bank Names.. (Temp/Perm Ban)\n"
                "+ Enjoy ntsbot!```\n"
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


                user_ref = db.reference(f"users/{user_id}")
                user_data = user_ref.get() or {}
                lucky = user_data.get("lucky", False)  

                if lucky:
                    outcome = random.choice(["2x", "3x"])
                    multiplier = 2 if outcome == "2x" else 3
                    winnings = bet * multiplier
                    update_balance(user_id, winnings - bet)


                    result_msg = (
                        f"🃏 Your cards: 10,11 (Total: **21**)\n"
                        f"🎲 Dealer's cards: 6,10 (Total: **16**)\n"
                        f"🎉 You won **{winnings - bet}** coins!"
                    )
                    await message.reply(result_msg)
                    return


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



        if message.content.startswith("!deposit"):
            parts = message.content.split()
            if len(parts) != 2 or (not parts[1].isdigit() and parts[1].lower() != "all"):
                await message.reply("Usage: `!deposit <amount/all>`")
                return

            balance = user_data.get("balance", 0)
            bank = user_data.get("bank", 0)
            level = user_data.get("level", 1)
            bank_limit = 500000 + ((level - 1) * 1000000)

            if parts[1].lower() == "all":
                deposit_amount = min(balance, bank_limit - bank)
            else:
                deposit_amount = int(parts[1])
                if deposit_amount > balance:
                    await message.reply("❌ You don't have that much money.")
                    return
                if deposit_amount + bank > bank_limit:
                    await message.reply("❌ This deposit would exceed your bank limit.")
                    return

            if deposit_amount <= 0:
                await message.reply("❌ Invalid deposit amount.")
                return

            update_balance(user_id, -deposit_amount)
            user_ref.update({"bank": bank + deposit_amount})
            await message.reply(f"✅ Deposited {deposit_amount} coins to bank! 🏦")


        if message.content.startswith("!profile"):
                if message.guild is None:
                    await message.reply("❌ This command can only be used in a server!")
                    return

                target = message.mentions[0] if message.mentions else message.author
                target_id = str(target.id)

                balance = get_balance(target_id)
                bank_balance = get_bank_balance(target_id)
                bank_limit = get_bank_limit(target_id)
                level = get_level(target_id)
                xp = get_xp(target_id)
                xp_needed = 100 + (level - 1) * 150


                formatted_balance = format_number(balance)
                formatted_bank_balance = format_number(bank_balance)
                formatted_bank_limit = format_number(bank_limit)

                profile_msg = (
                    f"{target.name}'s Profile:\n\n"
                    f"1. Balance: {formatted_balance}\n"
                    f"2. Bank Balance: {formatted_bank_balance}/{formatted_bank_limit}\n"
                    f"3. Level: {level}\n"
                    f"4. XP: {xp}/{xp_needed}"
                )

                await message.reply(profile_msg)



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
                "dancer", "robber", "byfron developer","officer","lawyer","begger","hyperion staff","robloxian","youtuber"
            ]
            job = random.choice(jobs)
            earnings = random.randint(100, 500)
            update_balance(user_id, earnings)
            xp_message = update_xp(user_id, 10)
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
                await message.reply("Already claimed!")
            else:
                update_balance(user_id, 500)
                set_last_claim(user_id, int(time.time()))
                xp_message = update_xp(user_id, 30)
                await message.reply(f"👴 | Claimed your daily 500 coins! {xp_message if xp_message else ''}")

        if message.content.startswith("!weekly"):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return
            if int(time.time()) - get_last_weeklyclaim(user_id) < 604800:
                await message.reply("Already claimed!")
            else:
                update_balance(user_id, 5000)
                set_last_weeklyclaim(user_id, int(time.time()))
                xp_message = update_xp(user_id, 150)
                await message.reply(f"👴 | Claimed your weekly 5000 coins! {xp_message if xp_message else ''}")


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
            if amount <= 0 or amount > 5000:
                await message.reply("❌ You can only take a loan between 1 and 5000 coins!")
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


            lucky = user_data.get("lucky", False)  

            if lucky:
                result = choice 
            else:
                result = random.choice(["heads", "tails"])  

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


            user_ref = db.reference(f"users/{user_id}")
            user_data = user_ref.get() or {}
            lucky = user_data.get("lucky", False) 

            if lucky:
                roll = guess 
            else:
                roll = random.randint(1, 6)

            if roll == guess:
                winnings = bet * 6
                update_balance(user_id, winnings)
                await message.reply(f"🎲 The dice rolled **{roll}**! You guessed correctly and won **{winnings}** coins!")
            else:
                update_balance(user_id, -bet)
                await message.reply(f"🎲 The dice rolled **{roll}**. You lost **{bet}** coins!")




        if message.content.startswith(("!leaderboard", "!lb")):
            if message.guild is None:
                await message.reply("❌ This command can only be used in a server!")
                return
            if is_banned(message.author.id):
                await message.reply("❌ | You are **banned** from using this bot.")
                return

            leaderboard = await get_server_leaderboard(message.guild) 
            if not leaderboard:
                await message.reply("❌ | No users found in this server!")
                return

            await message.reply("**🏆 Server Leaderboard**\n" + 
                "\n".join(f"{i+1}. {name} - {format_number(bal)} coins" for i, (name, bal) in enumerate(leaderboard)))






if __name__ == "__main__":
    def run_flask():
        app.run(host="0.0.0.0", port=8080)
    Thread(target=run_flask).start()
    print("Flask server is running.")
    client = SelfBot()
    client.run(TOKEN)
