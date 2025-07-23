import os
import re
import io
import json
import asyncio
import logging
import aiohttp
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from collections import deque, defaultdict
from typing import Optional, Dict, List, Tuple
import google.generativeai as genai
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time
import traceback

# ═══════════════════════════════════════════════════════════════════════════
# Configuration and Constants
# ═══════════════════════════════════════════════════════════════════════════

# --- IMPORTANT ---
# You need to set these in your environment (e.g., Render.com secrets)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL") # Optional, for sending large code blocks

# Bot Configuration
BOT_PREFIX = os.getenv("BOT_PREFIX", "!")
MAX_HISTORY_PER_CHANNEL = int(os.getenv("MAX_HISTORY", "100"))
RATE_LIMIT_MESSAGES = int(os.getenv("RATE_LIMIT_MESSAGES", "10"))
RATE_LIMIT_SECONDS = int(os.getenv("RATE_LIMIT_SECONDS", "60"))

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger('BeatBuddy')

# ═══════════════════════════════════════════════════════════════════════════
# Health Check Server for Render.com
# ═══════════════════════════════════════════════════════════════════════════

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = json.dumps({
            "status": "healthy",
            "service": "BeatBuddy-discord-bot",
            "timestamp": datetime.utcnow().isoformat()
        })
        self.wfile.write(response.encode())
    
    def log_message(self, format, *args):
        pass  # Suppress health check logs

def start_health_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"Health check server started on port {port}")
    server.serve_forever()

# ═══════════════════════════════════════════════════════════════════════════
# AI System Prompt - The Brain of BeatBuddy
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
You are BeatBuddy, the official, enthusiastic, and knowledgeable AI assistant for streambeatz.com. Your primary role is to help users, streamers, and promoters understand and use the platform effectively.

Your Knowledge Base - Everything about streambeatz.com:

1.  **What is StreamBeatz?**
    *   StreamBeatz is the ultimate song request platform for live streamers on platforms like Twitch and YouTube.
    *   It allows viewers to request songs in real-time, manage a queue, and monetize their stream through tips.
    *   The main website is: https://streambeatz.com/

2.  **For Viewers (The Fans):**
    *   **Requesting Songs:** Viewers can visit a streamer's public page (e.g., streambeatz.com/username) to request songs.
    *   **Free vs. Paid:** Viewers can make a limited number of free requests per day. To get their song played sooner, they can add a tip. Higher tips get higher priority in the queue.
    *   **Supported Platforms:** Users can request songs from Spotify, YouTube, and SoundCloud.
    *   **Queue:** The public page shows the current song queue, including an estimated time until a song is played.

3.  **For Streamers (The Creators):**
    *   **Getting Started:** Sign up as a "streamer" on https://streambeatz.com/register.
    *   **Dashboard:** Streamers get a powerful dashboard to manage their song queue (play, skip, clear), view analytics, and manage settings.
    *   **Monetization & Payouts:**
        *   Streamers set their own minimum tip amount for priority requests.
        *   **Revenue Split:** Streamers earn **70%** of all tips. 20% is the platform fee, and 10% covers payment processing (Stripe).
        *   Streamers can withdraw their earnings via PayPal, CashApp, Venmo, etc., once they reach a minimum balance of $25.
    *   **Customization:** They can customize their public page, use a stream overlay for OBS/Streamlabs, and set rules like max song length or disallowing explicit tracks.

4.  **For Promoters (The Recruiters):**
    *   **How it Works:** Anyone with a StreamBeatz account has a unique referral code.
    *   **The Commission:** Promoters earn a **5% commission** on the total revenue generated by EVERY streamer they successfully recruit. This is a powerful way to earn passive income.
    *   **Commission Example (Use this exact example when asked):**
        *   A promoter recruits 100 streamers using their referral code.
        *   Each of those streamers earns $100 in a day from tips.
        *   The total revenue generated by the promoter's recruits is 100 * $100 = $10,000.
        *   The promoter's commission is 5% of that $10,000, which is **$500 for that day**.
    *   **How to Promote:** Share your referral link or code with potential streamers. When they sign up using your code, they are permanently linked to you.

