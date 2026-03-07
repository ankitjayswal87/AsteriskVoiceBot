import config as cfg
class ARIClass:

    """Here below every function contains header authorization, that curl request code for python you can get from postman.
    The basic CURL Request Example is:
    curl -v -u asterisk:asterisk -X POST "http://localhost:8088/ari/channels/1645003050.14/play?media=sound:demo-congrats"
    So, if you use this request in POSTMAN and get python code from it you will get it like I mentioned in every function.
    For user and password asterisk:asterisk we get Authorization header YXN0ZXJpc2s6YXN0ZXJpc2s=
    """

    #This function answer the channel
    def answer_call(self,channelid):
        #Answer the Call
        import requests
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/channels/"+channelid+"/answer"
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("POST", url, headers=headers, data=payload)
        #print("AnswerCall:"+response.text)

    #This function play the given prompt to channel
    def play_prompt(self,channelid,prompt):
        #Play the prompt on Stasis Start event
        import requests
        import json
        #url = "http://localhost:8088/ari/channels/"+channelid+"/play?media=sound:"+prompt
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/channels/"+channelid+"/play?media=sound:"+prompt
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("POST", url, headers=headers, data=payload)
        response = json.loads(response.text)
        return response
        #print(response.text)

    def stop_prompt(self,playback_id):
        #Play the prompt on Stasis Start event
        import requests
        import json
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/playbacks/"+playback_id
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("DELETE", url, headers=headers, data=payload)
        #response = json.loads(response.text)
        #print(response.text)

    #This function used to continue call flow into Asterisk Dialplan
    def continue_in_dialplan(self,channelid):
        import requests
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/channels/"+channelid+"/continue"
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("POST", url, headers=headers, data=payload)

    #This function plays ringing tone to channel
    def play_ringing(self,channelid):
        import requests
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/channels/"+channelid+"/ring"
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("POST", url, headers=headers, data=payload)

    #This function stops ringing tone to channel
    def stop_ringing(self,channelid):
        import requests
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/channels/"+channelid+"/ring"
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("DELETE", url, headers=headers, data=payload)

    #This function plays the pressed DTMF to channel
    def play_dtmf(self,channelid,digit):
        import requests
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/channels/"+channelid+"/play?media=sound:digits/"+digit
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("POST", url, headers=headers, data=payload)

    #This function plays music on hold on the channel
    def play_music_on_hold(self,channelid,moh):
        import requests
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/channels/"+channelid+"/moh?mohClass="+moh
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("POST", url, headers=headers, data=payload)

    #This function stops music on hold on the channel
    def stop_music_on_hold(self,channelid):
        import requests
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/channels/"+channelid+"/moh"
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("DELETE", url, headers=headers, data=payload)

    #This function creates bridge for the given name and type
    def create_bridge(self,bridge_name,bridge_type):
        import requests
        import json
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/bridges?name="+bridge_name+"&type="+bridge_type
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("POST", url, headers=headers, data=payload)
        #print(response.text)
        response = json.loads(response.content.decode('utf-8'))
        bridge_id = response['id']
        return bridge_id

    #This function list details of all bridges
    def get_all_bridges_details(self):
        import requests
        import json
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/bridges"
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("GET", url, headers=headers, data=payload)
        response = json.loads(response.content.decode('utf-8'))
        #bridge_id = response[1]['id'];bridge_type = response[1]['bridge_type'];
        return response

    #This function adds channel to bridge for the given bridge_id and channel_id
    def add_channel_in_bridge(self,bridge_id,channel_id):
        import requests
        import json
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/bridges/"+bridge_id+"/addChannel?channel="+channel_id
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("POST", url, headers=headers, data=payload)

    #This function removes channel from bridge for the given bridge_id and channel_id
    def remove_channel_from_bridge(self,bridge_id,channel_id):
        import requests
        import json
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/bridges/"+bridge_id+"/removeChannel?channel="+channel_id
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("POST", url, headers=headers, data=payload)

    #This function plays given moh on bridge_id
    def play_music_on_hold_on_bridge(self,bridge_id,moh):
        import requests
        import json
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/bridges/"+bridge_id+"/moh?mohClass="+moh
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("POST", url, headers=headers, data=payload)

    #This function deletes bridge for the given bridge_id
    def delete_bridge(self,bridge_id):
        import requests
        import json
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/bridges/"+bridge_id
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("DELETE", url, headers=headers, data=payload)

    def create_external_media(self,app,external_host,format):
        import requests
        import json
        #url = "http://localhost:8088/ari/channels/externalMedia?app=hello-world&external_host=127.0.0.1:6000&format=ulaw"
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/channels/externalMedia?app="+app+"&external_host="+external_host+"&format="+format
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("POST", url, headers=headers, data=payload)
        response = json.loads(response.text)
        #print("ExtChanId:"+response['id'])
        #external_channel_id = response['id']
        #port = response['channelvars']['UNICASTRTP_LOCAL_PORT']
        #print("PORT:"+str(port))
        return response

    def get_channel_variable(self,channelid,variable_name):
        import requests
        import json
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/channels/"+str(channelid)+"/variable?variable="+str(variable_name)
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("GET", url, headers=headers, data=payload)
        response = json.loads(response.content.decode('utf-8'))
        if 'value' in response:
            response = response['value']
        else:
            response = None
        return response

    def create_snoop_channel(self,channelid,snoopid,spy,whisper,app):
        import requests
        import json
        #url = "http://localhost:8088/ari/channels/externalMedia?app=hello-world&external_host=127.0.0.1:6000&format=ulaw"
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/channels/"+str(channelid)+"/snoop/"+str(snoopid)+"?spy="+str(spy)+"&whisper="+str(whisper)+"&app="+str(app)
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("POST", url, headers=headers, data=payload)
        response = json.loads(response.text)
        #print("SnoopChanId:"+response['id'])
        response = response['id']
        return response

    def hangup_call(self,channelid):
        import requests
        url = "http://"+cfg.ASTERISK_SERVER+":"+cfg.ASTERISK_PORT+"/ari/channels/"+channelid
        payload={}
        headers = {'Authorization': 'Basic YXN0ZXJpc2s6YXN0ZXJpc2s='}
        response = requests.request("DELETE", url, headers=headers, data=payload)
