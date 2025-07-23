import os
import discord
from discord.ext import commands
import logging
import asyncio

# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

# It's highly recommended to use environment variables for sensitive data.
# You can get this token from the Discord Developer Portal.
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_DISCORD_BOT_TOKEN_HERE")

# The prefix for bot commands (e.g., !help).
BOT_PREFIX = os.getenv("BOT_PREFIX", "!")

# Your website's base URL and name.
WEBSITE_URL = "https://songreq.onrender.com"
WEBSITE_NAME = "streambeatz"

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('discordHelpbot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger('discordHelpbot')

# ═══════════════════════════════════════════════════════════════════════════
# Bot Setup
# ═══════════════════════════════════════════════════════════════════════════

# Define the necessary intents for the bot to function.
intents = discord.Intents.default()
intents.message_content = True  # Required to read message content.
intents.guilds = True           # Required for guild information.
intents.members = True          # Required for member information.

class HelpBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=BOT_PREFIX,
            intents=intents,
            help_command=None  # We will create a custom help command.
        )

    async def on_ready(self):
        """Called when the bot is successfully connected to Discord."""
        logger.info(f"{'='*50}")
        logger.info(f"Bot is logged in as {self.user}")
        logger.info(f"Bot ID: {self.user.id}")
        logger.info(f"Serving {len(self.guilds)} server(s)")
        logger.info(f"Website: {WEBSITE_URL}")
        logger.info(f"{'='*50}")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"for {BOT_PREFIX}help | {WEBSITE_NAME}"
            )
        )

    async def on_message(self, message: discord.Message):
        """
        This event is triggered for every message the bot can see.
        We use it to guide users who mention the bot.
        """
        # Ignore messages sent by the bot itself to prevent loops.
        if message.author == self.user:
            return

        # NEW FEATURE: Check if the bot was mentioned without a command.
        if self.user.mentioned_in(message) and not message.content.startswith(BOT_PREFIX):
            help_embed = discord.Embed(
                title=f"👋 Hello, {message.author.display_name}!",
                description=f"It looks like you have a question. I'm a bot with a specific set of commands designed to help you.\n\nPlease start by using the `{BOT_PREFIX}help` command to see everything I can do!",
                color=discord.Color.purple()
            )
            await message.channel.send(embed=help_embed)
            return # Stop further processing for this message.

        # Process actual commands. This is crucial!
        await self.process_commands(message)

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        """Global handler for command errors."""
        if isinstance(error, commands.CommandNotFound):
            return # Silently ignore commands that don't exist.
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ **Missing Argument:** You forgot to provide the `{error.param.name}`.")
        else:
            logger.error(f"Unhandled error in command '{ctx.command}': {error}", exc_info=True)
            await ctx.send("An unexpected error occurred. Please try again later.")

# Instantiate the bot
bot = HelpBot()

# ═══════════════════════════════════════════════════════════════════════════
#  General Commands
# ═══════════════════════════════════════════════════════════════════════════

@bot.command(name='help')
async def custom_help_command(ctx: commands.Context):
    """Displays the comprehensive help message."""
    embed = discord.Embed(
        title=f"👋 {WEBSITE_NAME} Help Desk",
        description=f"I'm your dedicated assistant for all things {WEBSITE_NAME}. Here's a full list of commands.",
        color=discord.Color.purple()
    )
    embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)

    embed.add_field(
        name="ℹ️ General Commands",
        value=f"`{BOT_PREFIX}whatis` - Explains what {WEBSITE_NAME} is.\n"
              f"`{BOT_PREFIX}features` - Lists the key platform features.\n"
              f"`{BOT_PREFIX}faq` - Frequently Asked Questions.\n"
              f"`{BOT_PREFIX}support` - How to get technical support.",
        inline=False
    )

    embed.add_field(
        name="🎧 For Streamers",
        value=f"`{BOT_PREFIX}setup` - A step-by-step guide to get started.\n"
              f"`{BOT_PREFIX}howitworks streamer` - The workflow for streamers.\n"
              f"`{BOT_PREFIX}payouts` - All about receiving your earnings.\n"
              f"`{BOT_PREFIX}overlay` - How to set up the OBS/Streamlabs overlay.\n"
              f"`{BOT_PREFIX}queue` - Explains how the smart queue works.",
        inline=False
    )
    
    embed.add_field(
        name="🎤 For Viewers",
        value=f"`{BOT_PREFIX}howitworks viewer` - The workflow for viewers.\n"
              f"`{BOT_PREFIX}tipping` - Explains how to tip for priority.\n"
              f"`{BOT_PREFIX}platforms` - Supported music platforms.",
        inline=False
    )

    embed.add_field(
        name="💰 Promoter Program",
        value=f"`{BOT_PREFIX}promote` - Details on the recruiter program.\n"
              f"`{BOT_PREFIX}referral` - Info on finding and using your referral code.",
        inline=False
    )

    embed.set_footer(text=f"For more details, visit {WEBSITE_URL}")
    await ctx.send(embed=embed)