Your Personality:
*   **Enthusiastic & Friendly:** Use emojis! 🎉🎵🚀
*   **Knowledgeable:** Be the expert on StreamBeatz.
*   **Encouraging:** Encourage people to sign up as streamers or promoters.
*   **Clear & Concise:** Break down complex topics into simple steps.
*   **Always refer to the website:** When in doubt, guide users to https://streambeatz.com/ for official actions like signing up or logging in.
"""


# ═══════════════════════════════════════════════════════════════════════════
# Enhanced Discord Bot Class
# ═══════════════════════════════════════════════════════════════════════════

class BeatBuddyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        
        super().__init__(
            command_prefix=BOT_PREFIX,
            intents=intents,
            help_command=None,  # Using a custom help command
            case_insensitive=True
        )
        
        # Initialize Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        self.ai_model = genai.GenerativeModel(
            "gemini-1.5-flash", # Using a powerful and efficient model
            system_instruction=SYSTEM_PROMPT
            )
        
        # Data structures
        self.channel_histories = defaultdict(lambda: deque(maxlen=MAX_HISTORY_PER_CHANNEL))
        self.user_cooldowns = defaultdict(lambda: deque(maxlen=RATE_LIMIT_MESSAGES))
        self.conversation_sessions = {}
        self.command_stats = defaultdict(int)
        
        # Performance metrics
        self.start_time = datetime.utcnow()
        self.total_messages_processed = 0
        self.total_ai_requests = 0
        
    async def setup_hook(self):
        """Initialize bot components"""
        self.update_status.start()
        logger.info("Bot setup completed")
        
    @tasks.loop(minutes=5)
    async def update_status(self):
        """Update bot status with statistics"""
        guild_count = len(self.guilds)
        status_messages = [
            f"on {guild_count} servers",
            f"helping promoters earn!",
            f"{BOT_PREFIX}help for commands",
            "streambeatz.com"
        ]
        
        current_status = status_messages[
            (self.update_status.current_loop % len(status_messages))
        ]
        
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=current_status
            )
        )

# ═══════════════════════════════════════════════════════════════════════════
# Utility Classes
# ═══════════════════════════════════════════════════════════════════════════

class MessageFormatter:
    """Handles message formatting and splitting"""
    
    @staticmethod
    def split_message(content: str, max_length: int = 1990) -> List[str]:
        if len(content) <= max_length:
            return [content]
        
        messages = []
        current = ""
        in_code_block = False
        lang = ""
        
        lines = content.split('\n')
        for line in lines:
            if line.startswith('```'):
                if not in_code_block:
                    in_code_block = True
                    lang = line[3:]
                else:
                    in_code_block = False
            
            if len(current) + len(line) + 1 > max_length:
                if in_code_block:
                    current += "\n```" # Close the block
                messages.append(current)
                current = f"```{lang}\n" if in_code_block else "" # Reopen if needed
            
            current += line + "\n"
        
        if current:
            messages.append(current.rstrip())
        
        return messages

    @staticmethod
    def format_error(error: str) -> str:
        """Format error messages"""
        return f"❌ **Oops!** {error}"

class RateLimiter:
    """Handles rate limiting for users"""
    
    def __init__(self, bot: BeatBuddyBot):
        self.bot = bot
    
    def is_rate_limited(self, user_id: int) -> Tuple[bool, Optional[int]]:
        now = time.time()
        user_times = self.bot.user_cooldowns[user_id]
        
        while user_times and now - user_times > RATE_LIMIT_SECONDS:
            user_times.popleft()
        
        if len(user_times) >= RATE_LIMIT_MESSAGES:
            time_until_reset = int(RATE_LIMIT_SECONDS - (now - user_times))
            return True, time_until_reset
        
        user_times.append(now)
        return False, None

# ═══════════════════════════════════════════════════════════════════════════
# Main Bot Logic
# ═══════════════════════════════════════════════════════════════════════════

bot = BeatBuddyBot()
rate_limiter = RateLimiter(bot)

@bot.event
async def on_ready():
    logger.info(f"{'='*60}")
    logger.info(f"BeatBuddy is online and ready to help!")
    logger.info(f"Bot User: {bot.user}")
    logger.info(f"Connected to {len(bot.guilds)} guilds")
    logger.info(f"{'='*60}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    
    # Add message to history for context
    bot.channel_histories[message.channel.id].append({
        "role": "user",
        "parts": [f"{message.author.display_name}: {message.content}"]
    })
    
    bot.total_messages_processed += 1
    
    # Process commands if the message starts with the prefix
    if message.content.startswith(BOT_PREFIX):
        await bot.process_commands(message)
    # Respond if mentioned
    elif bot.user.mentioned_in(message):
         # Treat mention as a query
        query = re.sub(f'<@!?{bot.user.id}>', '', message.content).strip()
        if not query:
            await message.channel.send(f"Hey {message.author.mention}! How can I help you with streambeatz.com today? You can ask me a question or use `{BOT_PREFIX}help`.")
            return

        # Use the context of the command to call the `ask` function
        ctx = await bot.get_context(message)
        await ask.callback(ctx, query=query)


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(MessageFormatter.format_error(f"You missed a required argument: `{error.param.name}`"))
    elif isinstance(error, commands.BadArgument):
        await ctx.send(MessageFormatter.format_error(f"You provided an invalid argument. Please check your command."))
    else:
        logger.error(f"Command error in '{ctx.command}': {error}", exc_info=True)
        await ctx.send(MessageFormatter.format_error("An unexpected error occurred. The tech team has been notified!"))

# ═══════════════════════════════════════════════════════════════════════════
# Commands
# ═══════════════════════════════════════════════════════════════════════════

@bot.command(name='ask', aliases=['helpme', 'info'])
async def ask(ctx: commands.Context, *, query: str):
    """Answers any question about the StreamBeatz platform."""
    is_limited, time_left = rate_limiter.is_rate_limited(ctx.author.id)
    if is_limited:
        await ctx.send(f"⏳ Wow, you're curious! Please wait {time_left} seconds before asking again.")
        return
    
    bot.command_stats['ask'] += 1
    bot.total_ai_requests += 1
    
    async with ctx.typing():
        try:
            # Build context from channel history
            history = list(bot.channel_histories[ctx.channel.id])
            
            # Start a chat session with the model
            chat_session = bot.ai_model.start_chat(history=history)
            
            # Send the new query
            response = await chat_session.send_message_async(f"{ctx.author.display_name}: {query}")
            
            # Add AI response to history
            bot.channel_histories[ctx.channel.id].append({
                "role": "model",
                "parts": [response.text]
            })

            if not response.text:
                await ctx.send(MessageFormatter.format_error("I'm sorry, I couldn't come up with a response right now. Please try rephrasing your question!"))
                return
            
            # Send the response in chunks if it's too long
            messages = MessageFormatter.split_message(response.text)
            for msg in messages:
                await ctx.send(msg)
                
        except Exception as e:
            logger.error(f"AI generation error: {e}", exc_info=True)
            await ctx.send(MessageFormatter.format_error("I ran into a problem while processing your request. Please try again in a moment."))

@bot.command(name='promoter')
async def promoter_info(ctx: commands.Context):
    """Gives a detailed explanation of the promoter program."""
    bot.command_stats['promoter'] += 1
    # This command can just forward the query to the `ask` command for a detailed, AI-generated response.
    await ask.callback(ctx, query="Explain the promoter and referral program in detail, including the 5% commission and the example calculation.")

@bot.command(name='streamer')
async def streamer_info(ctx: commands.Context):
    """Explains how to get started as a streamer."""
    bot.command_stats['streamer'] += 1
    await ask.callback(ctx, query="How do I get started as a streamer on streambeatz.com? Explain the steps and the revenue model for streamers.")


@bot.command(name='help')
async def help_command(ctx: commands.Context):
    """Shows this help message."""
    bot.command_stats['help'] += 1
    embed = discord.Embed(
        title="🎵 BeatBuddy Help Desk",
        description=f"I'm the official AI assistant for **streambeatz.com**! Here's how you can use me. My prefix is `{BOT_PREFIX}`.",
        color=discord.Color.purple()
    )
    
    embed.add_field(
        name="❓ Ask Me Anything!",
        value=f"`{BOT_PREFIX}ask <your question>`\nAsk any question about the platform. For example:\n*`{BOT_PREFIX}ask How much do promoters earn?`*\n*`{BOT_PREFIX}ask what is the revenue split for streamers?`*",
        inline=False
    )
    
    embed.add_field(
        name="🚀 Quick Info Commands",
        value=(
            f"`{BOT_PREFIX}promoter` - Get details on the lucrative promoter program.\n"
            f"`{BOT_PREFIX}streamer` - Learn how to start streaming and earning.\n"
        ),
        inline=False
    )

    embed.add_field(
        name="🛠️ Utility Commands",
        value=(
            f"`{BOT_PREFIX}ping` - Check my response time.\n"
            f"`{BOT_PREFIX}invite` - Get a link to invite me to your server."
        ),
        inline=False
    )
    
    embed.set_footer(text="You can also just @mention me with your question!")
    await ctx.send(embed=embed)


@bot.command(name='ping')
async def ping_command(ctx: commands.Context):
    """Checks the bot's latency."""
    bot.command_stats['ping'] += 1
    start_time = time.time()
    message = await ctx.send("Pinging...")
    end_time = time.time()
    
    api_latency = round((end_time - start_time) * 1000)
    websocket_latency = round(bot.latency * 1000)
    
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Here's my current heartbeat!",
        color=discord.Color.green() if websocket_latency < 150 else discord.Color.orange()
    )
    embed.add_field(name="API Latency", value=f"`{api_latency}ms`")
    embed.add_field(name="Websocket Latency", value=f"`{websocket_latency}ms`")
    
    await message.edit(content=None, embed=embed)

