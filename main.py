import traceback
import logging
import time
from fastapi import FastAPI, Request
from openai.types.chat import ChatCompletion

from components import OpenaiClient, DingtalkClient, PersistentAccumulator

logging.basicConfig(level=logging.WARN)

app = FastAPI()

dingtalk = DingtalkClient()

openai = OpenaiClient(if_stream=True)

# use local file to persistent token usage
token_usage_accumulator = PersistentAccumulator(prefix='token_usage_'+openai.chat_model)


@app.post("/")
async def root(request: Request):
    dingtalk.check_signature(
        request.headers.get('timestamp'),
        request.headers.get('sign'))

    # receive from dingtalk
    # https://open.dingtalk.com/document/orgapp/receive-message
    message = await request.json()

    if message['msgtype'] == 'audio':
        print("[{}] sent a message of type 'audio'.  -> {}".format(
            message['senderNick'], message['content']['recognition']))
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

    # prepare to call
    session_webhook = message['sessionWebhook']
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Answer in Chinese unless specified otherwise."},
        {"role": "user", "content": message['text']['content']}
    ]

    # call openai
    prompt_tokens = openai.num_tokens_from_messages(messages)
    print("Estimated Prompt Tokens:", prompt_tokens)

    start_time = time.perf_counter()
    try:
        completion = openai.chat_completions(messages)
        end_time = time.perf_counter()

        if isinstance(completion, ChatCompletion):
            print("Request duration: openai {:.3f} s.".format((end_time - start_time)))

            # organize responses
            answer = completion.choices[0].message.content
            usage = dict(completion).get('usage')
            token_usage_accumulator.add(usage.total_tokens)

            await dingtalk.send_text(answer, session_webhook)
            print("Estimated Completion Tokens:", openai.num_tokens_from_string(answer))
            print("[{}]: {}".format(openai.chat_model, answer.replace("\n", "\n  | ")))

            print("{}. Token statistics: {}".format(usage, token_usage_accumulator.get_current_total()))
        else:  # Stream[ChatCompletionChunk]
            print("Message received start at {:.3f} s.".format((end_time - start_time)))

            # organize responses
            answer = ''
            usage = 0
            if_in_block = False
            for chunk in completion:
                chunk_message = chunk.choices[0].delta.content
                if chunk_message is not None and len(chunk_message) > 0 \
                        and len(answer.strip()) + len(chunk_message.strip()) > 0:
                    answer += str(chunk_message)
                    if answer.rstrip().endswith('```') and not if_in_block:
                        if_in_block = not if_in_block
                    elif answer.rstrip().endswith('```') and if_in_block:
                        if_in_block = not if_in_block
                        print("[{}]: {}".format(openai.chat_model, answer.rstrip().replace("\n", "\n  | ")))
                        try:
                            await dingtalk.send_text(answer, session_webhook)
                        except Exception as e:
                            print("Send answer to dingtalk Failed", e.args)
                            continue
                        usage += openai.num_tokens_from_string(answer)
                        answer = ''
                    elif answer.endswith('\n\n') and not if_in_block:
                        print("[{}]: {}".format(openai.chat_model, answer.rstrip().replace("\n", "\n  | ")))
                        try:
                            await dingtalk.send_text(answer, session_webhook)
                        except Exception as e:
                            print("Send answer to dingtalk Failed", e.args)
                            continue
                        usage += openai.num_tokens_from_string(answer)
                        answer = ''

            if len(answer) > 0:
                print("[{}]: {}".format(openai.chat_model, answer.rstrip().replace("\n", "\n  | ")))
                await dingtalk.send_text(answer + "\n(完)", session_webhook)
                usage += openai.num_tokens_from_string(answer)

            end_time = time.perf_counter()

            token_usage_accumulator.add(prompt_tokens)
            token_usage_accumulator.add(usage)

            print("Request duration: openai {:.3f} s. Estimated completion Tokens: {}. Token statistics: {}".format(
                (end_time - start_time), usage, token_usage_accumulator.get_current_total()))

    except Exception as e:
        end_time = time.perf_counter()
        print("Error Request duration: openai {:.3f} s.".format((end_time - start_time)))

        logging.error(e)
        traceback.print_exc()
        await dingtalk.send_markdown(
            "我错了 orz",
            "<font color=silver>完，出错啦！暂时没法用咯…… 等会再试试吧 [傻笑] <br />（%s）" % e.args,
            session_webhook)

    return {
        "msgtype": "empty"
    }

if __name__ == '__main__':
    import uvicorn
    import os

    port = 8000

    if os.getenv("SERVER_PORT") is not None:
        port = int(os.getenv("SERVER_PORT"))

    uvicorn.run(app, host="0.0.0.0", port=port)