@bot.command(name='whatis', aliases=['about'])
async def what_is_streambeatz(ctx: commands.Context):
    """Explains what streambeatz is."""
    embed = discord.Embed(
        title=f"🎵 What is {WEBSITE_NAME}?",
        description=(
            f"{WEBSITE_NAME} is the ultimate song request platform designed for live streamers and their communities. "
            "We provide a seamless way for viewers to request songs from Spotify, YouTube, and more, directly to their "
            "favorite streamer's live session."
        ),
        color=discord.Color.purple()
    )
    await ctx.send(embed=embed)

@bot.command(name='features')
async def features(ctx: commands.Context):
    """Lists the key features of the platform."""
    embed = discord.Embed(
        title="✨ Key Features",
        description=f"Here's what makes {WEBSITE_NAME} the best choice for song requests:",
        color=discord.Color.gold()
    )
    embed.add_field(name="Multi-Platform Support", value="<:spotify:1234567890> Spotify, <:youtube:1234567890> YouTube, and custom song links.", inline=False)
    embed.add_field(name="Smart Monetization", value="💰 Set minimum tip amounts and earn directly from your viewers.", inline=False)
    embed.add_field(name="Advanced Queue Management", value="📊 Automatically manage your request queue with priority scoring.", inline=False)
    embed.add_field(name="Customizable Overlays", value="📺 Beautiful overlays for OBS and Streamlabs.", inline=False)
    embed.add_field(name="Real-Time Analytics", value="📈 Track your earnings, top songs, and top supporters.", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='faq')
async def faq(ctx: commands.Context):
    """Provides answers to frequently asked questions."""
    embed = discord.Embed(
        title="🤔 Frequently Asked Questions",
        color=discord.Color.orange()
    )
    embed.add_field(name="Q: Why is my OBS/Streamlabs overlay not updating?", value="A: In your 'Browser Source' properties, click the 'Refresh cache of current page' button.", inline=False)
    embed.add_field(name="Q: A viewer's payment failed. What should they do?", value="A: Payments are handled by Stripe. The viewer should try another payment method or check with their bank.", inline=False)
    embed.add_field(name="Q: Is my payment information secure?", value="A: Yes. All payments are handled by Stripe. Your payment details are never stored on our servers.", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='support')
async def support(ctx: commands.Context):
    """Provides information on how to get technical support."""
    embed = discord.Embed(
        title="🛠️ Technical Support",
        description="If you've encountered a bug or have an issue that is not answered in the FAQ, here's how to get help.",
        color=discord.Color.dark_grey()
    )
    embed.add_field(name="Step 1: Gather Information", value="Please have ready: Your username, a detailed description of the problem, and a screenshot if possible.", inline=False)
    embed.add_field(name="Step 2: Join our Discord", value="The best way to get help is to post in the `#support` channel on our official Discord server.", inline=False)
    await ctx.send(embed=embed)

# ═══════════════════════════════════════════════════════════════════════════
# Streamer Commands
# ═══════════════════════════════════════════════════════════════════════════

