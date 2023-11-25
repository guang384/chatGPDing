import hashlib
import json
import requests
import traceback
from fastapi import FastAPI, Request, HTTPException
import os
import logging
import hmac
import base64
from openai import OpenAI
import time
from persistent_accumulator import PersistentAccumulator

app = FastAPI()

openai_api_key = os.getenv("OPENAI_API_KEY")
if openai_api_key is None:
    logging.error("Need to set environment variable: OPENAI_API_KEY.")
    raise HTTPException(status_code=500, detail="Need to set environment variable: OPENAI_API_KEY.")

openai_client = OpenAI(
    api_key=os.environ['OPENAI_API_KEY'],  # this is also the default, it can be omitted
)

# use local file to persistent token usage
token_usage_accumulator = PersistentAccumulator(prefix='token_usage')


@app.on_event("startup")
async def startup_event():
    logging.basicConfig(level=logging.INFO)


def hmac_sha256_base64_encode(key, msg):
    hmac_key = bytes(key, 'utf-8')
    hmac_msg = bytes(msg, 'utf-8')

    hmac_hash = hmac.new(hmac_key, hmac_msg, hashlib.sha256).digest()
    base64_encoded = base64.b64encode(hmac_hash).decode('utf-8')

    return base64_encoded


def check_signature(timestamp, sign):
    SECRET_KEYS = os.getenv("DINGTALK_APP_SECRET")
    if SECRET_KEYS is None:
        logging.error("Need to set environment variable: DINGTALK_APP_SECRET.")
        raise HTTPException(status_code=401, detail="认证失败")
    for SECRET_KEY in SECRET_KEYS.split(','):
        contents = timestamp + "\n" + SECRET_KEY
        signed = hmac_sha256_base64_encode(SECRET_KEY, contents)
        if signed == sign:
            return
    raise HTTPException(status_code=401, detail="认证失败")


@app.post("/")
async def root(request: Request):
    check_signature(request.headers.get('timestamp'),
                    request.headers.get('sign'))
    # receive from dingtalk
    # https://open.dingtalk.com/document/orgapp/receive-message
    message = await request.json()

    if message['msgtype'] == 'audio':
        print("[{}] sent a message of type 'audio'.  -> {}".format(message['senderNick'],
                                                                   message['content']['recognition']))
        message['text'] = {
            "content": message['content']['recognition']
        }
    elif message['msgtype'] != 'text':
        print("[{}] sent a message of type '{}'.  -> {}".format(message['senderNick'], message['msgtype'], message))
        return {
            "msgtype": "text",
            "text": {
                "content": "请不要发文字信息意外的其他类型信息，我无法理解。"
            }
        }

    print("[{}]: {}".format(message['senderNick'], message['text']['content'].replace("\n", "\n  | ")))

    await call_openai(message['sessionWebhook'], [
        {"role": "system", "content": "You are a helpful assistant. Answer in Chinese unless specified otherwise."},
        {"role": "user", "content": message['text']['content']}
    ], 'gpt-4-1106-preview')
    # gpt-4-1106-preview

    return {
        "msgtype": "empty"
    }


async def call_openai(session_webhook, messages, model='gpt-4'):
    # prepare dingtalk
    url = session_webhook
    headers = {'Content-Type': 'application/json'}
    usage = None
    answer = ''

    # call openai
    openai_start_time = time.perf_counter()
    try:
        completion = openai_client.chat.completions.create(
            model=model,
            messages=messages
        )
        # organize responses
        answer = completion.choices[0].message.content
        usage = dict(completion).get('usage')
        token_usage_accumulator.add(usage.total_tokens)

        # https://open.dingtalk.com/document/orgapp/robot-message-types-and-data-format
        data = {
            "msgtype": "text",
            "text": {
                "content": answer
            }
        }
    except Exception as e:
        logging.error(e)
        # traceback.print_exc()
        data = {
            "msgtype": "markdown",
            "markdown": {
                "title": "我错了 orz",
                "text": "<font color=silver>完，出错啦！暂时没法用咯…… 等会再试试吧 [傻笑] <br />（%s）" % e.args
            }
        }
        answer = data["markdown"]["title"]
    openai_end_time = time.perf_counter()

    # response to dingtalk
    dingtalk_start_time = time.perf_counter()
    response = requests.post(url, data=json.dumps(data), headers=headers)
    dingtalk_end_time = time.perf_counter()

    # logging
    if response.json()['errcode'] == 0:
        print("[{}]: {}".format(model, answer.replace("\n", "\n  | ")))
    else:
        logging.info(response.json())
    print(
        "Request duration: openai {:.3f} s, dingtalk {:.3f} ms. {}. Token statistics: {}"
            .format(
            (openai_end_time - openai_start_time),
            (dingtalk_end_time - dingtalk_start_time) * 1000,
            usage,
            token_usage_accumulator.get_current_total()
        )
    )


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