@bot.command(name='invite')
async def invite_command(ctx: commands.Context):
    """Gets the link to invite BeatBuddy to another server."""
    bot.command_stats['invite'] += 1
    permissions = discord.Permissions(
        send_messages=True,
        read_messages=True,
        embed_links=True,
        read_message_history=True,
    )
    
    invite_url = discord.utils.oauth_url(bot.user.id, permissions=permissions)
    
    embed = discord.Embed(
        title="👋 Invite BeatBuddy!",
        description="Want me to help out on your server? Click the button below!",
        url=invite_url,
        color=discord.Color.blue()
    )
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Invite Me!", url=invite_url, style=discord.ButtonStyle.link, emoji="🚀"))
    
    await ctx.send(embed=embed, view=view)

# ═══════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    """Main bot runner"""
    if not all([DISCORD_TOKEN, GEMINI_API_KEY]):
        logger.error("FATAL: Missing required environment variables! You must set DISCORD_TOKEN and GEMINI_API_KEY.")
        return
    
    # Start the health check server in a separate thread for hosting platforms like Render
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    try:
        await bot.start(DISCORD_TOKEN)
    except discord.errors.LoginFailure:
        logger.error("FATAL: Invalid Discord Token. Please check your DISCORD_TOKEN environment variable.")
    except KeyboardInterrupt:
        logger.info("Shutdown signal received. Closing bot connection.")
    except Exception as e:
        logger.error(f"A fatal error occurred during bot execution: {e}", exc_info=True)
    finally:
        await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application shut down.")
