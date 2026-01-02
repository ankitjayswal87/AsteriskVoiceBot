import websockets
import asyncio
import socket
import json
import requests
import time
import os
import uuid
import base64
import shutil
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
prompt_path = os.path.join(current_dir, "..", "prompts/")
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
		#print(rtp_payload)
		#with open("/tmp/abctest.raw", "ab") as f:
			#f.write(rtp_payload)
		
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
	#url = "ws://localhost:8088/ari/events?api_key=asterisk:asterisk&app=hello-world"
	url = "ws://localhost:8088/ari/events?api_key="+user+":"+password+"&app="+app
	async with websockets.connect(url) as ws:
		while True:
			msg = await ws.recv()
			msg = json.loads(msg)
			event_type = msg['type']
			#print(event_type)
			if(event_type=='StasisStart'):
				channelid = msg['channel']['id']
				print(channelid)
				channel_name = msg['channel']['name']
				channel_name = channel_name.split("/")[0]
				caller_number = msg['channel']['caller']['number']
				did_number = msg['channel']['dialplan']['exten']
				ari.play_ringing(channelid)
				time.sleep(2)
				ari.stop_ringing(channelid)
				ari.answer_call(channelid)
				ari.play_prompt(channelid,'hello-world')
				if channel_name=='PJSIP':
					channel_variable_bridge_id = ari.get_channel_variable(channelid,"BRIDGE_ID")
					if channel_variable_bridge_id:
						print("SECOND CHANNEL COMING..."+str(channel_variable_bridge_id))
						ari.add_channel_in_bridge(channel_variable_bridge_id,channelid)
					else:
						response = ari.create_external_media(cfg.APP,cfg.RTP_SERVER+":"+str(cfg.RTP_PORT),cfg.CODEC)
						external_media_channelid = response['id']
						port = response['channelvars']['UNICASTRTP_LOCAL_PORT']
						print("EXT CHANNEL:"+str(external_media_channelid))
						bridge_id = ari.create_bridge("test_bridge","mixing")
						print("BridgeID:"+bridge_id)

						# Setting callid and port mapping
						r = redis.Redis(host='localhost', port=6379, db=0)
						call_data = {"call_id": channelid,"caller_number": caller_number,"did_number": did_number}
						r.hset("port:"+str(port), mapping=call_data)

						ari.add_channel_in_bridge(bridge_id,channelid)
						ari.add_channel_in_bridge(bridge_id,external_media_channelid)
						call_content = "Channel: PJSIP/101\nContext: second_call\nExtension: s\nPriority: 1\nSetVar: bridge_id="+str(bridge_id)
						call_file_name = str(uuid.uuid4())+".call"
						temp_file = "/tmp/"+call_file_name
						call_file_dir = "/var/spool/asterisk/outgoing/"
						with open(temp_file, "w") as f:
							f.write(call_content)
							shutil.move(temp_file,call_file_dir)

				# response = ari.create_external_media(cfg.APP,cfg.RTP_SERVER+":"+str(cfg.RTP_PORT),cfg.CODEC)
				# external_media_channelid = response['id']
				# print("EXT CHANNEL:"+str(external_media_channelid))
				#ari.play_music_on_hold(channelid,"default")
				#bridge_id = ari.create_bridge("test_bridge","mixing")
				#print("BridgeID:"+bridge_id)
				#ari.delete_bridge("9a08aeb0-c793-4a64-b3a3-5d1dc9221eae")
				#ari.add_channel_in_bridge("08b30dcb-cd22-42dd-87ce-c706eeb79049",channelid)
				#ari.continue_in_dialplan(channelid)
				#ari.play_music_on_hold_on_bridge("67bd133e-89e9-4bda-845c-025865c49120","default")

				#Get all bridge details and print them for every bridge
				# res = ari.get_all_bridges_details()
				# for i in range(len(res)):
				# 	print(res[i]['id']+res[i]['technology']+res[i]['bridge_type']+res[i]['bridge_class']+res[i]['creator']+res[i]['name']+str(res[i]['channels'])+res[i]['creationtime']+res[i]['video_mode'])
			
			elif(event_type=='ChannelDtmfReceived'):
				channelid = msg['channel']['id']
				digit = msg['digit']
				if(digit=='1'):
					ari.continue_in_dialplan(channelid)
				else:
					ari.play_dtmf(channelid,digit)
			elif(event_type=='ChannelTalkingStarted'):
				playback_channel_id = msg['channel']['id']
			elif(event_type=='ChannelTalkingFinished'):
				talk_end_channel_id = msg['channel']['id']
				talk_end_event = {'event':'talk_end','talk_end':{'accountSid':'1234','streamSid':'','callSid':talk_end_channel_id,'from':'','to':''},'streamSid':''}
				await ws_bot_client.send(json.dumps(talk_end_event))
			# elif(event_type=='ChannelTalkingStarted'):
			# 	playback_channel_id = msg['channel']['id']
			# elif(event_type=='ChannelTalkingFinished'):
			# 	talk_end_channel_id = msg['channel']['id']
			# 	talk_end_event = {'event':'talk_end','talk_end':{'accountSid':'1234','streamSid':'','callSid':talk_end_channel_id,'from':'','to':''},'streamSid':''}
			# 	#await ws_bot_client.send(json.dumps(talk_end_event))
			elif(event_type=='StasisEnd'):
				channelid = msg['channel']['id']
				#ari.hangup_call(channelid)

#asyncio.get_event_loop().run_until_complete(ari_events(cf.USER,cf.PASS,cf.APP))
async def main():
	udp_task = asyncio.create_task(udp_server())
	ari_task = asyncio.create_task(ari_events(user=cfg.USER, password=cfg.PASS, app=cfg.APP))
	await asyncio.gather(udp_task, ari_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server stopped")
