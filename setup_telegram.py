"""
Run this ONCE after creating your Telegram bot to get your chat_id.

Steps:
  1. Open Telegram → search @BotFather → send /newbot
  2. Follow prompts → copy the token it gives you
  3. Add to .env:  TELEGRAM_BOT_TOKEN=your_token_here
  4. Run: python setup_telegram.py
  5. It prints your chat_id — add to .env: TELEGRAM_CHAT_ID=your_id_here
"""
import sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from telegram_bot import get_token, get_updates, send_message

token = get_token()
if not token:
    print("ERROR: TELEGRAM_BOT_TOKEN not set in .env")
    print("  1. Message @BotFather on Telegram")
    print("  2. Send /newbot and follow prompts")
    print("  3. Copy the token into .env as TELEGRAM_BOT_TOKEN=xxx")
    sys.exit(1)

print(f"Token found: {token[:10]}...")
print()
print("Step 1: Send ANY message to your bot on Telegram now.")
input("Press Enter after you've messaged your bot... ")

updates = get_updates()
if not updates:
    print("No messages found. Make sure you sent a message to your bot first.")
    sys.exit(1)

for update in updates:
    msg = update.get("message", {})
    chat = msg.get("chat", {})
    chat_id = str(chat.get("id", ""))
    name = chat.get("first_name", "") + " " + chat.get("last_name", "")
    username = chat.get("username", "")
    text = msg.get("text", "")

    if chat_id:
        print(f"Found chat:")
        print(f"  Name:     {name.strip()}")
        print(f"  Username: @{username}")
        print(f"  Chat ID:  {chat_id}")
        print(f"  Message:  {text}")
        print()

        # Test send
        ok = send_message(chat_id, "✅ <b>Sports Betting Plus</b> connected successfully!\n\nYou'll receive daily picks and steam alerts here.", "HTML")
        if ok:
            print(f"Test message sent successfully!")
            print()
            print(f"Add this to your .env file:")
            print(f"  TELEGRAM_CHAT_ID={chat_id}")
        else:
            print("Failed to send test message. Check your token.")
        break