@bot.command(name='setup')
async def setup_guide(ctx: commands.Context):
    """Provides a step-by-step setup guide for streamers."""
    embed = discord.Embed(
        title="🚀 Streamer Setup Guide",
        description=f"Follow these steps to get {WEBSITE_NAME} running on your stream.",
        color=discord.Color.green()
    )
    embed.add_field(name="1️⃣ Sign Up & Link Account", value=f"Go to [{WEBSITE_URL}/register]({WEBSITE_URL}/register) and link your Twitch or YouTube account.", inline=False)
    embed.add_field(name="2️⃣ Configure Your Page", value="In your dashboard 'Settings', set your minimum tip, song length limits, etc.", inline=False)
    embed.add_field(name="3️⃣ Get Your Overlay URL", value="In the 'Overlay' section, copy your unique browser source URL.", inline=False)
    embed.add_field(name="4️⃣ Add to OBS/Streamlabs", value="Add a new 'Browser' source, paste the URL, and set the dimensions.", inline=False)
    embed.add_field(name="5️⃣ Share Your Link!", value=f"Your request page is `{WEBSITE_URL}/your_username`. Share it with your viewers!", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='payouts')
async def payouts(ctx: commands.Context):
    """Explains the payout process for streamers."""
    embed = discord.Embed(
        title="💰 Getting Paid: The Payout Process",
        color=discord.Color.dark_green()
    )
    embed.add_field(name="Balance", value="Tips you receive (your 70% share) are added to your site balance instantly.", inline=False)
    embed.add_field(name="Minimum Withdrawal", value="You need a minimum balance of **$25.00** to request a withdrawal.", inline=False)
    embed.add_field(name="Requesting a Payout", value="Go to your dashboard's 'Withdrawal' tab to choose your payout method.", inline=False)
    embed.add_field(name="Supported Platforms", value="We currently support payouts via **PayPal, Cash App, and Venmo**.", inline=False)
    embed.add_field(name="Processing Time", value="Payout requests are processed within **3-5 business days**.", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='queue')
async def queue_info(ctx: commands.Context):
    """Explains how the smart queue works."""
    embed = discord.Embed(
        title="📊 How the Smart Queue Works",
        description="Our queue uses a priority score to decide the order.",
        color=discord.Color.blue()
    )
    embed.add_field(name="Priority Factors", value="A song's position is determined by:\n- **Tip Amount**: Higher tips mean higher priority.\n- **Submitter Role**: Subs and mods can get a boost.\n- **Time**: Older requests slowly gain priority.\n- **Votes**: Viewer upvotes can increase priority.", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='overlay')
