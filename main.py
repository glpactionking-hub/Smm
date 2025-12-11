# requirements: aiogram==3.x (latest)
# Create a bot token with @BotFather and replace BOT_TOKEN.
# Note: when using getUpdates/setWebhook you must request reaction updates via allowed_updates
# (many libraries surface that via BotOptions / allowed_updates param).

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import MessageReactionUpdated, Message, ChatActions
from aiogram.filters import BaseFilter

BOT_TOKEN = "8219608540:AAE9vOFgQMH-FfjuEWEOQY0M5ig4tsZdA2w"
MULTIPLY_FACTOR = 5  # कितनी बार repeat करना है

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# aiogram provides a handler type for MessageReactionUpdated updates.
# If your aiogram version lacks direct type, use raw update handling or upgrade aiogram.

@dp.message_reaction_updated()  # triggers on reaction add/remove
async def on_reaction(updated: MessageReactionUpdated):
    try:
        chat_id = updated.chat.id
        msg_id = updated.message_id
        user = updated.from_user  # जो user reaction किया
        # old_reaction / new_reaction fields exist — pick the new reaction
        new_reactions = getattr(updated, "new_reaction", None) or getattr(updated, "reaction", None)
        # best-effort: get first emoji
        emoji = None
        if isinstance(new_reactions, list) and len(new_reactions):
            emoji = new_reactions[0].to_dict().get("emoji") if hasattr(new_reactions[0], "to_dict") else str(new_reactions[0])
        elif isinstance(new_reactions, str):
            emoji = new_reactions

        if not emoji:
            emoji = "👍"

        # Send a short reply that 'multiplies' the reaction (can't add reactions as bot)
        text = f"{emoji} " * MULTIPLY_FACTOR
        # Optionally mention who reacted:
        text = f"{user.full_name} reacted → {text}"

        await bot.send_message(chat_id=chat_id, reply_to_message_id=msg_id, text=text)
    except Exception as e:
        # basic error log
        print("Reaction handler error:", e)


async def main():
    # If you use long polling, request reaction updates explicitly:
    # some libraries let you pass allowed_updates when starting polling.
    # aiogram's polling accepts allowed_updates param in start_polling().
    await dp.start_polling(bot, allowed_updates=["message_reaction_updated", "message", "edited_message"])

if __name__ == "__main__":
    asyncio.run(main())