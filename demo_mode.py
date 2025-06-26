import asyncio
import json
import base64
import os
import audioop

import sounddevice as sd
import websockets
import structlog
from dotenv import load_dotenv


def load_prompt(file_name: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "prompts", f"{file_name}.txt")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


load_dotenv()
logger = structlog.get_logger()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VOICE = "echo"
SYSTEM_MESSAGE = load_prompt("system_prompt")

# Hard-coded availability for demo mode
AVAILABLE_SLOTS = [
    "10:00 AM - 10:30 AM",
    "2:00 PM - 2:30 PM",
    "4:00 PM - 4:30 PM",
]


async def send_session_update(ws):
    instructions = SYSTEM_MESSAGE
    formatted = "\n".join(f"- {s}" for s in AVAILABLE_SLOTS)
    instructions += f"\n\nToday's available slots:\n{formatted}"
    session_update = {
        "type": "session.update",
        "session": {
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": instructions,
            "modalities": ["text", "audio"],
            "temperature": 0.2,
        },
    }
    await ws.send(json.dumps(session_update))


def encode_chunk(data: bytes) -> str:
    ulaw = audioop.lin2ulaw(data, 2)
    return base64.b64encode(ulaw).decode()


def decode_chunk(b64: str) -> bytes:
    ulaw = base64.b64decode(b64)
    return audioop.ulaw2lin(ulaw, 2)


async def demo_conversation():
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set")

    uri = (
        "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
        "&response_format=json"
    )
    async with websockets.connect(
        uri,
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        },
    ) as ws:
        await send_session_update(ws)
        loop = asyncio.get_running_loop()
        q: asyncio.Queue[bytes] = asyncio.Queue()

        def callback(indata, frames, time, status):
            loop.call_soon_threadsafe(q.put_nowait, bytes(indata))

        with sd.RawInputStream(
            samplerate=8000, channels=1, dtype="int16", callback=callback
        ):
            with sd.RawOutputStream(
                samplerate=8000, channels=1, dtype="int16"
            ) as out:

                async def sender():
                    while True:
                        chunk = await q.get()
                        payload = {
                            "type": "input_audio_buffer.append",
                            "audio": encode_chunk(chunk),
                        }
                        await ws.send(json.dumps(payload))

                async def receiver():
                    async for message in ws:
                        resp = json.loads(message)
                        if resp["type"] == "response.audio.delta" and resp.get("data"):
                            out.write(decode_chunk(resp["data"]))

                await asyncio.gather(sender(), receiver())


if __name__ == "__main__":
    asyncio.run(demo_conversation())
