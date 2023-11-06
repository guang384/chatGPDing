import hashlib
import json
import requests

from fastapi import FastAPI, Request, HTTPException
import os
import logging
import hmac
import base64
import openai
import time

app = FastAPI()


@app.on_event("startup")
async def startup_event():
    logging.basicConfig(level=logging.INFO)


def hmacsha256_base64_encode(key, msg):
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
        signed = hmacsha256_base64_encode(SECRET_KEY, contents)
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
    ])
    return {
        "msgtype": "empty"
    }


async def call_openai(session_webhook, messages, model='gpt-4'):
    # call openai
    openai.api_key = os.getenv("OPENAI_API_KEY")
    if openai.api_key is None:
        logging.error("Need to set environment variable: OPENAI_API_KEY.")
        raise HTTPException(status_code=500, detail="认证失败")

    openai_start_time = time.perf_counter()
    completion = openai.ChatCompletion.create(
        model=model,
        messages=messages
    )
    openai_end_time = time.perf_counter()

    answer = completion.to_dict()['choices'][0]['message']

    # response to dingtalk
    # https://open.dingtalk.com/document/orgapp/robot-message-types-and-data-format
    url = session_webhook
    headers = {'Content-Type': 'application/json'}
    data = {
        "msgtype": "text",
        "text": {
            "content": answer['content']
        }
    }

    dingtalk_start_time = time.perf_counter()
    response = requests.post(url, data=json.dumps(data), headers=headers)
    dingtalk_end_time = time.perf_counter()

    if response.json()['errcode'] == 0:
        print("[{}]: {}".format(model, answer['content'].replace("\n", "\n  | ")))
    else:
        logging.info(response.json())
    print("Request duration: openai {:.3f} s, dingtalk {:.3f} ms".format(
        (openai_end_time - openai_start_time),
        (dingtalk_end_time - dingtalk_start_time) * 1000))


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
