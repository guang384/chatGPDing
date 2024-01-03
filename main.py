import logging
import threading
import time
from queue import Queue

from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from openai.types.chat import ChatCompletion

from components import DingtalkClient, OpenaiClient

logging.basicConfig(level=logging.WARN)


class DingtalkMessagesHandler:
    def __init__(self, if_stream=True, number_workers=5):
        self.queue = Queue()
        self.dingtalk = DingtalkClient()
        self.openai = OpenaiClient(if_stream=if_stream)
        self.stopped = False
        self.processing = {}
        self.number_workers = number_workers

    def is_session_webhook_in_processing(self, session_webhook):
        return session_webhook in self.processing

    def get_processing_messages(self, session_webhook):
        return self.processing[session_webhook]

    def handle_request(self, request):
        self.queue.put(request)
        self.processing[request['session_webhook']] = request['messages']

    def start_workers(self):
        for i in range(self.number_workers):
            worker = threading.Thread(target=self.process_request, args=(i,))
            worker.start()

    def stop_workers(self):
        self.stopped = True
        for i in range(self.number_workers):
            self.queue.put({})
            time.sleep(0.001)

    def process_request(self, num):
        print("Started Message processing Worker: #" + str(num))
        while not self.stopped:
            request = self.queue.get()
            if request == {}:
                self.queue.task_done()
                break
            # main logic
            self.process_messages(request['session_webhook'], request['send_to'], request['messages'])

            # remove processed
            del self.processing[request['session_webhook']]

            self.queue.task_done()
        print("Stopped Message processing Worker: #" + str(num))

    def process_messages(self, session_webhook, send_to, messages):
        prompt_tokens = self.openai.num_tokens_from_messages(messages)
        print("Estimated Prompt Tokens:", prompt_tokens)

        start_time = time.perf_counter()
        try:
            completion = self.openai.chat_completions(messages)
            end_time = time.perf_counter()

            if isinstance(completion, ChatCompletion):
                print("Request duration: openai {:.3f} s.".format((end_time - start_time)))

                # organize responses
                answer = completion.choices[0].message.content
                self.dingtalk.send_text(
                    answer.rstrip() + message_bottom(usage.total_tokens, self.openai.chat_model),
                    session_webhook)
                print("Estimated Completion Tokens:", self.openai.num_tokens_from_string(answer))
                print("[{}]->[{}]: {}".format(self.openai.chat_model, send_to, answer.replace("\n", "\n  | ")))

                print("Token usage: {}.".format(usage))
            else:  # Stream[ChatCompletionChunk]
                print("Message received start at {:.3f} s.".format((end_time - start_time)))

                # organize responses
                answer = ''
                usage = 0
                if_in_block = False
                backticks_count = 0
                for chunk in completion:
                    chunk_message = chunk.choices[0].delta.content
                    if chunk_message is not None and len(chunk_message) > 0 \
                            and len(answer.strip()) + len(chunk_message.strip()) > 0:
                        answer += str(chunk_message)
                        if answer[-1] != '\n':
                            continue
                        if '```' in answer:
                            content = ''

                            lines = answer.rstrip().splitlines()  # to lines
                            last_line = lines[-1]
                            answer_without_last_line = "\n".join(lines[:-1])
                            if not if_in_block:
                                if_block_start, backticks_count = is_valid_md_code_start(last_line)
                                if if_block_start:
                                    content = answer_without_last_line
                                    answer = last_line + '\n'
                                    if_in_block = True
                            else:
                                if is_valid_md_code_end(last_line, backticks_count):
                                    content = answer
                                    answer = ''
                                    if_in_block = False
                            if len(content.strip()) > 0:
                                print("[{}]->[{}]: {}".format(
                                    self.openai.chat_model,
                                    send_to,
                                    content.rstrip().replace("\n", "\n  | ")))
                                try:
                                    self.dingtalk.send_text(content, session_webhook)
                                except Exception as e:
                                    print("Send answer to dingtalk Failed", e.args)
                                    continue
                                usage += self.openai.num_tokens_from_string(content)

                        if answer.endswith('\n\n') and not if_in_block and len(answer) > 100:
                            print("[{}]->[{}]: {}".format(
                                self.openai.chat_model, send_to, answer.rstrip().replace("\n", "\n  | ")))
                            try:
                                self.dingtalk.send_text(answer, session_webhook)
                            except Exception as e:
                                print("Send answer to dingtalk Failed", e.args)
                                continue
                            usage += self.openai.num_tokens_from_string(answer)
                            answer = ''

                if len(answer) > 0:
                    print("[{}]->[{}]: {}".format(
                        self.openai.chat_model, send_to, answer.rstrip().replace("\n", "\n  | ")))
                    answer_tokens = self.openai.num_tokens_from_string(answer)
                    self.dingtalk.send_text(
                        answer.rstrip() + message_bottom(prompt_tokens + usage + answer_tokens, self.openai.chat_model),
                        session_webhook)
                    usage += answer_tokens

                end_time = time.perf_counter()

                print("Request duration: openai {:.3f} s. Estimated completion Tokens: {}.".format(
                    (end_time - start_time), str(prompt_tokens + usage)))

        except Exception as e:
            end_time = time.perf_counter()
            print("Error Request duration: openai {:.3f} s.".format((end_time - start_time)))

            logging.error(e)
            # traceback.print_exc()
            self.dingtalk.send_markdown(
                "我错了 orz",
                "<font color=silver>完，出错啦！暂时没法用咯…… 等会再试试吧 [傻笑] <br />（%s）" % e.args,
                session_webhook)

    def check_signature(self, timestamp, sign):
        return self.dingtalk.check_signature(timestamp, sign)


