# ChatGPDing
A ROBOT OF DINGDING TALK TO CHATGPT


> The command `uvicorn main:app --reload` can be used to start a Uvicorn server in the current project 
and enable automatic reloading.


> To share project dependencies, 
generate a `requirements.txt` file with `pip freeze` command, 
add it to your git repository, 
and let others install dependencies with `pip install -r requirements.txt` command.

A very simple implementation to integrate OpenAI and DingTalk platforms.

> [DingTalk message format description](https://open.dingtalk.com/document/orgapp/the-use-of-internal-application-robots-in-person-to-person-single-chat)


Use virtualenv
> pip3 install virtualenv
> 
> virtualenv venv
> 
> source venv/bin/activate
> 
> deactivate
> 

Start Shell

```shell
#!/bin/bash

cd /home/cui/chatGPDing

export OPENAI_API_KEY=sk-HY*******R
export DINGTALK_APP_SECRET=ljnV62W*********3I_OyYsHrfOk,pHGW******V8qPo0d9
export REWRITE_DINGTALK_HOST=some.domain
export REWRITE_DINGTALK_PATHNAME=hellotalk
export OPENAI_BASE_URL=https://some.domain/hellogpt
export OPENAI_CHAT_MODEL=gpt-4-1106-preview
export SERVER_PORT=8035

source venv/bin/activate && python main.py
```

Can use [Cloudflare pages functions](https://developers.cloudflare.com/pages/functions/)

> rewrite http://oapi.dingtalk.com/robot/sendBySession to http://some.domain/hellotalk
> 
> rewrite https://api.openai.com/v1 to https://some.domain/hellogpt
> 

