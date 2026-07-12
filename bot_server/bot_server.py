import asyncio
import socket
import subprocess
import websockets
import json
from datetime import datetime
import base64
import os
import langid
from openai import OpenAI
import config as cfg
import library
import threading
import queue
import numpy as np
import soxr
import audioop
import g711
from openai import AsyncOpenAI
import redis
import time
tts_stop_events = {}   # {external_media_port: threading.Event()}
tts_queues = {}      # {external_media_port: Queue()}
tts_workers = {}     # {external_media_port: Thread()}
ulaw_queues = {}
rtp_workers = {}
stt_queues = {}      # external_media_port -> asyncio.Queue
stt_tasks = {}       # external_media_port -> asyncio.Task
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI

#read config parameters
HOST = cfg.BOT_SERVER
PORT = cfg.BOT_PORT
LLM_SERVER = cfg.LLM_SERVER
LLM_PORT = cfg.LLM_PORT
STT_MODEL = cfg.STT_MODEL
TTS_MODEL = cfg.TTS_MODEL
TTS_VOICE = cfg.TTS_VOICE
LANGUAGE_SUPPORT = cfg.LANGUAGE_SUPPORT

#create openai client on bot server start
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
current_dir = os.getcwd()
prompt_path = os.path.join(current_dir, "..", "prompts/")

r = redis.Redis(host=cfg.REDIS_HOST, port=cfg.REDIS_PORT, db=0)

llm = ChatOpenAI(
    model="gpt-4o-mini",
    streaming=True,
)

agent = create_agent(
    model=llm,
    system_prompt="You are a helpful voice assistant.",
)

client_stt = AsyncOpenAI()

async def stt_worker(external_media_port):

    queue = stt_queues[external_media_port]

    async with client_stt.realtime.connect(model="gpt-realtime") as conn:

        await conn.session.update(
            session={
                "type": "realtime",
                "audio": {
                    "input": {
                        "format": {
                            "type": "audio/pcmu"
                        },
                        "transcription": {
                            "model": "gpt-4o-mini-transcribe"
                        },
                        "turn_detection": {
                            "type": "server_vad"
                        }
                    }
                }
            }
        )

        #
        # Ignore session.created
        #
        #await conn.recv()

        async def receiver():

            async for event in conn:

                if event.type == "conversation.item.input_audio_transcription.delta":
                    print("PARTIAL:", event.delta)

                elif event.type == "conversation.item.input_audio_transcription.completed":

                    print("FINAL:", event.transcript)
                    #print(type(event.transcript))
                    transcript = event.transcript
                    if isinstance(transcript, bytes):
                        transcript = transcript.decode("utf-8")


                    #
                    # Store in Redis
                    #
                    # r.set(
                    #     f"stt:{external_media_port}",
                    #     transcript,
                    #     ex=300
                    # )
                    # print("DATA SET IN REDIS---")
                    if transcript:
                        asyncio.create_task(llm_query(transcript, external_media_port))
                    else:
                        start_tts(TTS_VOICE, "kindly speak in detail so I can understand, can you please repeat, I can understand English, Hindi and Gujarati languages.", external_media_port)

                elif event.type == "error":
                    print(event)

        recv_task = asyncio.create_task(receiver())

        try:

            while True:

                audio = await queue.get()

                if audio is None:
                    break

                await conn.input_audio_buffer.append(
                    audio=base64.b64encode(audio).decode("ascii")
                )

                queue.task_done()

        finally:

            await conn.input_audio_buffer.commit()

            recv_task.cancel()

def rtp_worker(external_media_port):
    q = ulaw_queues[external_media_port]

    streamer = library.RTPStreamer(
        sock,
        "127.0.0.1",
        external_media_port
    )

    while True:
        item = q.get()

        if item is None:
            print("STOPPING RTP WORKER")
            break

        streamer.send_ulaw(item)

        q.task_done()

def tts_worker(external_media_port):
    q = tts_queues[external_media_port]

    while True:
        item = q.get()

        if item is None:
            print("STOPPING TTS WORKER")
            break

        voice, text = item

        event = tts_stop_events.setdefault(
            external_media_port,
            threading.Event()
        )
        event.clear()

        text_to_speech(
            voice,
            text,
            external_media_port,
            event
        )

        q.task_done()
        
def ensure_rtp_worker(external_media_port):

    if external_media_port not in ulaw_queues:
        ulaw_queues[external_media_port] = queue.Queue()

    if (
        external_media_port not in rtp_workers
        or not rtp_workers[external_media_port].is_alive()
    ):

        worker = threading.Thread(
            target=rtp_worker,
            args=(external_media_port,),
            daemon=True,
        )

        worker.start()

        rtp_workers[external_media_port] = worker
        
