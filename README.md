# Introduction

This is a voice bot solution which works with ARI interface, that can help you to build Voice Assistants. I have used OPENAI to perform STT, LLM and TTS, you can use any other provider as well as per your need by modifying required code. Setting up RAG LLM query is not covered here, you can use your own logic or api there. Here I assume that basic ARI is enabled on your Asterisk server and it has ARI user:password as asterisk:asterisk.

# Asterisk Configuration

Sample /etc/asterisk/ari.conf file to add is below.

```
[general]
enabled = yes
pretty = yes

[asterisk]
type = user
read_only = no
password = asterisk
password_format = plain
```

Sample /etc/asterisk/http.conf file to add is below.

```
[general]
enabled = yes
bindaddr = 0.0.0.0
bindport = 8088
```

Here is the starting point of your call into Dialplan, the call enters into Stasis dialplan application called 'voicebot-app'.

```
exten => 1001,1,Answer()
same => n,Set(TALK_DETECT(set)=700,128)
same => n,Stasis(voicebot-app)
same = n,Hangup()
```

With above configuration you can reload Asterisk as below.

```
asterisk -rvvvv
core reload
```

# Code setup

There are three main folders into the repository:
1) telephony_server

This folder contains telephony_server.py file that holds code for connecting to ARI application and creating of external media channel to stream it over external application. Install the required packages with requirement.txt in the python venv. Run the server via below command.

```python3 telephony_server.py```

2) bot_server

This folder contains bot_server.py file that receives media streams for the call and process it for STT, LLM and TTS operations. Install the required packages with requirement.txt file in the python venv. Run the server via below command.

```
export OPENAI_API_KEY="sk-"
python3 bot_server.py
```

3) prompts

Contains some filler sounds that can be played during the gap of silence till the TTS generate the answer.


Once you run both the servers, you can register one sip user in softphone and dial 1001 to test the voicebot application.
