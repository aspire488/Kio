"""KIO Live Acceptance Test — single-message runner.
Usage: python _live_test.py "message text"
Sends one message to KIO_Runtime_bot, waits for response, prints it.
"""
import asyncio, sys, io, time, json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def run_test(message: str, wait: int = 15):
    from telethon import TelegramClient
    client = TelegramClient('.telegram_sessions/kio_test_user', 39912440, 'b62d46342966040767fa6660857caa31')
    await client.start()
    bot = 'KIO_Runtime_bot'

    start = time.time()
    await client.send_message(bot, message)

    await asyncio.sleep(3)
    response_text = None
    response_time = None
    async for msg in client.iter_messages(bot, limit=5):
        if not msg.out and msg.date.timestamp() > start - 2:
            response_text = msg.text
            response_time = round(msg.date.timestamp() - start, 1)
            break

    result = {
        'message': message,
        'response': response_text or 'NO_RESPONSE',
        'response_time_s': response_time,
        'status': 'RECEIVED' if response_text else 'TIMEOUT'
    }
    print(json.dumps(result, ensure_ascii=False))
    await client.disconnect()

if len(sys.argv) < 2:
    print("Usage: python _live_test.py 'message'")
    sys.exit(1)

message = sys.argv[1]
wait = int(sys.argv[2]) if len(sys.argv) > 2 else 15
asyncio.run(run_test(message, wait))
