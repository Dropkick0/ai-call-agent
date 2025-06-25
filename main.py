import time
import os
import json
import base64
import asyncio
import logging
from datetime import datetime

import structlog
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(format="%(message)s", level=logging.INFO)
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()


def load_prompt(file_name):
    dir_path = os.path.dirname(os.path.realpath(__file__))
    prompt_path = os.path.join(dir_path, "prompts", f"{file_name}.txt")

    try:
        with open(prompt_path, "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        logger.error("prompt.load_failed", path=prompt_path)
        raise


# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # requires OpenAI Realtime API Access
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
NGROK_URL = os.getenv("NGROK_URL")
PORT = int(os.getenv("PORT", 5050))
GOOGLE_CRED_JSON = os.getenv("GOOGLE_CRED_JSON")

SYSTEM_MESSAGE = load_prompt("system_prompt")
VOICE = "echo"
LOG_EVENT_TYPES = [
    "response.content.done",
    "rate_limits.updated",
    "response.done",
    "input_audio_buffer.committed",
    "input_audio_buffer.speech_stopped",
    "input_audio_buffer.speech_started",
    "session.created",
]

app = FastAPI()

if not OPENAI_API_KEY:
    raise ValueError("Missing the OpenAI API key. Please set it in the .env file.")

if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_PHONE_NUMBER:
    raise ValueError("Missing Twilio configuration. Please set it in the .env file.")


@app.get("/", response_class=HTMLResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}


@app.post("/make-call")
async def make_call(to_phone_number: str):
    """Make an outgoing call to the specified phone number."""
    if not to_phone_number:
        return {"error": "Phone number is required"}
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        call = client.calls.create(
            url=f"{NGROK_URL}/outgoing-call",
            to=to_phone_number,
            from_=TWILIO_PHONE_NUMBER,
        )
        start_ts = datetime.utcnow().isoformat()
        logger.info(
            "call.initiated",
            call_id=call.sid,
            start_time=start_ts,
            to=to_phone_number,
        )
    except Exception as e:
        logger.error("call.initiation_failed", error=str(e))

    return {"call_sid": call.sid}


@app.api_route("/outgoing-call", methods=["GET", "POST"])
async def handle_outgoing_call(request: Request):
    """Handle outgoing call and return TwiML response to connect to Media Stream."""
    response = VoiceResponse()
    response.say("This calls may be recorded for compliance purposes")
    response.pause(length=1)
    response.say("Connecting with Compliance Agent")
    connect = Connect()
    connect.stream(url=f"wss://{request.url.hostname}/media-stream")
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")


@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and OpenAI."""
    logger.info("client.connected")
    await websocket.accept()

    async with websockets.connect(
        "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01&response_format=json",
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        },
    ) as openai_ws:
        await send_session_update(openai_ws)
        stream_sid = None
        session_id = None
        call_id = None
        start_ts = None
        transcripts = []

        async def receive_from_twilio():
            """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
            nonlocal stream_sid, call_id, start_ts
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data["event"] == "media" and openai_ws.open:
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data["media"]["payload"],
                        }
                        await openai_ws.send(json.dumps(audio_append))
                    elif data["event"] == "start":
                        stream_sid = data["start"]["streamSid"]
                        call_id = data["start"].get("callSid")
                        start_ts = datetime.utcnow().isoformat()
                        logger.info(
                            "stream.started",
                            call_id=call_id,
                            stream_sid=stream_sid,
                            start_time=start_ts,
                        )
            except WebSocketDisconnect:
                logger.info("client.disconnected", call_id=call_id)
                if openai_ws.open:
                    await openai_ws.close()

        async def send_to_twilio():
            """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
            nonlocal stream_sid, session_id, transcripts
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)
                    if response["type"] in LOG_EVENT_TYPES:
                        logger.info(
                            "openai.event",
                            call_id=call_id,
                            event=response["type"],
                            payload=response,
                        )
                    if response["type"] == "session.created":
                        session_id = response["session"]["id"]
                    if response["type"] == "session.updated":
                        logger.info("session.updated", call_id=call_id)
                    if response["type"] == "response.audio.delta" and response.get(
                        "delta"
                    ):
                        try:
                            audio_payload = base64.b64encode(
                                base64.b64decode(response["delta"])
                            ).decode("utf-8")
                            audio_delta = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": audio_payload},
                            }
                            await websocket.send_json(audio_delta)
                        except Exception as e:
                            logger.error(
                                "audio.process_error", call_id=call_id, error=str(e)
                            )
                    if response["type"] == "conversation.item.created":
                        transcripts.append(response)
                        logger.info(
                            "conversation.item", call_id=call_id, item=response
                        )
                    if response["type"] == "input_audio_buffer.speech_started":
                        logger.info("speech.start", call_id=call_id)

                        # Send clear event to Twilio
                        await websocket.send_json({"streamSid": stream_sid, "event": "clear"})

                        logger.info("speech.cancel", call_id=call_id)

                        # Send cancel message to OpenAI
                        interrupt_message = {"type": "response.cancel"}
                        await openai_ws.send(json.dumps(interrupt_message))
            except Exception as e:
                logger.error("send_to_twilio.error", call_id=call_id, error=str(e))

        try:
            await asyncio.gather(receive_from_twilio(), send_to_twilio())
        finally:
            stop_ts = datetime.utcnow().isoformat()
            logger.info(
                "call.completed",
                call_id=call_id,
                start_time=start_ts,
                stop_time=stop_ts,
                outcome=transcripts,
            )


async def send_session_update(openai_ws):
    """Send session update to OpenAI WebSocket."""
    session_update = {
        "type": "session.update",
        "session": {
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.2,
        },
    }
    logger.info("session.update.send", payload=session_update)
    await openai_ws.send(json.dumps(session_update))
