import asyncio
import websockets
import requests
import json
from datetime import datetime
import base64
import os
import time
import subprocess
#import threading
#import queue
#import shutil
from openai import OpenAI
#from pydub import AudioSegment
#import io
import config as cfg

HOST = cfg.BOT_SERVER
PORT = cfg.BOT_PORT
LLM_SERVER = cfg.LLM_SERVER
LLM_PORT = cfg.LLM_PORT

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
                print(decoded_audio)
                with open("/tmp/"+call_id+".raw", "ab") as f:
                    f.write(decoded_audio)
            elif event=='talk_end':
                #print(message)
                call_id = message['talk_end']['callSid']
            elif event=='stop':
                call_id = message['stop']['callSid']
                #await websocket.close()
                #print("Stop:"+call_id)
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

