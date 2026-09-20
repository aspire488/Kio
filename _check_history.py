import asyncio, sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def check():
    from telethon import TelegramClient
    client = TelegramClient('.telegram_sessions/kio_test_user', 39912440, 'b62d46342966040767fa6660857caa31')
    await client.start()
    bot = 'KIO_Runtime_bot'
    async for msg in client.iter_messages(bot, limit=10):
        direction = 'OUT' if msg.out else 'IN'
        txt = msg.text[:120] if msg.text else '(no text)'
        print(f'{direction} | {msg.date} | {txt}')
    await client.disconnect()

asyncio.run(check())