def is_valid_md_code_start(line) -> (bool, int):
    if not line:  # if empty line
        return False, 0
    if not line.lstrip(' ').startswith('```'):
        return False, 1
    if len(line) - len(line.lstrip(' ')) > 3:
        return False, 2
    first_not_backticks_pos = len(line.lstrip())
    for i, c in enumerate(line.lstrip()):
        if c != '`':
            first_not_backticks_pos = i
            break
    if "`" in line.lstrip()[first_not_backticks_pos:]:
        return False, 3
    return True, first_not_backticks_pos


def is_valid_md_code_end(line, backticks_count) -> bool:
    if backticks_count < 3:
        backticks_count = 3
    if not line:  # if empty line
        return False
    if not line.lstrip(' ').startswith('```'):
        return False
    if len(line) - len(line.lstrip(' ')) > 3:
        return False
    for i, c in enumerate(line.strip()):
        if c != '`':
            return False
    if len(line.strip()) < backticks_count:
        return False
    return True


def message_bottom(usage, model):
    return f"\n\n( --- Used up {usage} tokens. --- )\n( --- {model} --- )"


def truncate_string(s):
    s = s.replace('\n', '')  # 去掉回车
    if len(s) > 100:
        s = s[:50] + ' ... ' + s[-30:]
    return s


####################################################################

@asynccontextmanager
async def lifespan(app: FastAPI):
    # The logic here is executed after startup. The logic here is executed before stopping.
    print('DingtalkMessagesHandler workers Starting up.')
    handler.start_workers()

    yield

    # The logic here is executed before stopping.
    print('DingtalkMessagesHandler workers Shutting down.')
    handler.stop_workers()


handler = DingtalkMessagesHandler(
    if_stream=True,
    number_workers=8)

app = FastAPI(lifespan=lifespan)


@app.post("/")
async def root(request: Request):
    handler.check_signature(
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

    # prepare to call
    session_webhook = message['sessionWebhook']
    senderNick = message['senderNick']
    senderContent = message['text']['content']
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Answer in Chinese unless specified otherwise."},
        {"role": "user", "content": senderContent}
    ]

    # Concurrency Control
    if handler.is_session_webhook_in_processing(session_webhook):
        processing_message = handler.get_processing_messages(session_webhook)
        print("[{}](忽略): {}".format(senderNick, senderContent.replace("\n", "\n  | ")))

        return {
            "msgtype": "markdown",
            "markdown": {
                "title": "[忙疯了]好快...",
                "text": "<font color=silver>你发的太快了…… 有点处理不过来了呢…… [尴尬]\n\n\n我还在琢磨：\""
                        + truncate_string(processing_message[-1]['content']) + "\""
            }
        }

    print("[{}]: {}".format(senderNick, senderContent.replace("\n", "\n  | ")))

    # call openai
    handler.handle_request({
        'session_webhook': session_webhook,
        'send_to': senderNick,
        'messages': messages
    })

    # Do not reply now, reply later using webhook method.
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
