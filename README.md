# ChatGPDing

A DingTalk robot that integrates various model API services.

#### NEED PYTHON=3.9 +

> **Available model API services:** 
> - Anthropic(Claude3)
> - OpenAI(GPT-3.5/4,Service compatible with OpenAI API.)
> - Dashscope(qwen-vl)

---
### Some helpful instructions

About uvicorn
> The command `uvicorn main:app --reload` can be used to start an Uvicorn server in the current project 
and enable automatic reloading. ( Maybe you need to first run `sudo apt install uvicorn`. )


> To share project dependencies, 
generate a `requirements.txt` file with `pip freeze` command, 
add it to your git repository, 
and let others install dependencies with `pip install -r requirements.txt` command.

DingTalk document
> [DingTalk message format description](https://open.dingtalk.com/document/orgapp/the-use-of-internal-application-robots-in-person-to-person-single-chat)


Use virtualenv
> pip3 install virtualenv
> 
> sudo apt install python3.9
>
> virtualenv --python=python3.9 venv
> 
> source venv/bin/activate
> 
> deactivate
> 

Secrets

```shell
export DINGTALK_APP_KEY=dingXXXXXXX,dingYYYYYYYY
export DINGTALK_APP_SECRET=ljnV62W*********3I_OyYsHrfOk,pHGW******V8qPo0d9
export REWRITE_DINGTALK_HOST=some.domain
export REWRITE_DINGTALK_PATHNAME=hellotalk

export OPENAI_API_KEY=sk-XXXXXXX
export OPENAI_BASE_URL=https://some.domain/hellogpt
export OPENAI_CHAT_MODEL=gpt-4-1106-preview
export OPENAI_SYSTEM_PROMPT=You are a very helpful assistant.

export ANTHROPIC_API_KEY=sk-ant-api03-XXXXXXX
export ANTHROPIC_BASE_URL=https://some.domain/helloclaude
export ANTHROPIC_CHAT_MODEL=claude-3-opus-20240229

export DASHSCOPE_API_KEY=sk-XXXXXXX
```
Start Shell
```shell
#!/bin/bash

cd /home/cui/chatGPDing

# The possible values are: openai,anthropic,dashscope
export CHATBOT_SERVER_TYPE=openai

export CHATBOT_SERVER_API_KEY=$OPENAI_API_KEY
export CHATBOT_SERVER_BASE_URL=$OPENAI_BASE_URL
export CHATBOT_SERVER_CHAT_MODEL=$OPENAI_CHAT_MODEL
export CHATBOT_SERVER_STREAMING_ENABLE=true
export CHATBOT_SERVER_MULTIMODAL_ENABLE=false
export CHATBOT_SERVER_SYSTEM_PROMPT=You are a very helpful assistant.

export MESSAGE_HANDLER_WORKER_THREADS=2
export GROUP_MESSAGES_HANDLING_ENABLE=true
export ROBOTS_INTERACT_ENABLE=true          # TODO
export SERVER_PORT=8035

source venv/bin/activate && python main.py

```

Use [Cloudflare pages functions](https://developers.cloudflare.com/pages/functions/) to speed up access.
(check files in `cloudflare_page_functions_example`)

> Examples:
> 
>> rewrite http://oapi.dingtalk.com/robot/sendBySession to http://some.domain/hellotalk
> 
>> rewrite https://api.openai.com/v1 to https://some.domain/hellogpt
> 
