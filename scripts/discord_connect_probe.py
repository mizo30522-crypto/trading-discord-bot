"""Connect to Discord, log identity + visible channels, then exit.

Used as a one-shot smoke test that the bot token is valid and the bot can
see the report channel.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import discord

from trading_bot.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


async def main() -> int:
    settings = load_settings()
    if not settings.discord_bot_token:
        print("DISCORD_BOT_TOKEN not set", file=sys.stderr)
        return 2
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    ready = asyncio.Event()

    @client.event
    async def on_ready() -> None:
        print(f"Logged in as {client.user} (id={client.user.id if client.user else '?'})")
        for guild in client.guilds:
            print(f"  Guild: {guild.name} (id={guild.id})")
        channel = None
        if settings.discord_report_channel_id:
            channel = client.get_channel(settings.discord_report_channel_id)
            if channel is None:
                try:
                    channel = await client.fetch_channel(settings.discord_report_channel_id)
                except discord.HTTPException as exc:
                    print(f"  Cannot fetch report channel {settings.discord_report_channel_id}: {exc}")
            if channel is not None:
                print(f"  Report channel: #{channel.name} ({type(channel).__name__})")
        ready.set()
        await asyncio.sleep(2)
        await client.close()

    task = asyncio.create_task(client.start(settings.discord_bot_token))
    try:
        await asyncio.wait_for(ready.wait(), timeout=30)
    except TimeoutError:
        print("Timed out waiting for on_ready", file=sys.stderr)
        await client.close()
        return 1
    await task
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
