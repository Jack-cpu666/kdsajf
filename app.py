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

# Environment Variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
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
logger = logging.getLogger('DiscordAI')

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
            "service": "discord-ai-bot",
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
# AI System Prompt - Professional and Helpful
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are NOVA, an advanced AI assistant integrated into Discord. Your purpose is to be helpful, informative, and engaging while maintaining professionalism and respect.

Core Principles:
• Be helpful and provide accurate, detailed information
• Maintain a friendly yet professional tone
• Respect all users and promote positive interactions
• Admit when you don't know something rather than guessing
• Provide sources when discussing factual information
• Be creative and engaging when appropriate
• Follow Discord's community guidelines

Capabilities:
• Answer questions across various domains (science, technology, arts, etc.)
• Help with coding and technical problems
• Assist with creative writing and brainstorming
• Provide educational explanations
• Engage in thoughtful discussions
• Generate code examples with proper formatting

Response Guidelines:
• Keep responses concise but comprehensive
• Use Discord markdown for formatting
• Break long responses into readable sections
• Include code in proper code blocks
• Be mindful of Discord's 2000 character limit per message

Current Context:
You're operating in a Discord server where multiple conversations may be happening. Use the conversation history to maintain context and provide relevant responses."""

# ═══════════════════════════════════════════════════════════════════════════
# Enhanced Discord Bot Class
# ═══════════════════════════════════════════════════════════════════════════

class NovaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        
        super().__init__(
            command_prefix=BOT_PREFIX,
            intents=intents,
            help_command=None,  # Custom help command
            case_insensitive=True
        )
        
        # Initialize Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        self.ai_model = genai.GenerativeModel("gemini-2.0-flash-exp")
        
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
        await self.load_extensions()
        self.update_status.start()
        logger.info("Bot setup completed")
        
    async def load_extensions(self):
        """Load bot extensions/cogs"""
        # Add any cogs here in the future
        pass
        
    @tasks.loop(minutes=5)
    async def update_status(self):
        """Update bot status with statistics"""
        guild_count = len(self.guilds)
        status_messages = [
            f"Serving {guild_count} servers",
            f"Processed {self.total_ai_requests} requests",
            f"{BOT_PREFIX}help for commands",
            "Powered by Gemini AI"
        ]
        
        current_status = status_messages[
            (self.update_status.current_loop % len(status_messages))
        ]
        
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name=current_status
            )
        )

# ═══════════════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════════════

class MessageFormatter:
    """Handles message formatting and splitting"""
    
    @staticmethod
    def split_message(content: str, max_length: int = 1990) -> List[str]:
        """Split long messages while preserving code blocks"""
        if len(content) <= max_length:
            return [content]
        
        messages = []
        current = ""
        in_code_block = False
        
        lines = content.split('\n')
        for line in lines:
            if line.startswith('```'):
                in_code_block = not in_code_block
            
            if len(current) + len(line) + 1 > max_length:
                if in_code_block:
                    current += "\n```"
                messages.append(current)
                current = "```\n" if in_code_block else ""
            
            current += line + "\n"
        
        if current:
            messages.append(current.rstrip())
        
        return messages
    
    @staticmethod
    def format_code_block(code: str, language: str = "python") -> str:
        """Format code with syntax highlighting"""
        return f"```{language}\n{code}\n```"
    
    @staticmethod
    def format_error(error: str) -> str:
        """Format error messages"""
        return f"❌ **Error:** {error}"

class RateLimiter:
    """Handles rate limiting for users"""
    
    def __init__(self, bot: NovaBot):
        self.bot = bot
    
    def is_rate_limited(self, user_id: int) -> Tuple[bool, Optional[int]]:
        """Check if user is rate limited"""
        now = time.time()
        user_times = self.bot.user_cooldowns[user_id]
        
        # Remove old entries
        while user_times and now - user_times[0] > RATE_LIMIT_SECONDS:
            user_times.popleft()
        
        if len(user_times) >= RATE_LIMIT_MESSAGES:
            time_until_reset = int(RATE_LIMIT_SECONDS - (now - user_times[0]))
            return True, time_until_reset
        
        user_times.append(now)
        return False, None

# ═══════════════════════════════════════════════════════════════════════════
# Main Bot Commands
# ═══════════════════════════════════════════════════════════════════════════

bot = NovaBot()
rate_limiter = RateLimiter(bot)

