This is a voice bot solution which works with ARI interface, that can help you to build Voice Assistants. Here I assume that basic ARI is enabled on your Asterisk server and it has ARI user:password as asterisk:asterisk.

Here is the starting point of your call into Dialplan, the call enters into Stasis dialplan application called 'voicebot-app'.

exten => 1001,1,Answer()
same => n,Set(TALK_DETECT(set)=700,128)
same => n,Stasis(voicebot-app)
same = n,Hangup()

There are three main folders into the repository:
1) telephony_server
2) bot_server
3) prompts

1) telephony_server:
This folder contains telephony_server.py file that holds code for connecting to ARI application and creating of external media channel to stream it over external application. Install the required packages with requirement.txt in the python venv. Run the server via below command.
python3 telephony_server.py

2) bot_server:
This folder contains bot_server.py file that receives media streams for the call and process it for STT, LLM and TTS operations. Install the required packages with requirement.txt file in the python venv. Run the server via below command.
python3 bot_server.py

3) prompts:
Contains some filler sounds that can be played during the gap of silence till the TTS generate the answer.
