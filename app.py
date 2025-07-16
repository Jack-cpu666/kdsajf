import discord
import google.generativeai as genai
import aiosqlite
import asyncio

DISCORD_TOKEN = "MTM5NDk3OTA0MzUzNDgzNTc0Mg.GzPI1j.eHZwHfnxXEAcrc6Z1NflNOhcb7rDPJwC0VTMC0"
GEMINI_API_KEY = "AIzaSyBqQQszYifOVY6396kV9lkEs1Tz3cSdmVo"
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

    # 1) Persist every message
    await client.db.execute(
        "INSERT OR IGNORE INTO messages (msg_id, author, content, ts) VALUES (?,?,?,?)",
        (str(message.id), message.author.name, message.content, message.created_at.timestamp())
    )
    await client.db.commit()

    # 2) Build prompt
    if message.content.startswith("!ask"):
        # standalone question—no history
        question = message.content[len("!ask"):].strip()
        if not question:
            return await message.channel.send("❌ Please ask something after `!ask`.")

        system = (
            "You are ASCENDANCY AI, a witty and argumentative Discord bot. "
            "Answer the user’s question concisely and factually."
        )
        prompt = f"{system}\nUser: {question}\nAI:"

    else:
        # free‐form chat—include last MAX_HISTORY for context
        cursor = await client.db.execute(
            "SELECT author, content FROM messages ORDER BY ts DESC LIMIT ?",
            (MAX_HISTORY,)
        )
        rows = await cursor.fetchall()
        await cursor.close()
        rows.reverse()  # oldest → newest

        context = "\n".join(f"{author}: {content}" for author, content in rows)
        system = (
            "You are ASCENDANCY AI, a witty and argumentative Discord bot. "
            "Join the conversation: argue when appropriate, answer statements when needed."
        )
        prompt = f"{system}\n{context}\nAI:"

    # 3) Send to Gemini
    await message.channel.send("🤖 Thinking…")
    try:
        resp = model.generate_content(prompt)
        text = getattr(resp, "text", None) or (resp.candidates and resp.candidates[0].text)
        if not text:
            raise RuntimeError("no response from Gemini")
        await message.channel.send(text[:2000])

    except Exception as e:
        # on error, fallback to summary of context only in free‐form
        if not message.content.startswith("!ask"):
            summary_prompt = (
                "Summarize the gist of the conversation below without quoting verbatim:\n"
                f"{context}\nSummary:"
            )
            try:
                resp2 = model.generate_content(summary_prompt)
                return await message.channel.send(resp2.text[:2000])
            except:
                pass

        await message.channel.send(f"⚠️ Error: {e}")


async def main():
    await client.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