@bot.event
async def on_ready():
    """Bot startup event"""
    logger.info(f"{'='*60}")
    logger.info(f"NOVA AI Bot is online!")
    logger.info(f"Bot User: {bot.user}")
    logger.info(f"Bot ID: {bot.user.id}")
    logger.info(f"Discord.py Version: {discord.__version__}")
    logger.info(f"Connected to {len(bot.guilds)} guilds")
    logger.info(f"Serving {sum(g.member_count for g in bot.guilds)} users")
    logger.info(f"{'='*60}")

@bot.event
async def on_message(message: discord.Message):
    """Process all messages for context"""
    if message.author.bot:
        return
    
    # Store message in history
    channel_id = message.channel.id
    bot.channel_histories[channel_id].append({
        "author": message.author.name,
        "content": message.content,
        "timestamp": message.created_at.isoformat()
    })
    
    bot.total_messages_processed += 1
    
    # Process commands
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: `{error.param.name}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Invalid argument: {error}")
    else:
        logger.error(f"Command error in {ctx.command}: {error}", exc_info=True)
        await ctx.send("❌ An unexpected error occurred. Please try again later.")

# ═══════════════════════════════════════════════════════════════════════════
# AI Commands
# ═══════════════════════════════════════════════════════════════════════════

@bot.command(name='ask', aliases=['ai', 'query', 'q'])
async def ask_ai(ctx: commands.Context, *, query: str):
    """Ask the AI assistant a question"""
    # Rate limiting
    is_limited, time_left = rate_limiter.is_rate_limited(ctx.author.id)
    if is_limited:
        await ctx.send(
            f"⏳ You're sending messages too quickly! "
            f"Please wait {time_left} seconds before trying again."
        )
        return
    
    # Update stats
    bot.command_stats['ask'] += 1
    bot.total_ai_requests += 1
    
    # Show typing indicator
    async with ctx.typing():
        try:
            # Build context
            history = bot.channel_histories[ctx.channel.id]
            conversation_context = "\n".join([
                f"[{msg['timestamp']}] {msg['author']}: {msg['content']}"
                for msg in list(history)[-20:]  # Last 20 messages
            ])
            
            # Create prompt
            prompt = f"""{SYSTEM_PROMPT}

Recent Conversation History:
{conversation_context}

Current User: {ctx.author.name}
Current Query: {query}

Please provide a helpful and informative response."""

            # Generate response
            response = await bot.ai_model.generate_content_async(prompt)
            
            if not response.text:
                await ctx.send("❌ I couldn't generate a response. Please try again.")
                return
            
            # Format and send response
            formatted_response = f"**{ctx.author.mention}** asked: {query}\n\n{response.text}"
            messages = MessageFormatter.split_message(formatted_response)
            
            for msg in messages:
                await ctx.send(msg)
                
        except Exception as e:
            logger.error(f"AI generation error: {e}", exc_info=True)
            await ctx.send(
                "❌ An error occurred while processing your request. "
                "Please try again or contact an administrator."
            )

@bot.command(name='chat', aliases=['conversation'])
async def start_chat(ctx: commands.Context):
    """Start a conversation session with the AI"""
    session_id = f"{ctx.channel.id}-{ctx.author.id}"
    
    if session_id in bot.conversation_sessions:
        await ctx.send("💬 You already have an active conversation session!")
        return
    
    bot.conversation_sessions[session_id] = {
        "started": datetime.utcnow(),
        "messages": []
    }
    
    embed = discord.Embed(
        title="💬 Conversation Mode Activated",
        description=(
            f"Hello {ctx.author.mention}! I'm now in conversation mode.\n"
            "I'll respond to all your messages in this channel.\n\n"
            f"Type `{BOT_PREFIX}endchat` to end the conversation."
        ),
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name='endchat')
async def end_chat(ctx: commands.Context):
    """End a conversation session"""
    session_id = f"{ctx.channel.id}-{ctx.author.id}"
    
    if session_id not in bot.conversation_sessions:
        await ctx.send("❌ You don't have an active conversation session.")
        return
    
    session = bot.conversation_sessions.pop(session_id)
    duration = datetime.utcnow() - session["started"]
    
    embed = discord.Embed(
        title="👋 Conversation Ended",
        description=f"Thanks for chatting, {ctx.author.mention}!",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="Duration",
        value=f"{duration.total_seconds():.0f} seconds"
    )
    embed.add_field(
        name="Messages",
        value=len(session["messages"])
    )
    await ctx.send(embed=embed)

@bot.command(name='code')
async def generate_code(ctx: commands.Context, language: str, *, description: str):
    """Generate code based on description"""
    bot.command_stats['code'] += 1
    
    async with ctx.typing():
        try:
            prompt = f"""Generate {language} code for the following requirement:
{description}

Provide clean, well-commented code with best practices."""

            response = await bot.ai_model.generate_content_async(prompt)
            
            if not response.text:
                await ctx.send("❌ Couldn't generate code. Please try again.")
                return
            
            # Extract code blocks
            code_pattern = re.compile(r"```(?:\w+)?\n(.*?)```", re.DOTALL)
            matches = code_pattern.findall(response.text)
            
            if matches:
                # Send code via webhook if configured
                if DISCORD_WEBHOOK_URL and len(matches[0]) > 1000:
                    await send_code_webhook(
                        matches[0],
                        f"generated_{language}_code.{get_extension(language)}"
                    )
                    await ctx.send(
                        f"✅ Generated {language} code has been sent via webhook!\n\n"
                        f"**Description:** {description}"
                    )
                else:
                    # Send in channel
                    formatted = MessageFormatter.format_code_block(matches[0], language)
                    messages = MessageFormatter.split_message(
                        f"**Generated {language} code:**\n{formatted}"
                    )
                    for msg in messages:
                        await ctx.send(msg)
            else:
                await ctx.send(response.text)
                
        except Exception as e:
            logger.error(f"Code generation error: {e}", exc_info=True)
            await ctx.send("❌ An error occurred while generating code.")

# ═══════════════════════════════════════════════════════════════════════════
# Utility Commands
# ═══════════════════════════════════════════════════════════════════════════

@bot.command(name='help')
async def help_command(ctx: commands.Context):
    """Show help information"""
    embed = discord.Embed(
        title="🤖 NOVA AI Bot - Help",
        description="I'm an advanced AI assistant powered by Google's Gemini AI.",
        color=discord.Color.blue()
    )
    
    # AI Commands
    embed.add_field(
        name="🧠 AI Commands",
        value=(
            f"`{BOT_PREFIX}ask <question>` - Ask me anything\n"
            f"`{BOT_PREFIX}chat` - Start a conversation session\n"
            f"`{BOT_PREFIX}endchat` - End conversation session\n"
            f"`{BOT_PREFIX}code <language> <description>` - Generate code"
        ),
        inline=False
    )
    
    # Utility Commands
    embed.add_field(
        name="🛠️ Utility Commands",
        value=(
            f"`{BOT_PREFIX}help` - Show this help message\n"
            f"`{BOT_PREFIX}stats` - Show bot statistics\n"
            f"`{BOT_PREFIX}ping` - Check bot latency\n"
            f"`{BOT_PREFIX}clear <amount>` - Clear messages (Manage Messages required)"
        ),
        inline=False
    )
    
    # Info Commands
    embed.add_field(
        name="ℹ️ Info Commands",
        value=(
            f"`{BOT_PREFIX}about` - About the bot\n"
            f"`{BOT_PREFIX}invite` - Get bot invite link\n"
            f"`{BOT_PREFIX}server` - Server information"
        ),
        inline=False
    )
    
    embed.set_footer(text=f"Prefix: {BOT_PREFIX} | Made with ❤️ using discord.py")
    await ctx.send(embed=embed)

@bot.command(name='stats')
async def stats_command(ctx: commands.Context):
    """Show bot statistics"""
    uptime = datetime.utcnow() - bot.start_time
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)
    
    embed = discord.Embed(
        title="📊 Bot Statistics",
        color=discord.Color.green()
    )
    
    # General Stats
    embed.add_field(
        name="General",
        value=(
            f"**Servers:** {len(bot.guilds)}\n"
            f"**Users:** {sum(g.member_count for g in bot.guilds)}\n"
            f"**Uptime:** {days}d {hours}h {minutes}m {seconds}s"
        )
    )
    
    # Usage Stats
    embed.add_field(
        name="Usage",
        value=(
            f"**Messages Processed:** {bot.total_messages_processed:,}\n"
            f"**AI Requests:** {bot.total_ai_requests:,}\n"
            f"**Commands Used:** {sum(bot.command_stats.values()):,}"
        )
    )
    
    # System Stats
    embed.add_field(
        name="System",
        value=(
            f"**Latency:** {round(bot.latency * 1000)}ms\n"
            f"**Python:** {os.sys.version.split()[0]}\n"
            f"**Discord.py:** {discord.__version__}"
        )
    )
    
    # Top Commands
    if bot.command_stats:
        top_commands = sorted(bot.command_stats.items(), key=lambda x: x[1], reverse=True)[:5]
        command_list = "\n".join([f"`{cmd}`: {count}" for cmd, count in top_commands])
        embed.add_field(
            name="Top Commands",
            value=command_list,
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='ping')
async def ping_command(ctx: commands.Context):
    """Check bot latency"""
    start_time = time.time()
    message = await ctx.send("🏓 Pinging...")
    end_time = time.time()
    
    api_latency = round((end_time - start_time) * 1000)
    websocket_latency = round(bot.latency * 1000)
    
    embed = discord.Embed(
        title="🏓 Pong!",
        color=discord.Color.green() if websocket_latency < 100 else discord.Color.orange()
    )
    embed.add_field(name="Websocket", value=f"{websocket_latency}ms")
    embed.add_field(name="API", value=f"{api_latency}ms")
    
    await message.edit(content=None, embed=embed)

@bot.command(name='clear', aliases=['purge'])
@commands.has_permissions(manage_messages=True)
async def clear_messages(ctx: commands.Context, amount: int):
    """Clear messages from the channel"""
    if amount < 1 or amount > 100:
        await ctx.send("❌ Please provide a number between 1 and 100.")
        return
    
    deleted = await ctx.channel.purge(limit=amount + 1)  # +1 for the command message
    msg = await ctx.send(f"✅ Cleared {len(deleted) - 1} messages.")
    await asyncio.sleep(3)
    await msg.delete()

@bot.command(name='about')
async def about_command(ctx: commands.Context):
    """Show information about the bot"""
    embed = discord.Embed(
        title="About NOVA AI",
        description=(
            "NOVA is an advanced AI assistant bot for Discord, powered by Google's "
            "Gemini AI. Designed to be helpful, informative, and engaging while "
            "maintaining professionalism and respect."
        ),
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Features",
        value=(
            "• Advanced AI responses\n"
            "• Code generation\n"
            "• Conversation sessions\n"
            "• Context awareness\n"
            "• Rate limiting\n"
            "• Comprehensive logging"
        )
    )
    
    embed.add_field(
        name="Technology",
        value=(
            "• **AI Model:** Gemini 2.0 Flash\n"
            "• **Language:** Python 3.11+\n"
            "• **Framework:** discord.py\n"
            "• **Hosting:** Render.com ready"
        )
    )
    
    embed.set_footer(text="Created with ❤️ for the Discord community")
    await ctx.send(embed=embed)

@bot.command(name='invite')
async def invite_command(ctx: commands.Context):
    """Get bot invite link"""
    permissions = discord.Permissions(
        send_messages=True,
        read_messages=True,
        embed_links=True,
        attach_files=True,
        read_message_history=True,
        add_reactions=True,
        use_external_emojis=True,
        manage_messages=True
    )
    
    invite_url = discord.utils.oauth_url(bot.user.id, permissions=permissions)
    
    embed = discord.Embed(
        title="📨 Invite NOVA AI",
        description="Click the button below to add me to your server!",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="Permissions Required",
        value=(
            "• Send Messages\n"
            "• Embed Links\n"
            "• Attach Files\n"
            "• Read Message History\n"
            "• Add Reactions\n"
            "• Manage Messages (for clear command)"
        )
    )
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Invite Bot", url=invite_url, style=discord.ButtonStyle.link))
    
    await ctx.send(embed=embed, view=view)

@bot.command(name='server', aliases=['serverinfo'])
async def server_info(ctx: commands.Context):
    """Show server information"""
    guild = ctx.guild
    
    embed = discord.Embed(
        title=f"Server Info - {guild.name}",
        color=discord.Color.blue()
    )
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    # General Info
    embed.add_field(name="Owner", value=guild.owner.mention)
    embed.add_field(name="Created", value=guild.created_at.strftime("%B %d, %Y"))
    embed.add_field(name="Members", value=guild.member_count)
    
    # Channels
    embed.add_field(
        name="Channels",
        value=(
            f"Text: {len(guild.text_channels)}\n"
            f"Voice: {len(guild.voice_channels)}\n"
            f"Categories: {len(guild.categories)}"
        )
    )
    
    # Other Info
    embed.add_field(name="Roles", value=len(guild.roles))
    embed.add_field(name="Emojis", value=len(guild.emojis))
    
    # Features
    if guild.features:
        features = ", ".join(guild.features[:10])
        if len(guild.features) > 10:
            features += f" (+{len(guild.features) - 10} more)"
        embed.add_field(name="Features", value=features, inline=False)
    
    embed.set_footer(text=f"Server ID: {guild.id}")
    await ctx.send(embed=embed)

# ═══════════════════════════════════════════════════════════════════════════
# Webhook Functions
# ═══════════════════════════════════════════════════════════════════════════

async def send_code_webhook(code: str, filename: str = "code.py"):
    """Send code file via webhook"""
    if not DISCORD_WEBHOOK_URL:
        return
    
    try:
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(DISCORD_WEBHOOK_URL, session=session)
            
            file_buffer = io.BytesIO(code.encode('utf-8'))
            file = discord.File(file_buffer, filename=filename)
            
            await webhook.send(
                content="📎 **Generated Code File**",
                file=file,
                username="NOVA AI - Code Generator"
            )
            
    except Exception as e:
        logger.error(f"Webhook send error: {e}")

def get_extension(language: str) -> str:
    """Get file extension for language"""
    extensions = {
        "python": "py",
        "javascript": "js",
        "typescript": "ts",
        "java": "java",
        "c": "c",
        "cpp": "cpp",
        "csharp": "cs",
        "go": "go",
        "rust": "rs",
        "ruby": "rb",
        "php": "php",
        "swift": "swift",
        "kotlin": "kt",
        "html": "html",
        "css": "css",
        "sql": "sql",
        "bash": "sh",
        "powershell": "ps1"
    }
    return extensions.get(language.lower(), "txt")

# ═══════════════════════════════════════════════════════════════════════════
# Message Listener for Conversation Mode
# ═══════════════════════════════════════════════════════════════════════════

@bot.listen('on_message')
async def conversation_listener(message: discord.Message):
    """Handle conversation mode messages"""
    if message.author.bot or message.content.startswith(BOT_PREFIX):
        return
    
    session_id = f"{message.channel.id}-{message.author.id}"
    if session_id not in bot.conversation_sessions:
        return
    
    # Update session
    session = bot.conversation_sessions[session_id]
    session["messages"].append({
        "author": message.author.name,
        "content": message.content,
        "timestamp": message.created_at.isoformat()
    })
    
    # Rate limiting
    is_limited, time_left = rate_limiter.is_rate_limited(message.author.id)
    if is_limited:
        await message.add_reaction("⏳")
        return
    
    async with message.channel.typing():
        try:
            # Build conversation context
            conversation = "\n".join([
                f"{msg['author']}: {msg['content']}"
                for msg in session["messages"][-10:]  # Last 10 messages
            ])
            
            prompt = f"""{SYSTEM_PROMPT}

This is a conversation session. Respond naturally and engagingly.

Conversation so far:
{conversation}

Provide a natural, conversational response."""

            response = await bot.ai_model.generate_content_async(prompt)
            
            if response.text:
                messages = MessageFormatter.split_message(response.text)
                for msg in messages:
                    await message.channel.send(msg)
                    
                # Update session
                session["messages"].append({
                    "author": "NOVA",
                    "content": response.text,
                    "timestamp": datetime.utcnow().isoformat()
                })
            
        except Exception as e:
            logger.error(f"Conversation error: {e}")
            await message.add_reaction("❌")

# ═══════════════════════════════════════════════════════════════════════════
# Error Handlers
# ═══════════════════════════════════════════════════════════════════════════

@bot.event
async def on_error(event: str, *args, **kwargs):
    """Global error handler"""
    logger.error(f"Error in {event}: {traceback.format_exc()}")

# ═══════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    """Main bot runner"""
    # Validate environment variables
    if not all([DISCORD_TOKEN, GEMINI_API_KEY]):
        logger.error("Missing required environment variables!")
        logger.error("Required: DISCORD_TOKEN, GEMINI_API_KEY")
        logger.error("Optional: DISCORD_WEBHOOK_URL, BOT_PREFIX, PORT")
        return
    
    # Start health check server
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Run bot
    try:
        await bot.start(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown complete.")
