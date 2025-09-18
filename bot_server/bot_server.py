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

def raw_to_wav_stt(input_file,output_file):
    command = ["ffmpeg","-f", "mulaw","-ar", "8000","-ac", "1","-i", input_file,output_file]

    try:
        subprocess.run(command, stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
        #print("Conversion successful.")
    except subprocess.CalledProcessError as e:
        print("Error during conversion:", e)

def speech_to_text(api_key,input_file,output_file,tts_file,tts_file_new):
    # STT for the user input
    client = OpenAI(api_key=api_key)
    with open(output_file, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(model="gpt-4o-transcribe",file=audio_file)

    stt_data = transcription.text
    #print(stt_data)
    if os.path.exists(output_file):
        #print('delete file')
        os.remove(input_file)
        os.remove(output_file)
    if os.path.exists(tts_file):
        #print('delete tts file')
        os.remove(tts_file)
        os.remove(tts_file_new)
    return stt_data

def text_to_speech(api_key,voice,text_data,file_name):
    client = OpenAI(api_key=api_key)
    #print("New TTS Calling")
    try:
        input_file = "/tmp/"+file_name+"_tts.pcm"
        output_file = "/tmp/"+file_name+"_tts_new.raw"
        with client.audio.speech.with_streaming_response.create(model="tts-1",voice="nova",input=text_data,response_format="pcm") as response:
            with open(input_file, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=480):
                    f.write(chunk)
            
        if os.path.exists(input_file):
            command = ["ffmpeg","-f", "s16le","-ar", "24000","-ac", "1","-i", input_file,"-ar", "8000","-ac", "1","-f", "s16le",output_file] #["ffmpeg","-i", input_file,"-ar", "8000",output_file]
            try:
                subprocess.run(command, stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
                #print("text to speech done")
                return True
            except subprocess.CalledProcessError as e:
                print("Error during conversion:", e)
                return False
        else:
            print("tts file not exists")
            return False
    except Exception as e:
        print("tts not done")
        return False

def text_to_speech_old(api_key,voice,text_data,file_name):
    client = OpenAI(api_key=api_key)

    try:
        input_file = "/tmp/"+file_name+"_tts.wav"
        output_file = "/tmp/"+file_name+"_tts_new.wav"
        response = client.audio.speech.create(model="tts-1",voice=voice,input=text_data)
        mp3_audio = io.BytesIO(response.content)
        audio = AudioSegment.from_file(mp3_audio, format="mp3")
        audio.export(input_file, format="wav")
        
        if os.path.exists(input_file):
            command = ["ffmpeg","-i", input_file,"-ar", "8000",output_file]
            try:
                subprocess.run(command, stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
                #print("text to speech done")
                return True
            except subprocess.CalledProcessError as e:
                print("Error during conversion:", e)
                return False
        else:
            print("tts file not exists")
            return False
    except Exception as e:
        print("tts not done")
        return False

def llm_query(LLM_SERVER,LLM_PORT,vector_db,stt_data):
    url = "http://"+LLM_SERVER+":"+LLM_PORT+"/lang_chain_api/ask_to_vector_db_rag"
    payload = json.dumps({"vector_db": vector_db,"query": stt_data})
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
            elif event=='talk_end':
                #print(message)
                call_id = message['talk_end']['callSid']
                input_file = '/tmp/'+call_id+'.raw'
                output_file = '/tmp/'+call_id+'.wav'
                # tts_file = '/tmp/'+call_id+'_tts.wav'
                # tts_file_new = '/tmp/'+call_id+'_tts_new.wav'
                tts_file = '/tmp/'+call_id+'_tts.pcm'
                tts_file_new = '/tmp/'+call_id+'_tts_new.raw'

                # raw to wav file conversion
                if os.path.exists(input_file):
                    raw_to_wav_stt(input_file,output_file)

                    # STT
                    now = datetime.now()
                    #print("STT Start:", now.strftime("%H:%M:%S"))
                    stt_data = speech_to_text(os.getenv("OPENAI_API_KEY"),input_file,output_file,tts_file,tts_file_new)
                    now = datetime.now()
                    #print("STT END:", now.strftime("%H:%M:%S"))
                    print("STT Data: "+stt_data)

                    if stt_data:
                        # LLM query
                        now = datetime.now()
                        #print("LLM Start:", now.strftime("%H:%M:%S"))
                        tts_data = llm_query(LLM_SERVER,LLM_PORT,"openai_vector_data",stt_data)
                        now = datetime.now()
                        #print("LLM END:", now.strftime("%H:%M:%S"))
                        print("LLM Answer: "+tts_data)

                        #TTS
                        tts_done = text_to_speech(os.getenv("OPENAI_API_KEY"),"nova",tts_data,call_id)
                        now = datetime.now()
                        #print("TTS END:", now.strftime("%H:%M:%S"))
                        if tts_done:
                            tts_event = {'event':'tts','sequenceNumber': 2,'tts':{'callSid':call_id,'reason':'','stt':True},'streamSid':''}
                            await websocket.send(json.dumps(tts_event))
                        else:
                            tts_event = {'event':'tts','sequenceNumber': 2,'tts':{'callSid':call_id,'reason':'','stt':False},'streamSid':''}
                            await websocket.send(json.dumps(tts_event))
                    else:
                        tts_event = {'event':'tts','sequenceNumber': 2,'tts':{'callSid':call_id,'reason':'','stt':False},'streamSid':''}
                        await websocket.send(json.dumps(tts_event))

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

