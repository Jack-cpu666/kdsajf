import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
import google.generativeai as genai
import aiosqlite
import asyncio

# ── Minimal HTTP server to satisfy Render’s port requirement ──
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def start_health_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=start_health_server, daemon=True).start()

# ── Discord + Gemini Bot ──
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
        q = message.content[len("!ask"):].strip()
        if not q:
            return await message.channel.send("❌ Please ask something after `!ask`.")
        prompt = (
            "You are ASCENDANCY AI, a witty and argumentative Discord bot. "
            "Answer the user’s question concisely and factually.\n"
            f"User: {q}\nAI:"
        )
    else:
        cursor = await client.db.execute(
            "SELECT author, content FROM messages ORDER BY ts DESC LIMIT ?",
            (MAX_HISTORY,)
        )
        rows = await cursor.fetchall()
        await cursor.close()
        rows.reverse()
        context = "\n".join(f"{a}: {c}" for a, c in rows)
        prompt = (
            "You are ASCENDANCY AI, a witty and argumentative Discord bot. "
            "Join the conversation: argue when appropriate, answer statements when needed.\n"
            f"{context}\nAI:"
        )

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
