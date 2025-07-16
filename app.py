import os
import discord
import google.generativeai as genai
import aiosqlite
import asyncio

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DB_PATH = "chat_memory.db"
MAX_HISTORY = 200

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-pro")


async def init_db():
    db = await aiosqlite.connect(DB_PATH)
    await db.execute(
        "CREATE TABLE IF NOT EXISTS messages ("
        "msg_id TEXT PRIMARY KEY, author TEXT, content TEXT, ts REAL)"
    )
    await db.commit()
    return db


@client.event
async def on_ready():
    client.db = await init_db()
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message):
    if message.author.bot:
        return

    await client.db.execute(
        "INSERT OR IGNORE INTO messages (msg_id, author, content, ts) VALUES (?,?,?,?)",
        (str(message.id), message.author.name, message.content, message.created_at.timestamp())
    )
    await client.db.commit()

    if message.content.startswith("!ask"):
        question = message.content[len("!ask"):].strip()
        if not question:
            return await message.channel.send("❌ Please ask something after `!ask`.")
        system = "You are ASCENDANCY AI, a witty and argumentative Discord bot. Answer concisely and factually."
        prompt = f"{system}\nUser: {question}\nAI:"
    else:
        cursor = await client.db.execute(
            "SELECT author, content FROM messages ORDER BY ts DESC LIMIT ?",
            (MAX_HISTORY,)
        )
        rows = await cursor.fetchall()
        await cursor.close()
        rows.reverse()
        context = "\n".join(f"{author}: {content}" for author, content in rows)
        system = "You are ASCENDANCY AI, a witty and argumentative Discord bot. Join the conversation."
        prompt = f"{system}\n{context}\nAI:"

    await message.channel.send("🤖 Thinking…")
    try:
        resp = model.generate_content(prompt)
        text = getattr(resp, "text", None) or (resp.candidates and resp.candidates[0].text)
        if not text:
            raise RuntimeError("No response from Gemini")
        await message.channel.send(text[:2000])
    except Exception as e:
        await message.channel.send(f"⚠️ Error: {e}")


async def main():
    await client.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