def ensure_tts_worker(external_media_port):
    if external_media_port not in tts_queues:
        tts_queues[external_media_port] = queue.Queue()

    if (
        external_media_port not in tts_workers
        or not tts_workers[external_media_port].is_alive()
    ):
        worker = threading.Thread(
            target=tts_worker,
            args=(external_media_port,),
            daemon=True,
        )
        worker.start()
        tts_workers[external_media_port] = worker

async def call_agent(query, external_media_port):
    #now = datetime.now()
    #print("ENSURE TTS WORKER:", now.strftime("%H:%M:%S"))
    ensure_tts_worker(external_media_port)

    buffer = ""
    now = datetime.now()
    #print("CALL AGENT:", now.strftime("%H:%M:%S"))

    async for event in agent.astream_events(
        {
            "messages": [
                {
                    "role": "user",
                    "content": query,
                }
            ]
        },
        version="v2",
    ):

        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]

            if chunk.content:
                buffer += chunk.content

                if len(buffer) > 70 or buffer.endswith((".", "!", "?")):
                    # now = datetime.now()
                    # print("BUFFER---:", now.strftime("%H:%M:%S"))
                    tts_queues[external_media_port].put(
                        (TTS_VOICE, buffer)
                    )
                    buffer = ""

    if buffer:
        tts_queues[external_media_port].put(
            (TTS_VOICE, buffer)
        )

#detects language in stt data - allows to control enable/disable language support
def is_supported_language(text):
    lang, confidence = langid.classify(text)
    if lang in LANGUAGE_SUPPORT:
        return True,lang
    else:
        return False,lang
    #return lang == 'en' or lang == 'hi' or lang == 'gu'

