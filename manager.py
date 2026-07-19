import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

BASE_DIR = Path(__file__).resolve().parent
TOKENS_FILE = BASE_DIR / "tokens.json"
CONFIG_FILE = BASE_DIR / "config.json"
QUEUE_DIR = BASE_DIR / "queue"
STATUS_DIR = BASE_DIR / "status"
SUBBOT_SCRIPT = BASE_DIR / "subbot" / "bot_template.py"

QUEUE_DIR.mkdir(exist_ok=True)
STATUS_DIR.mkdir(exist_ok=True)

MANAGER_TOKEN = "PUT_YOUR_MANAGER_BOT_TOKEN_HERE"


def read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[manager] Failed to read {path.name}: {e}", file=sys.stderr)
        return {}


def get_tokens() -> dict:
    return read_json_file(TOKENS_FILE)


def get_config() -> dict:
    return read_json_file(CONFIG_FILE)


def get_bot_status(name: str) -> dict:
    f = STATUS_DIR / f"{name}.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


class Manager:

    def __init__(self):
        self.processes: dict[str, subprocess.Popen] = {}

    def run_all(self):
        tokens = get_tokens()
        if not tokens:
            print("[manager] tokens.json is empty or not found. No bots will run.")
            return

        for name, token in tokens.items():
            if not token or "PUT_" in token:
                print(f"[manager] Skipping '{name}': Token not yet set in tokens.json")
                continue
            self.run_bot(name, token)

    def run_bot(self, name: str, token: str):
        if name in self.processes and self.processes[name].poll() is None:
            print(f"[manager] '{name}' is already running.")
            return

        env = os.environ.copy()
        env["BOT_NAME"] = name
        env["BOT_TOKEN"] = token

        print(f"[manager] Starting bot '{name}' ...")
        proc = subprocess.Popen(
            [sys.executable, str(SUBBOT_SCRIPT)],
            env=env,
            cwd=str(BASE_DIR),
        )
        self.processes[name] = proc

    def kill_all(self):
        for name, proc in self.processes.items():
            if proc.poll() is None:
                print(f"[manager] Stopping bot '{name}' ...")
                proc.terminate()

    def check_running(self, name: str) -> bool:
        proc = self.processes.get(name)
        return proc is not None and proc.poll() is None


bot_manager = Manager()

intents = discord.Intents.default()
intents.guilds = True
bot = commands.Bot(command_prefix="!__unused__!", intents=intents)




@bot.event
async def on_ready():
    print(f"[manager] Logged in as {bot.user}")
    bot_manager.run_all()
    try:
        synced = await bot.tree.sync()
        print(f"[manager] Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"[manager] Failed to sync slash commands: {e}", file=sys.stderr)


@bot.tree.command(name="bots", description="Show all managed bots")
@app_commands.checks.has_permissions(administrator=True)
async def bots_cmd(interaction: discord.Interaction):
    tokens = get_tokens()
    if not tokens:
        await interaction.response.send_message("No bots in tokens.json.", ephemeral=True)
        return

    lines = []
    for name in tokens.keys():
        status = get_bot_status(name)
        real_name = status.get("real_name")
        running = bot_manager.check_running(name)

        if real_name:
            display = f"**{name}** - {real_name}"
        else:
            display = f"**{name}** - (Still logging in...)"

        if not running:
            display += "  [NOT RUNNING]"

        vc_name = status.get("voice_channel_name")
        if vc_name:
            display += f"  [In: {vc_name}]"

        lines.append(display)

    embed = discord.Embed(
        title="Managed Bots",
        description="\n".join(lines),
        color=discord.Color.blurple(),
    )
    await interaction.response.send_message(embed=embed)




def main():
    try:
        bot.run(MANAGER_TOKEN)
    finally:
        bot_manager.kill_all()


if __name__ == "__main__":
    main()
