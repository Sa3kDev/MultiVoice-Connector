
import asyncio
import json
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands, tasks

BOT_NAME = os.environ.get("BOT_NAME")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not BOT_NAME or not BOT_TOKEN:
    print("[FATAL] You must set BOT_NAME and BOT_TOKEN as environment variables.", file=sys.stderr)
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent.parent
QUEUE_DIR = BASE_DIR / "queue"
QUEUE_DIR.mkdir(exist_ok=True)
QUEUE_FILE = QUEUE_DIR / f"{BOT_NAME}.json"

STATUS_DIR = BASE_DIR / "status"
STATUS_DIR.mkdir(exist_ok=True)
STATUS_FILE = STATUS_DIR / f"{BOT_NAME}.json"

CONFIG_FILE = BASE_DIR / "config.json"


def get_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[{BOT_NAME}] Failed to read config: {e}", file=sys.stderr)
        return {}

intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!__unused__!", intents=intents)


def save_status(**kwargs):
    data = {
        "name": BOT_NAME,
        "real_name": str(bot.user) if bot.user else None,
        "id": bot.user.id if bot.user else None,
    }
    data.update(kwargs)
    try:
        STATUS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[{BOT_NAME}] Failed to write status: {e}", file=sys.stderr)


def get_command():
    if not QUEUE_FILE.exists():
        return None
    try:
        raw = QUEUE_FILE.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        data = json.loads(raw)
        QUEUE_FILE.unlink(missing_ok=True)
        return data
    except Exception as e:
        print(f"[{BOT_NAME}] Failed to read command from queue: {e}", file=sys.stderr)
        try:
            QUEUE_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        return None


async def join_voice(guild_id: int, channel_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        print(f"[{BOT_NAME}] guild {guild_id} not found.", file=sys.stderr)
        return False, "guild_not_found"

    channel = guild.get_channel(channel_id)
    if channel is None or not isinstance(channel, discord.VoiceChannel):
        print(f"[{BOT_NAME}] voice channel {channel_id} not found.", file=sys.stderr)
        return False, "channel_not_found"

    existing_vc = guild.voice_client
    try:
        if existing_vc and existing_vc.is_connected():
            await existing_vc.move_to(channel)
        else:
            await channel.connect()
        save_status(voice_channel_id=channel.id, voice_channel_name=channel.name, guild_id=guild.id)
        return True, None
    except Exception as e:
        print(f"[{BOT_NAME}] Failed to join voice: {e}", file=sys.stderr)
        return False, str(e)


async def leave_voice(guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        return False, "guild_not_found"

    vc = guild.voice_client
    if vc and vc.is_connected():
        try:
            await vc.disconnect(force=True)
            save_status(voice_channel_id=None, voice_channel_name=None, guild_id=guild.id)
            return True, None
        except Exception as e:
            return False, str(e)
    return True, "already_disconnected"


@tasks.loop(seconds=1.0)
async def watch_queue():
    cmd = get_command()
    if not cmd:
        return

    action = cmd.get("action")
    guild_id = cmd.get("guild_id")
    channel_id = cmd.get("channel_id")

    if action == "join" and guild_id and channel_id:
        ok, err = await join_voice(int(guild_id), int(channel_id))
        print(f"[{BOT_NAME}] join -> ok={ok} err={err}")
    elif action == "leave" and guild_id:
        ok, err = await leave_voice(int(guild_id))
        print(f"[{BOT_NAME}] leave -> ok={ok} err={err}")
    else:
        print(f"[{BOT_NAME}] Unknown command in queue: {cmd}", file=sys.stderr)


@bot.event
async def on_ready():
    print(f"[{BOT_NAME}] Logged in as {bot.user} (ID: {bot.user.id})")
    save_status(voice_channel_id=None, voice_channel_name=None, online=True)
    if not watch_queue.is_running():
        watch_queue.start()
    
    config = get_config()
    bot_config = config.get(BOT_NAME, {})
    default_voice_id = bot_config.get("voice_id")
    if default_voice_id:
        try:
            voice_id = int(default_voice_id)
            for guild in bot.guilds:
                channel = guild.get_channel(voice_id)
                if channel and isinstance(channel, discord.VoiceChannel):
                    ok, err = await join_voice(guild.id, voice_id)
                    if ok:
                        print(f"[{BOT_NAME}] Auto-joined voice channel: {channel.name}")
                    else:
                        print(f"[{BOT_NAME}] Failed to auto-join voice channel: {err}", file=sys.stderr)
                    break
        except ValueError:
            print(f"[{BOT_NAME}] Invalid voice_id in config: {default_voice_id}", file=sys.stderr)


def run():
    try:
        bot.run(BOT_TOKEN)
    except discord.LoginFailure:
        print(f"[{BOT_NAME}] Invalid token. Check tokens.json", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
