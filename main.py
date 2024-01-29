import hashlib
import logging
import re
import threading
import time
import os
from queue import Queue
import asyncio
from urllib.parse import urlparse
import chardet
import openai

import requests
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from openai.types.chat import ChatCompletion

from components import DingtalkClient, OpenaiClient, DashscopeClient

logging.basicConfig(level=logging.WARN)

# Matching image name, image name is the first 8 characters of MD5 encoding and in uppercase.
md5_filename_pattern = r"([0-9A-F]{8}\.png|[0-9A-F]{8}\.jpg)"


class DingtalkMessagesHandler:
    """
    Processing messages received from DingTalk users.
    """

    def __init__(self, if_stream=True, number_workers=4):
        self.queue = Queue()
        self.dingtalk = DingtalkClient()
        self.openai = OpenaiClient(if_stream=if_stream)
        self.dashscope = DashscopeClient()
        self.stopped = False
        self.processing = {}
        self.number_workers = number_workers

    def is_session_webhook_in_processing(self, session_webhook):
        return session_webhook in self.processing

    def get_processing_messages(self, session_webhook):
        return self.processing[session_webhook]

    def handle_request(self, request):
        self.queue.put(request)
        self.processing[request['session_webhook']] = request['message']

    def start_workers(self):
        for i in range(self.number_workers):
            worker = threading.Thread(target=asyncio.run, args=(self.process_request(i),))
            worker.start()

    def stop_workers(self):
        self.stopped = True
        for i in range(self.number_workers):
            self.queue.put({})
            time.sleep(0.001)

    async def process_request(self, num):
        print("Started Message processing Worker: #" + str(num))
        while not self.stopped:
            request = self.queue.get()
            if request == {}:
                self.queue.task_done()
                break
            # main logic
            await self.process_message(request['session_webhook'], request['send_to'], request['message'])

            # remove processed
            del self.processing[request['session_webhook']]

            self.queue.task_done()
        print("Stopped Message processing Worker: #" + str(num))

    async def process_message(self, session_webhook, send_to, message):
        # If the file content contains image names and the images exist, use a multimodal model to answer.
        if_has_exist_image = False
        contents = []
        if re.search(md5_filename_pattern, message):
            segments = re.split(md5_filename_pattern, message)
            for segment in segments:
                if len(segment) == 0:
                    continue
                if re.search(md5_filename_pattern, segment):
                    dir_name = os.path.abspath(download_dir)
                    file_path = os.path.join(dir_name, segment)
                    if os.path.exists(file_path):
                        if_has_exist_image = True
                        contents.append({"image": "file://" + file_path})
                        continue
                contents.append({"text": segment})

        if if_has_exist_image:
            # Hand it over to Qwen-VL
            content, usage = await self.dashscope.multimodal_conversation(contents)
            await self.dingtalk.send_text(
                content + message_bottom(
                    {"in": usage['input_tokens'], "out": usage['output_tokens'], "img": usage['image_tokens']},
                    self.dashscope.model),
                session_webhook)
            print("[{}]->[{}]: {}".format(
                self.dashscope.model, send_to, content.rstrip().replace("\n", "\n  | ")))
            return

        # Hand it over to ChatGPT
        messages = [
            {"role": "system", "content": "You are a helpful assistant. Answer in Chinese unless specified otherwise."},
            {"role": "user", "content": message}
        ]
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
                usage = dict(completion).get('usage')

                await self.dingtalk.send_text(
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
                                print("[{}]->[{}]: {}".format(self.openai.chat_model, send_to,
                                                              content.rstrip().replace("\n", "\n  | ")))
                                try:
                                    await self.dingtalk.send_text(content, session_webhook)
                                except Exception as e:
                                    print("Send answer to dingtalk Failed", e.args)
                                    continue
                                usage += self.openai.num_tokens_from_string(content)

                        if answer.endswith('\n\n') and not if_in_block and len(answer) > 100:
                            print("[{}]->[{}]: {}".format(self.openai.chat_model, send_to,
                                                          answer.rstrip().replace("\n", "\n  | ")))
                            try:
                                await self.dingtalk.send_text(answer, session_webhook)
                            except Exception as e:
                                print("Send answer to dingtalk Failed", e.args)
                                continue
                            usage += self.openai.num_tokens_from_string(answer)
                            answer = ''

                print("[{}]->[{}]: {}".format(
                    self.openai.chat_model, send_to, answer.rstrip().replace("\n", "\n  | ")))
                answer_tokens = self.openai.num_tokens_from_string(answer)
                await self.dingtalk.send_text(
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
            if isinstance(e, openai.BadRequestError) and e.code == 'context_length_exceeded':
                await self.dingtalk.send_markdown(
                    "好长 orz",
                    "<font color=silver>好家伙，这也太长了…… 弄短点吧 [傻笑] <br />（%s）" % e.args,
                    session_webhook)
            else:
                await self.dingtalk.send_markdown(
                    "我错了 orz",
                    "<font color=silver>完，出错啦！暂时没法用咯…… 等会再试试吧 [傻笑] <br />（%s）" % e.args,
                    session_webhook)

    def check_signature(self, timestamp, sign):
        return self.dingtalk.check_signature(timestamp, sign)

    async def processes_multimodal_conversation(self, sender, conversations, file_info=None):
        content, usage = await self.dashscope.multimodal_conversation(conversations)
        print("[{}]->[{}]: {}".format(
            handler.dashscope.model, sender, content.rstrip().replace("\n", "\n  | ")))
        return {
            "msgtype": "text",
            "text": {
                "content": content + message_bottom(
                    {"in": usage['input_tokens'], "out": usage['output_tokens'], "img": usage['image_tokens']},
                    handler.dashscope.model, file_info)
            }
        }


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


def message_bottom(usage, model, file_name=None):
    if file_name is None:
        return f"\n\n( --- Used up {usage} tokens. --- )\n( --- {model} --- )"
    else:
        return f"\n\n( --- {file_name} --- )\n( --- Used up {usage} tokens. --- )\n( --- {model} --- )"


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
    number_workers=4)

app = FastAPI(lifespan=lifespan)

download_dir = os.getenv("DOWNLOAD_DIR")
if download_dir is None:
    logging.info("You can modify the file save directory by setting the environment variable DOWNLOAD_DIR.")
    download_dir = './downloads'
print("File download directory: {}".format(download_dir))


def download_file(url, dir_path, file_extension=None):
    response = requests.get(url)
    if response.status_code == 200:
        file_content = response.content
        md5_hash = hashlib.md5(file_content).hexdigest()
        parsed_url = urlparse(url)
        file_name = os.path.basename(parsed_url.path)
        if file_extension is None:
            file_extension = os.path.splitext(file_name)[1]
        file_name = md5_hash[:8].upper() + file_extension
        dir_name = os.path.abspath(dir_path)
        os.makedirs(dir_name, exist_ok=True)

        file_path = os.path.join(dir_name, file_name)
        with open(file_path, 'wb') as file:
            file.write(response.content)
        print(f'File has been saved as：{file_path}')
        return file_path
    else:
        print('File download error')


@app.post("/")
async def root(request: Request):
    app_key = handler.check_signature(
        request.headers.get('timestamp'),
        request.headers.get('sign'))

    # receive from dingtalk
    # https://open.dingtalk.com/document/orgapp/receive-message
    message = await request.json()

    if message['msgtype'] == 'audio':
        print("[{}] sent a message of type 'audio'.  -> {}".format(
            message['senderNick'], message['content']['recognition']))
        # process as normal text message
        message['text'] = {
            "content": message['content']['recognition']
        }
    elif message['msgtype'] == 'picture':
        download_code = message['content']['downloadCode']
        print("[{}] sent a message of type 'picture'.  -> {}".format(message['senderNick'], download_code))
        image_url = await handler.dingtalk.get_file_download_url(app_key, download_code)
        file_path = download_file(image_url, download_dir)
        return await handler.processes_multimodal_conversation(message['senderNick'], [
            {"image": "file://" + os.path.abspath(file_path)},
            {"text": "这是什么?"}
        ], os.path.basename(file_path))
    elif message['msgtype'] == 'richText':
        questions = []
        rich_text = message['content']['richText']
        images = []
        for element in rich_text:
            if 'type' in element and element['type'] == 'picture':
                download_code = element['downloadCode']
                image_url = await handler.dingtalk.get_file_download_url(app_key, download_code)
                file_path = download_file(image_url, download_dir)
                questions.append({"image": "file://" + os.path.abspath(file_path)})
                images.append(os.path.basename(file_path))
            elif 'text' in element:
                questions.append({"text": element['text']})
        return await handler.processes_multimodal_conversation(message['senderNick'], questions, images)
    elif message['msgtype'] == 'file':
        file_name = message['content']['fileName']
        ext = os.path.splitext(file_name)[1]
        if ext != '.txt':
            return await send_unknown_message(message)
        download_code = message['content']['downloadCode']
        file_url = await handler.dingtalk.get_file_download_url(app_key, download_code)
        file_path = download_file(file_url, download_dir, ext)
        # guess encoding
        with open(file_path, 'rb') as f:
            content = f.read()
            result = chardet.detect(content)
            encoding = result['encoding']
        # read content
        with open(file_path, 'r', encoding=encoding) as file:
            content = file.read()
            print(content)
        # process as normal text message
        message['text'] = {
            "content": content
        }
    elif message['msgtype'] != 'text':
        return await send_unknown_message(message)

    # prepare to call
    session_webhook = message['sessionWebhook']
    sender_nick = message['senderNick']
    sender_content = message['text']['content']

    # Concurrency Control
    if handler.is_session_webhook_in_processing(session_webhook):
        processing_message = handler.get_processing_messages(session_webhook)
        print("[{}](忽略): {}".format(sender_nick, sender_content.replace("\n", "\n  | ")))

        return {
            "msgtype": "markdown",
            "markdown": {
                "title": "[忙疯了]好快...",
                "text": "<font color=silver>你发的太快了…… 有点处理不过来了呢…… [尴尬]\n\n\n我还在琢磨：\""
                        + truncate_string(processing_message) + "\""
            }
        }

    print("[{}]: {}".format(sender_nick, sender_content.replace("\n", "\n  | ")))

    # call openai
    handler.handle_request({
        'session_webhook': session_webhook,
        'send_to': sender_nick,
        'message': sender_content
    })

    # Do not reply now, reply later using webhook method.
    return {
        "msgtype": "empty"
    }


async def send_unknown_message(message):
    print("[{}] sent a message of type '{}'.  -> {}".format(message['senderNick'], message['msgtype'], message))
    return {
        "msgtype": "text",
        "text": {
            "content": "我暂时无法理解这个类型的信息。"
        }
    }


if __name__ == '__main__':
    import uvicorn
    import os

    port = 8000

    if os.getenv("SERVER_PORT") is not None:
        port = int(os.getenv("SERVER_PORT"))

    uvicorn.run(app, host="0.0.0.0", port=port)