def raw_to_wav_stt(input_file,output_file):
    command = ["ffmpeg","-f", "mulaw","-ar", "8000","-ac", "1","-i", input_file,output_file]

    try:
        subprocess.run(command, stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
        #print("Conversion successful.")
    except subprocess.CalledProcessError as e:
        print("Error during conversion:", e)

#performs stt operation
def speech_to_text(input_file, output_file):
    stt_data = None
    try:
        # Initialize OpenAI client
        #client = OpenAI(api_key=api_key)

        # STT for the user input
        with open(output_file, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model=STT_MODEL,
                file=audio_file
            )
        stt_data = transcription.text

    except FileNotFoundError as fe:
        print(f"File not found: {fe}")
        stt_data = "I am not able to understand properly, please repeat"
    except Exception as e:
        print(f"Error during transcription: {e}")
        stt_data = "can you please speak again, I did not catch it properly"

    finally:
        # Cleanup files safely
        for f in [input_file, output_file]:
            try:
                if os.path.exists(f):
                    os.remove(f)
                    #print(f"Deleted {f}")
            except Exception as cleanup_err:
                print(f"Error deleting file {f}: {cleanup_err}")

    return stt_data

def start_tts(voice, text_data, external_media_port):
    event = tts_stop_events.setdefault(
        external_media_port, threading.Event()
    )
    event.clear()

    threading.Thread(
        target=text_to_speech,
        args=(voice, text_data, external_media_port, event),
        daemon=True
    ).start()
    
def stop_tts(external_media_port):

    event = tts_stop_events.get(external_media_port)

    if event:
        event.set()

    q = tts_queues.get(external_media_port)

    if q:
        while not q.empty():
            try:
                q.get_nowait()
                q.task_done()
            except queue.Empty:
                break

    rtp_q = ulaw_queues.get(external_media_port)

    if rtp_q:
        while not rtp_q.empty():
            try:
                rtp_q.get_nowait()
                rtp_q.task_done()
            except queue.Empty:
                break
            
    stt_q = stt_queues.get(external_media_port)

    if stt_q:
        while not stt_q.empty():
            try:
                stt_q.get_nowait()
                stt_q.task_done()
            except queue.Empty:
                break

def stop_tts_old(external_media_port):
    event = tts_stop_events.get(external_media_port)

    if event:
        event.set()

    q = tts_queues.get(external_media_port)

    if q:
        while not q.empty():
            try:
                q.get_nowait()
                q.task_done()
            except queue.Empty:
                break

def text_to_speech(voice, text_data, external_media_port, stop_event):

    ensure_rtp_worker(external_media_port)

    state = None
    sampler = library.Sampler(24000, 8000)

    with client.audio.speech.with_streaming_response.create(
        model=TTS_MODEL,
        voice=voice,
        input=text_data,
        response_format="pcm"
    ) as response:

        for chunk in response.iter_bytes(chunk_size=960):

            if stop_event.is_set():
                print("STOPPING TTS")
                break

            #ulaw, state = sampler.pcm24k_to_ulaw(chunk, state)
            
            # pcm = np.frombuffer(chunk, dtype=np.int16)
            # pcm8 = soxr.resample(pcm,24000,8000)
            # pcm8 = pcm8.astype(np.int16)
            # ulaw = audioop.lin2ulaw(pcm8.tobytes(), 2)
            
            pcm = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
            pcm8 = soxr.resample(pcm,24000,8000)
            #pcm8 = pcm8.astype(np.int16)
            #ulaw = audioop.lin2ulaw(pcm8.tobytes(), 2)
            ulaw = g711.encode_ulaw(pcm8)

            ulaw_queues[external_media_port].put(ulaw)

def text_to_speech_old(voice, text_data, external_media_port, stop_event):
    state = None
    sampler = library.Sampler(24000, 8000)
    streamer = library.RTPStreamer(sock, "127.0.0.1", external_media_port)

    with client.audio.speech.with_streaming_response.create(
        model=TTS_MODEL,
        voice=voice,
        input=text_data,
        response_format="pcm"
    ) as response:

        for chunk in response.iter_bytes(chunk_size=960):
            # now = datetime.now()
            # print("TTS RESPONSE:", now.strftime("%H:%M:%S"))
            if stop_event.is_set():
                print("STOPPING TTS AS USER INTERRUPTED IT")
                break

            ulaw, state = sampler.pcm24k_to_ulaw(chunk, state)
            streamer.send_ulaw(ulaw)

async def llm_query(query,external_media_port):
    await call_agent(query,external_media_port)

async def handle_voice_stream(websocket):
    print("Call connected to Bot")
    try:
        async for message in websocket:
            message = json.loads(message)
            event = message['event']
            if event=='start':
                call_id = message['start']['callSid']
                stream_id = message['start']['streamSid']
                caller_number = message['start']['from']
                did_number = message['start']['to']
                external_media_port = int(message['start']['external_media_port'])
                r.set(f"stt:{external_media_port}","",ex=300)
                stt_queues[external_media_port] = asyncio.Queue()
                stt_tasks[external_media_port] = asyncio.create_task(stt_worker(external_media_port))
            elif event=='media':
                call_id = message['media']['callSid']
                payload = message['media']['payload']
                external_media_port = int(message['media']['external_media_port'])
                decoded_audio = base64.b64decode(payload)
                if external_media_port in stt_queues:
                    await stt_queues[external_media_port].put(decoded_audio)
                #print(decoded_audio)
                # print("LENGTH OF USER AUDIO---")
                # print(len(decoded_audio))
                # with open("/tmp/"+call_id+".raw", "ab") as f:
                #     f.write(decoded_audio)
            elif event=='talk_start':
                call_id = message['talk_start']['callSid']
                external_media_port = int(message['talk_start']['external_media_port'])
                stop_tts(external_media_port)
            elif event=='talk_end':
                call_id = message['talk_end']['callSid']
                external_media_port = int(message['talk_end']['external_media_port'])
                
                # await stt_queues[external_media_port].put(None)
                # await stt_tasks[external_media_port]
                # del stt_tasks[external_media_port]
                # del stt_queues[external_media_port]

                # if stt_data and len(stt_data)>=3:
                #     # stt_event = {'event':'stt','sequenceNumber': 2,'stt':{'callSid':call_id,'reason':'','language':lang},'streamSid':''}
                #     # await websocket.send(json.dumps(stt_event))
                #     now = datetime.now()
                #     print("LLM QUERY START:", now.strftime("%H:%M:%S"))
                #     #asyncio.create_task(llm_query(stt_data, external_media_port))
                # else:
                #     start_tts(TTS_VOICE, "kindly speak in detail so I can understand, can you please repeat, I can understand English, Hindi and Gujarati languages.", external_media_port)
            elif event=='stop':
                call_id = message['stop']['callSid']
                #await websocket.close()
                print("Stop:"+call_id)
                if external_media_port in ulaw_queues:
                    ulaw_queues[external_media_port].put(None)

                if external_media_port in tts_queues:
                    tts_queues[external_media_port].put(None)
                    
                print("workers stopped")
                    
                # ulaw_queues.pop(external_media_port, None)
                # rtp_workers.pop(external_media_port, None)

                # tts_queues.pop(external_media_port, None)
                # tts_workers.pop(external_media_port, None)

                # tts_stop_events.pop(external_media_port, None)
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"Unhandled server error: {e}")
    finally:
        print("Call disconnected")
        #await websocket.close()

async def main():
    async with websockets.serve(handle_voice_stream, HOST, PORT):
        print(f"Bot Server running on ws://{HOST}:{PORT}")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())

