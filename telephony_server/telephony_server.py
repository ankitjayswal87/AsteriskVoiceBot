import websockets
import asyncio
import socket
import json
import requests
import time
import os
import uuid
import base64
import random
import config as cf
import redis
from ari_class import ARIClass
from cachetools import TTLCache
import config as cfg

ari = ARIClass()

cache = TTLCache(maxsize=100, ttl=300)
ws_bot_url = cfg.BOT_URL #'ws://127.0.0.1:8080'
ws_bot_client = None

current_dir = os.getcwd()
prompt_path = current_dir+"/prompts/"
channel_playbacks = {}
external_media_channels = {}

filler_prompts = ["give_me_sec_new", "just_moment_new", "wait_new"]

async def connect_bot_websocket():
	global ws_bot_client
	try:
		ws_bot_client = await websockets.connect(ws_bot_url)
		print("Bot Server connected")
	except Exception as e:
		print("Websocket connection error:", e)

async def listen_to_bot_message(websocket):
	try:
		while True:
			message = await websocket.recv()
			message = json.loads(message)
			event = message['event']
			call_id = message['tts']['callSid']
			stt_flag = message['tts']['stt']
			if event=='tts':
				if stt_flag==False:
					# set here the not able to understand message
					ari.play_prompt(call_id,prompt_path+'clear_loud_new')
				else:
					# playback the bot response here
					tts_file = "/tmp/"+call_id+"_tts_new"
					response = ari.play_prompt(call_id,tts_file)
	except websockets.exceptions.ConnectionClosed:
		print("Connection closed")

# UDP RTP Server handler
async def udp_server(host=cfg.RTP_SERVER, port=cfg.RTP_PORT):
    loop = asyncio.get_running_loop()
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind((host, port))
    udp.setblocking(False)

    print(f"RTP Media Server listening on {host}:{port}")

    while True:
        msg, rinfo = await loop.sock_recvfrom(udp, 2048)

        # Extract RTP payload (skip first 12 bytes)
        rtp_payload = msg[12:]

        # Create Redis key e.g port:15605
        key = "port:"+str(rinfo[1])
        asyncio.create_task(process_stream_data(key,rtp_payload))

async def process_stream_data(key,rtp_payload):
    try:
        if cache.get(key):
            #print("DATA GOT FROM CACHE....")
            parsed_call_data = cache.get(key)
            call_id = parsed_call_data['call_id']
            caller_number = parsed_call_data['caller_number']
            did_number = parsed_call_data['did_number']
            base64_bytes = base64.b64encode(rtp_payload)
            base64_string = base64_bytes.decode('utf-8')
            start_event = {'event':'start','sequenceNumber':1,'start':{'accountSid':'1234','streamSid':'','callSid':call_id,'from':caller_number,'to':did_number,'mediaFormat':{'encoding':'audio/x-mulaw','sampleRate': 8000,'bitRate': 64, 'bitDepth':8}},'streamSid':''}
            media_event = {'event': 'media','sequenceNumber': 2,'media': {'chunk': 1,'timestamp': 208,'callSid':call_id,'payload': base64_string},'streamSid': 'vkslvs'}
            stop_event = {'event':'stop','sequenceNumber': 2,'stop':{'callSid':call_id,'reason':'call_disconnected'},'streamSid':''}
            if ws_bot_client:
                await ws_bot_client.send(json.dumps(media_event))
                #await ws.close(code=1000, reason="Client done")
        else:
			# get data from redis and set in cache to retrieve frequently later
            r = redis.Redis(host=cfg.REDIS_HOST, port=cfg.REDIS_PORT, db=0)
            call_data = r.hgetall(key)
            parsed_call_data = {k.decode('utf-8'): v.decode('utf-8') for k, v in call_data.items()}
            cache[key] = parsed_call_data
            call_id = parsed_call_data['call_id']
            caller_number = parsed_call_data['caller_number']
            did_number = parsed_call_data['did_number']
            base64_bytes = base64.b64encode(rtp_payload)
            base64_string = base64_bytes.decode('utf-8')
            start_event = {'event':'start','sequenceNumber':1,'start':{'accountSid':'1234','streamSid':'','callSid':call_id,'from':caller_number,'to':did_number,'mediaFormat':{'encoding':'audio/x-mulaw','sampleRate': 8000,'bitRate': 64, 'bitDepth':8}},'streamSid':''}
            media_event = {'event': 'media','sequenceNumber': 2,'media': {'chunk': 1,'timestamp': 208,'payload': base64_bytes},'streamSid': 'vkslvs'}
            stop_event = {'event':'stop','sequenceNumber': 2,'stop':{'callSid':call_id,'reason':'call_disconnected'},'streamSid':''}

            # connecting to Bot websocket server on call start
            await connect_bot_websocket()
            bot_listener_task = asyncio.create_task(listen_to_bot_message(ws_bot_client))

            if ws_bot_client:
                await ws_bot_client.send(json.dumps(start_event))
                #await ws.close(code=1000, reason="Client done")

    except Exception as e:
        print("Error in process_stream_data:", e)

