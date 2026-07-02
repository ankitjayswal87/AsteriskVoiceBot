import asyncio
import socket
import struct
import audioop
import websockets
import requests
import json
from datetime import datetime
import base64
import os
import time
import random
import subprocess
import langid
#import threading
#import queue
#import shutil
from openai import OpenAI
#from pydub import AudioSegment
#import io
import config as cfg
import library
import threading
import queue
tts_stop_events = {}   # {external_media_port: threading.Event()}
tts_queues = {}      # {external_media_port: Queue()}
tts_workers = {}     # {external_media_port: Thread()}
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

llm = ChatOpenAI(
    model="gpt-4o-mini",
    streaming=True,
)

agent = create_agent(
    model=llm,
    system_prompt="You are a helpful voice assistant.",
)

def tts_worker(external_media_port):
    q = tts_queues[external_media_port]

    while True:
        item = q.get()

        if item is None:
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
    ensure_tts_worker(external_media_port)

    buffer = ""

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

                if len(buffer) > 50 or buffer.endswith((".", "!", "?")):
                    tts_queues[external_media_port].put(
                        (TTS_VOICE, buffer)
                    )
                    buffer = ""

    if buffer:
        tts_queues[external_media_port].put(
            (TTS_VOICE, buffer)
        )

async def call_agent_old(query,external_media_port):
    buffer = ""
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
                #print(chunk.content, end="", flush=True)
                buffer += chunk.content
                if len(buffer) > 150 or buffer.endswith((".", "!", "?")):
                    print("----123----")
                    print(buffer)
                    start_tts(TTS_VOICE, buffer, external_media_port)
                    buffer = ""

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

def stop_tts_old(external_media_port):
    event = tts_stop_events.get(external_media_port)
    if event:
        event.set()

def text_to_speech(voice, text_data, external_media_port, stop_event):
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
            if stop_event.is_set():
                print("STOPPING TTS AS USER INTERRUPTED IT")
                break

            ulaw, state = sampler.pcm24k_to_ulaw(chunk, state)
            streamer.send_ulaw(ulaw)

#performs tts operation
def text_to_speech_old(voice,text_data,external_media_port):
    try:
        state = None
        sampler = library.Sampler(24000,8000)
        streamer = library.RTPStreamer(sock, "127.0.0.1", external_media_port)
        
        with client.audio.speech.with_streaming_response.create(model=TTS_MODEL,voice=voice,input=text_data,response_format="pcm") as response:
            for chunk in response.iter_bytes(chunk_size=960):
                ulaw, state = sampler.pcm24k_to_ulaw(chunk, state)
                streamer.send_ulaw(ulaw)
    except Exception as e:
        print("tts not done")
        streamer.stream_ulaw_audio(prompt_path+'not_able.ulaw')

async def llm_query(query,external_media_port):
    #asyncio.run(call_agent(query,external_media_port))
    await call_agent(query,external_media_port)

#performs intelligence lookup for reply
def llm_query_old(LLM_SERVER,LLM_PORT,stt_data):
    url = "http://"+LLM_SERVER+":"+LLM_PORT+"/agentic_ai/bus_booking"
    payload = json.dumps({"thread_id": "call123abc","user_id":"test123","query": stt_data,"model": "openai"})
    headers = {'Content-Type': 'application/json'}
    response = requests.request("POST", url, headers=headers, data=payload)
    data = json.loads(response.text)
    return data['response']

async def handle_voice_stream(websocket):
    print("Call connected to Bot")
    try:
        async for message in websocket:
            message = json.loads(message)
            event = message['event']
            #print(event)
            if event=='start':
                call_id = message['start']['callSid']
                stream_id = message['start']['streamSid']
                caller_number = message['start']['from']
                did_number = message['start']['to']
            elif event=='media':
                call_id = message['media']['callSid']
                payload = message['media']['payload']
                decoded_audio = base64.b64decode(payload)
                #print(decoded_audio)
                with open("/tmp/"+call_id+".raw", "ab") as f:
                    f.write(decoded_audio)
            elif event=='talk_start':
                call_id = message['talk_start']['callSid']
                external_media_port = int(message['talk_start']['external_media_port'])
                stop_tts(external_media_port)
                print("stopping tts------")
            elif event=='talk_end':
                call_id = message['talk_end']['callSid']
                external_media_port = int(message['talk_end']['external_media_port'])
                print("EXTERNAL MEDIA PORT:"+str(external_media_port))
                
                # stream_ulaw_audio(sock,"/var/lib/asterisk/sounds/num-was-successfully.ulaw", "127.0.0.1", external_media_port)
                # stream_ulaw_audio(sock,"/var/lib/asterisk/sounds/num-was-successfully.ulaw", "127.0.0.1", external_media_port)
                # stream_ulaw_audio(sock,"/var/lib/asterisk/sounds/num-was-successfully.ulaw", "127.0.0.1", external_media_port)
                # continue
                input_file = '/tmp/'+call_id+'.raw'
                output_file = '/tmp/'+call_id+'.wav'

                # raw to wav file conversion
                if os.path.exists(input_file):
                    raw_to_wav_stt(input_file,output_file)

                    # STT
                    stt_data = speech_to_text(input_file,output_file)
                    print("STT Data: "+stt_data)
                    lang_status,lang = is_supported_language(stt_data)
                    #print("LANGUAGE:"+str(lang))

                    if stt_data and lang_status and len(stt_data)>=3:
                        stt_event = {'event':'stt','sequenceNumber': 2,'stt':{'callSid':call_id,'reason':'','language':lang},'streamSid':''}
                        await websocket.send(json.dumps(stt_event))
                        # LLM query
                        #llm_response = llm_query(LLM_SERVER,LLM_PORT,stt_data)
                        asyncio.create_task(llm_query(stt_data, external_media_port))
                        #print("LLM Answer: "+llm_response)

                        #TTS
                        #text_to_speech(TTS_VOICE,llm_response,external_media_port)
                        #start_tts(TTS_VOICE, llm_response, external_media_port)
                    else:
                        #text_to_speech(TTS_VOICE,"kindly speak in detail so I can understand, can you please repeat, I can understand English, Hindi and Gujarati languages.",external_media_port)
                        start_tts(TTS_VOICE, "kindly speak in detail so I can understand, can you please repeat, I can understand English, Hindi and Gujarati languages.", external_media_port)

            elif event=='stop':
                call_id = message['stop']['callSid']
                #await websocket.close()
                print("Stop:"+call_id)
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