async def overlay_guide(ctx: commands.Context):
    """Detailed instructions for setting up the OBS/Streamlabs overlay."""
    embed = discord.Embed(
        title="📺 Overlay Setup (OBS/Streamlabs)",
        description="Follow these steps carefully to add the request queue to your stream.",
        color=discord.Color.dark_purple()
    )
    embed.add_field(name="Step 1: Get Your Overlay URL", value=f"Log in on {WEBSITE_NAME}, go to your dashboard, and find the **'Overlay'** section. Copy the URL.", inline=False)
    embed.add_field(name="Step 2: Add a Browser Source", value="In OBS or Streamlabs, right-click 'Sources' and select `Add` -> `Browser`.", inline=False)
    embed.add_field(name="Step 3: Configure the Source", value="Paste your **Overlay URL** into the URL field and set the **Width** and **Height** (e.g., Width: 400, Height: 600).", inline=False)
    embed.add_field(name="Troubleshooting", value="If the overlay is stuck, right-click the source, go to `Properties`, and click **'Refresh cache of current page'**.", inline=False)
    await ctx.send(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════
# Viewer Commands
# ═══════════════════════════════════════════════════════════════════════════

@bot.command(name='howitworks')
async def how_it_works(ctx: commands.Context, role: str = None):
    """Explains how the platform works for streamers or viewers."""
    if role and role.lower() == 'streamer':
        await setup_guide.callback(ctx) # Use .callback() to properly invoke the command
        return
    
    # Default to viewer if role is 'viewer' or not specified
    if role is None or role.lower() == 'viewer':
        embed = discord.Embed(
            title="🎤 How It Works for Viewers",
            color=discord.Color.red()
        )
        embed.add_field(name="1. Visit the Streamer's Page", value="Click the song request link provided by the streamer.", inline=False)
        embed.add_field(name="2. Find a Song", value="Search for any song on Spotify or YouTube.", inline=False)
        embed.add_field(name="3. Submit Your Request", value="You can submit your song for free.", inline=False)
        embed.add_field(name="4. Tip for Priority (Optional)", value="Want your song played sooner? Add a tip! Higher tips move your song up the queue.", inline=False)
        embed.add_field(name="5. Watch and Listen", value="See your request on the streamer's overlay and enjoy!", inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"Invalid role. Please use `{BOT_PREFIX}howitworks streamer` or `{BOT_PREFIX}howitworks viewer`.")


@bot.command(name='tipping')
async def tipping_info(ctx: commands.Context):
    """Explains how tipping works for viewers."""
    embed = discord.Embed(
        title="💖 How to Tip for Priority",
        description="Tipping is the best way to support the streamer and get your song heard faster.",
        color=discord.Color.magenta()
    )
    embed.add_field(name="Why Tip?", value="When you tip, your song request gets a higher priority score, moving it up the queue.", inline=False)
    embed.add_field(name="How to Tip", value="After selecting a song, you'll see an option to add a tip before submitting.", inline=False)
    embed.add_field(name="Payment Methods", value="We securely process payments via Stripe, which accepts most major credit cards and Cash App.", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='platforms')
async def platforms_info(ctx: commands.Context):
    """Lists the supported music platforms."""
    embed = discord.Embed(
        title="🎶 Supported Music Platforms",
        description="You can request songs from the following sources:",
        color=discord.Color.from_rgb(30, 215, 96) # Spotify Green
    )
    embed.add_field(name="<:spotify:1234567890> Spotify", value="Search the entire Spotify library directly on the request page.", inline=False)
    embed.add_field(name="<:youtube:1234567890> YouTube", value="Paste a link to any YouTube video.", inline=False)
    await ctx.send(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════
# Promoter Commands
# ═══════════════════════════════════════════════════════════════════════════

@bot.command(name='promote', aliases=['recruiter'])
async def promoter_program(ctx: commands.Context):
    """Explains the promoter/recruiter revenue share program."""
    embed = discord.Embed(
        title="🤝 Promoter & Recruiter Program",
        description="Earn a passive income by helping us grow! We offer a generous revenue share for every streamer you successfully bring to our platform.",
        color=discord.Color.teal()
    )
    embed.add_field(name="The Deal", value="You will earn **5% of the total revenue** generated by every single streamer you recruit. This is a **lifetime commission**.", inline=False)
    embed.add_field(name="Example Scenario", value="Let's say you recruit **100** streamers, and each earns **$100 per day**.\nTotal Daily Revenue: `100 * $100 = $10,000`\nYour Commission: `$10,000 * 5% = $500`\nThat's **$500 per day** in passive income for you!", inline=False)
    await ctx.send(embed=embed)

# FIX: Corrected commands.comntexts to commands.Context
@bot.command(name='referral')
async def referral_info(ctx: commands.Context):
    """Explains how to use the referral system."""
    embed = discord.Embed(
        title="🔗 How Referrals Work",
        description="Your referral code is the key to earning your commission.",
        color=discord.Color.dark_teal()
    )
    embed.add_field(name="Finding Your Code", value=f"1. Sign up for an account at [{WEBSITE_URL}]({WEBSITE_URL}).\n2. Go to your user dashboard.\n3. Your unique referral code will be displayed there.", inline=False)
    embed.add_field(name="How to Use It", value="Give your code to streamers. When they sign up, there will be a field to enter a 'Referral Code'. Once they use your code, they are permanently linked to you.", inline=False)
    embed.add_field(name="Tracking Earnings", value="Your dashboard will have a section to track your recruited streamers and the commission you've earned.", inline=False)
    await ctx.send(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════
# Bot Runner
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    """Main entry point for the bot."""
    if DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        logger.error("Please replace 'YOUR_DISCORD_BOT_TOKEN_HERE' with your actual bot token in app.py.")
        return

    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        logger.info("Starting bot...")
        asyncio.run(main())
    except discord.errors.LoginFailure:
        logger.error("Failed to log in. Please check if your Discord token is valid.")
    except Exception as e:
        logger.fatal(f"An unexpected error occurred while running the bot: {e}", exc_info=True)