async def ari_events(user,password,app):
	# Websocket connection to ARI App
	#url = "ws://localhost:8088/ari/events?api_key=asterisk:asterisk&app=hello-world"
	url = "ws://localhost:8088/ari/events?api_key="+user+":"+password+"&app="+app
	async with websockets.connect(url) as ws:
		unique_id = str(uuid.uuid4())
		while True:
			msg = await ws.recv()
			msg = json.loads(msg)
			event_type = msg['type']
			#print(event_type)
			#print(msg)
			if(event_type=='StasisStart'):
				channelid = msg['channel']['id']
				channel_name = msg['channel']['name']
				channel_name = channel_name.split("/")[0]
				#print(channel_name)
				#print("START: "+channelid)
				ari.answer_call(channelid)
				
				# Tracking SIP channel
				if channel_name=='PJSIP':
					caller_number = msg['channel']['caller']['number']
					did_number = msg['channel']['dialplan']['exten']
					
					incoming_sip_channel_id = channelid
					#ari.play_prompt(incoming_sip_channel_id,prompt_path+'welcome_new')
					response = ari.create_external_media(cfg.APP,cfg.RTP_SERVER+":"+str(cfg.RTP_PORT),cfg.CODEC)
					external_media_channelid = response['id']
					port = response['channelvars']['UNICASTRTP_LOCAL_PORT']
					#print("CREATE:"+external_media_channelid)
					external_media_channels[incoming_sip_channel_id] = external_media_channelid

					# Setting callid and port mapping
					r = redis.Redis(host='localhost', port=6379, db=0)
					call_data = {"call_id": incoming_sip_channel_id,"caller_number": caller_number,"did_number": did_number}
					r.hset("port:"+str(port), mapping=call_data)
					
					# create bridge and add SIP,ExternalMedia channels into the bridge
					bridge_id = ari.create_bridge(unique_id,"mixing")
					ari.add_channel_in_bridge(bridge_id,incoming_sip_channel_id)
					ari.add_channel_in_bridge(bridge_id,external_media_channelid)
					# set here your welcome prompt
					ari.play_prompt(incoming_sip_channel_id,prompt_path+'welcome_new')
			
			elif(event_type=='ChannelDtmfReceived'):
				channelid = msg['channel']['id']
				digit = msg['digit']
				if(digit=='1'):
					ari.continue_in_dialplan(channelid)
				else:
					ari.play_dtmf(channelid,digit)

			elif(event_type=='PlaybackStarted'):
				playback_id = msg['playback']['id']
				playback_channel_id = msg['playback']['target_uri'].split(':')[-1]
				# store playbackid in dictionary
				channel_playbacks[playback_channel_id] = playback_id

			elif(event_type=='ChannelTalkingStarted'):
				playback_channel_id = msg['channel']['id']
				playback_id = channel_playbacks.get(playback_channel_id)
				if playback_channel_id in channel_playbacks:
					del channel_playbacks[playback_channel_id]

				#ari.add_channel_in_bridge(bridge_id,incoming_sip_channel_id)
				if playback_id:
					# interrupt handling
					ari.stop_prompt(playback_id)
			elif(event_type=='ChannelTalkingFinished'):
				talk_end_channel_id = msg['channel']['id']
				#ari.remove_channel_from_bridge(bridge_id,incoming_sip_channel_id)
				#ari.play_music_on_hold(incoming_sip_channel_id,"default")
				talk_end_event = {'event':'talk_end','talk_end':{'accountSid':'1234','streamSid':'','callSid':talk_end_channel_id,'from':'','to':''},'streamSid':''}
				await ws_bot_client.send(json.dumps(talk_end_event))
				random_filler_prompt = random.choice(filler_prompts)
				time.sleep(1)
				# play random filler prompt here
				ari.play_prompt(talk_end_channel_id,prompt_path+random_filler_prompt)
				
			elif(event_type=='StasisEnd'):
				call_id = msg['channel']['id']
				channel_name = msg['channel']['name']
				channel_name = channel_name.split("/")[0]
				external_media_channelid = external_media_channels.get(call_id)
				ari.delete_bridge(bridge_id)
				if external_media_channelid:
					#print("END:"+str(external_media_channelid))
					del external_media_channels[call_id]
					ari.hangup_call(str(external_media_channelid))
				# if call_id in external_media_channels:
				# 	del external_media_channels[call_id]

				if channel_name=='PJSIP':
					#print("STOP: "+call_id)
					stop_event = {'event':'stop','sequenceNumber': 2,'stop':{'callSid':call_id,'reason':'call_disconnected'},'streamSid':''}
					await ws_bot_client.send(json.dumps(stop_event))
					if os.path.exists("/tmp/"+call_id+".raw"):
						os.remove("/tmp/"+call_id+".raw")
					if os.path.exists("/tmp/"+call_id+"_tts.pcm"):
						os.remove("/tmp/"+call_id+"_tts.pcm")
					if os.path.exists("/tmp/"+call_id+"_tts_new.raw"):
						os.remove("/tmp/"+call_id+"_tts_new.raw")


#asyncio.get_event_loop().run_until_complete(ari_events(cf.USER,cf.PASS,cf.APP))
async def main():
	#await connect_bot_websocket()
	
	#bot_listener_task = asyncio.create_task(listen_to_bot_message(ws_bot_client))
	udp_task = asyncio.create_task(udp_server())
	ari_task = asyncio.create_task(ari_events(user="asterisk", password="asterisk", app="hello-world"))
	await asyncio.gather(udp_task, ari_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server stopped")
