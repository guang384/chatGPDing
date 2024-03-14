import os
import re
import time
import traceback
from typing import List

import chardet

from components.ai_side.chatbot_client import ChatBotClient, ChatMessage, ContextLengthExceededException, \
    UnsupportedMultiModalMessageError, ImageBlock, TextBlock, UploadingTooManyImagesException, \
    DisabledMultiModalConversation, TokenUsage
from components.im_side.dingtalk_client import DingtalkClient
from components.message_handler import MessageHandler, QueuedRequest, ConcurrentRequestException
from components.tools import download_file, truncate_string


def _create_busy_message(content: str):
    return {
        "msgtype": "markdown",
        "markdown": {
            "title": "[忙疯了]好快...",
            "text": "<font color=silver>你发的太快了…… 有点处理不过来了呢…… [尴尬]\n\n\n我还在琢磨：\""
                    + truncate_string(content) + "\""
        }
    }


def _create_unknown_msgtype_message(message):
    print("[{}] sent a message of type '{}'.  -> {}".format(message['senderNick'], message['msgtype'], message))
    return {
        "msgtype": "text",
        "text": {
            "content": "我暂时无法理解这个类型的信息。"
        }
    }


def _create_do_not_rely_other_message():
    return {
        "msgtype": "markdown",
        "markdown": {
            "title": "[裂开]啊这...",
            "text": "<font color=silver>不要引用其他消息…… 我看不到…… [闭嘴]"
        }
    }


def _create_message_bottom(usage: TokenUsage, chat_model_name: str, file_names: List[str] = None):
    usage_dict = {"in": usage.input_tokens, "out": usage.output_tokens}
    if usage.image_tokens > 0:
        usage_dict["img"] = usage.image_tokens

    if file_names is None or len(file_names) == 0:
        return f"\n\n( --- Used up {usage_dict} tokens. --- )\n( --- {chat_model_name} --- )"
    else:
        return f"\n\n( --- {file_names} --- )\n( --- Used up {usage_dict} tokens. --- )\n( --- {chat_model_name} --- )"


def _create_empty_message():
    """
    send empty message will not reply to the message to the user
    Replying with an empty message means not responding immediately, reply later using webhook method.
    """
    return {
        "msgtype": "empty"
    }


def _create_should_one_to_one_message():
    return {
        "msgtype": "text",
        "text": {
            "content": "emm... 还是小窗吧[闭嘴]"
        }
    }


def _is_valid_md_code_start(line) -> tuple[bool, int]:
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


def _is_valid_md_code_end(line, backticks_count) -> bool:
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


def _organize_iterable_response(iterable_reply):
    """
    Iterate through the data one by one, return once a complete content is formed, until completion.
    """
    accumulated_content = ''
    for chunk in iterable_reply:
        if chunk is not None and len(chunk) > 0:
            chunk = str(chunk)
            accumulated_content += chunk
            if '\n' not in chunk:
                continue

            if '```' not in accumulated_content:
                parts = accumulated_content.rsplit('\n\n', 1)
                complete_content_block = parts[0]
                if len(complete_content_block) > 100:
                    if len(parts) > 1:
                        accumulated_content = parts[1]
                    else:
                        accumulated_content = ''
                    yield complete_content_block, False

                continue
            # to lines
            # Notice: if the original string ends with a newline character ("\n", "\r", or "\r\n"),
            # this trailing newline is ignored
            lines = accumulated_content.splitlines() + ([""] if accumulated_content.endswith('\n') else [])
            last_code_block_start_line_index = -1
            last_code_block_end_line_index = -1
            last_code_block_backticks_number = -1
            for index, line in enumerate(lines):
                if last_code_block_start_line_index < 0:
                    started, backticks_number = _is_valid_md_code_start(line)
                    if started:
                        last_code_block_start_line_index = index
                        last_code_block_backticks_number = backticks_number
                else:
                    ended = _is_valid_md_code_end(line, last_code_block_backticks_number)
                    if ended:
                        last_code_block_start_line_index = -1
                        last_code_block_backticks_number = -1
                        last_code_block_end_line_index = index
            if last_code_block_start_line_index > -1:  # start but not end
                complete_content_block = '\n'.join(lines[0:last_code_block_start_line_index])
                accumulated_content = '\n'.join(lines[last_code_block_start_line_index:])
                if len(complete_content_block) > 0:
                    yield complete_content_block, False
                continue
            if last_code_block_end_line_index == -1:  # no block
                parts = accumulated_content.rsplit('\n', 1)
                complete_content_block = parts[0]
                accumulated_content = parts[1]
                if len(complete_content_block) > 0:
                    yield complete_content_block, False
            else:  # has block and already end
                complete_content_block = '\n'.join(lines[0:last_code_block_end_line_index + 1])
                accumulated_content = '\n'.join(lines[last_code_block_end_line_index + 1:])
                if len(complete_content_block) > 0:
                    yield complete_content_block, False
    yield accumulated_content, True


# Matching image name, image name is the first 8 characters of MD5 encoding and in uppercase.
MD5_FILENAME_PATTERN = r"([0-9A-F]{8}\.png|[0-9A-F]{8}\.jpg)"


class DingtalkMessageHandler(MessageHandler):
    def __init__(self,
                 chatbot_client: ChatBotClient,
                 dingtalk_client: DingtalkClient,
                 download_dir: str = None,
                 worker_threads: int = None):
        super().__init__(worker_threads=worker_threads)
        self.chatbot_client = chatbot_client
        self.dingtalk_client = dingtalk_client

        self.download_dir = download_dir if download_dir is not None else os.getenv("DOWNLOAD_DIR")
        if self.download_dir is None:
            print("You can modify the file save directory by setting the environment variable DOWNLOAD_DIR.")
            self.download_dir = './downloads'
        print(f"All files from DingTalk messages will be downloaded to directory: {os.path.abspath(self.download_dir)}")

    def check_signature(self, timestamp, sign) -> str:
        return self.dingtalk_client.check_signature(timestamp, sign)

    async def process_request(self, request: QueuedRequest) -> None:
        """
        Call the chatbot to process specific messages.
        :param request:
        :return:
        """
        session_webhook = request.parameters["session_webhook"]
        send_to = request.parameters["send_to"]
        content = request.parameters["content"]

        # check content
        # If the file content contains image names and the images exist, use a multimodal model to answer.
        images = re.findall(MD5_FILENAME_PATTERN, content)

        if len(images) > 10:
            raise UploadingTooManyImagesException("You can include multiple images in a single request, "
                                                  "but up to 10 images allowed.")

        # prepare contents
        multimodal_contents = []
        if re.search(MD5_FILENAME_PATTERN, content):
            segments = re.split(MD5_FILENAME_PATTERN, content)
            for segment in segments:
                if len(segment.strip()) == 0:
                    continue
                if re.search(MD5_FILENAME_PATTERN, segment):
                    dir_name = os.path.abspath(self.download_dir)
                    file_path = os.path.join(dir_name, segment)
                    if os.path.exists(file_path):
                        multimodal_contents.append(ImageBlock(image=file_path))
                        continue
                    else:
                        images.remove(segment)
                multimodal_contents.append(TextBlock(text=segment))

        # prepare chat messages
        if len(images) > 0:
            # multimodal messages
            chat_messages = [ChatMessage(role='user', content=multimodal_contents)]
        else:
            # text only
            chat_messages = [ChatMessage(role='user', content=content)]

        # send to chatbot server and get reply
        start_time = time.perf_counter()
        try:
            iterable_reply, usage = self.chatbot_client.completions(chat_messages)
            end_time = time.perf_counter()
            print("Message received from chatbot server start at {:.3f} s.".format((end_time - start_time)))

            if not self.chatbot_client.stream_enabled:
                content = list(iterable_reply)[0]
                content += _create_message_bottom(usage, self.chatbot_client.chat_model_name, images)
                await self.send_message_to_dingtalk(session_webhook, send_to, content)
            else:
                need_resend = ""
                # organize iterable response
                for content, is_end in _organize_iterable_response(iterable_reply):
                    content = need_resend + content.rstrip()
                    if is_end:
                        content += _create_message_bottom(usage, self.chatbot_client.chat_model_name, images)
                    success = await self.send_message_to_dingtalk(session_webhook, send_to, content)
                    need_resend = "" if success else (need_resend + "\n\n" + content)

            print("Request chatbot server duration: {:.3f} s. Estimated completion Tokens: {}.".format(
                (end_time - start_time), usage))

        except Exception as e:
            end_time = time.perf_counter()
            print("Error Request chatbot server duration: {:.3f} s.".format((end_time - start_time)))

            if isinstance(e, ContextLengthExceededException):
                await self.dingtalk_client.send_markdown(
                    "好长 orz",
                    "<font color=silver>好家伙，这也太长了…… 弄短点吧 [傻笑] <br />(%s)" % e.args,
                    session_webhook)
            elif isinstance(e, UnsupportedMultiModalMessageError):
                await self.dingtalk_client.send_markdown(
                    "哎呀 orz",
                    "<font color=silver>你发图片…… 我暂时只能理解文字消息呀 [黑眼圈]",
                    session_webhook)
            elif isinstance(e, UploadingTooManyImagesException):
                await self.dingtalk_client.send_markdown(
                    "好多 orz",
                    "<font color=silver>你发图片…… 发太多了啊 [投降] <br />(%s)" % e.args,
                    session_webhook)
            elif isinstance(e, DisabledMultiModalConversation):
                await self.dingtalk_client.send_markdown(
                    "可是 orz",
                    "<font color=silver>啊…… 我暂时不能帮你解读图片 [对不起]",
                    session_webhook)
            else:
                traceback.print_exc()
                await self.dingtalk_client.send_markdown(
                    "我错了 orz",
                    "<font color=silver>完，出错啦！暂时没法用咯…… 等会再试试吧 [傻笑] <br />(%s)" % str(e.args),
                    session_webhook)

    async def send_message_to_dingtalk(self, session_webhook, send_to, content) -> bool:
        print("[{}]->[{}]: {}".format(self.chatbot_client.chat_model_name, send_to,
                                      content.rstrip().replace("\n", "\n  | ")))
        try:
            await self.dingtalk_client.send_text(content, session_webhook)
        except Exception as e:
            print("Send answer to dingtalk Failed,"
                  "The current message failed to send and is waiting to be resent.", e.args)
            return False
        return True

    async def handle_message_from_dingtalk(self, app_key: str, message: dict) -> dict:
        """
        handle message from DingTalk
        https://open.dingtalk.com/document/orgapp/receive-message
        :param app_key:
        :param message:
        :return message:
        """
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
            image_url = await self.dingtalk_client.get_file_download_url(app_key, download_code)
            file_path = download_file(image_url, self.download_dir)
            # process as normal text message
            message['text'] = {
                "content": os.path.basename(file_path)
            }

        elif message['msgtype'] == 'richText':
            segments = []
            rich_text = message['content']['richText']
            for element in rich_text:
                if 'type' in element and element['type'] == 'picture':
                    download_code = element['downloadCode']
                    image_url = await self.dingtalk_client.get_file_download_url(app_key, download_code)
                    file_path = download_file(image_url, self.download_dir)
                    segments.append(os.path.basename(file_path))
                elif 'text' in element:
                    segments.append(element['text'])
                # process as normal text message
                message['text'] = {
                    "content": ' '.join(segments)
                }

        elif message['msgtype'] == 'file':
            file_name = message['content']['fileName']
            ext = os.path.splitext(file_name)[1]
            if ext != '.txt':
                return _create_unknown_msgtype_message(message)
            download_code = message['content']['downloadCode']
            file_url = await self.dingtalk_client.get_file_download_url(app_key, download_code)
            file_path = download_file(file_url, self.download_dir, ext)
            # guess encoding
            with open(file_path, 'rb') as f:
                content = f.read()
                result = chardet.detect(content)
                encoding = result['encoding']
            # read content
            with open(file_path, 'r', encoding=encoding) as file:
                content = file.read()
            # process as normal text message
            message['text'] = {
                "content": content
            }

        elif message['msgtype'] != 'text':
            return _create_unknown_msgtype_message(message)

        # should one to one
        userid = message['senderStaffId']
        robot_code = message['robotCode']

        if (not self.handlingGroupMessages) and message['conversationType'] == '2':
            await self.dingtalk_client.one_to_one_text("来，这边~ [坏笑]", robot_code, userid, app_key)
            return _create_should_one_to_one_message()

        # Do not rely on other messages
        if 'originalProcessQueryKey' in message or 'originalMsgId' in message:
            return _create_do_not_rely_other_message()

        # prepare to call
        session_webhook = message['sessionWebhook']
        sender_nick = message['senderNick']
        sender_content = message['text']['content']

        # Add to queue for processing.
        request = {
            'session_webhook': session_webhook,
            'send_to': sender_nick,
            'userid': userid,
            'robot_code': robot_code,
            'content': sender_content
        }

        try:
            self.add_new_request_to_queue(session_webhook, request)
            print("[{}]: {}".format(sender_nick, sender_content.replace("\n", "\n  | ")))
        except ConcurrentRequestException as e:
            print("[{}](忽略): {}".format(sender_nick, sender_content.replace("\n", "\n  | ")))
            processing_queued_request: QueuedRequest = e.args[1]
            return _create_busy_message(processing_queued_request.parameters["message"])

        return _create_empty_message()


if __name__ == '__main__':
    some_content = """
好的,以下是一个用Python编写的Hello World程序:

```python
print("Hello World!")
```

这个程序只有一行代码,它使用Python内置的`print()`函数在终端或控制台上输出字符串"Hello World!"。

当您运行这个Python程序时,它会在屏幕上打印出"Hello World!"。这是一个非常简单但经典的程序,通常被用作编程入门的第一个例子。
    """
    print("===")
    for seg, content_is_end in _organize_iterable_response(list(some_content)):
        print(f"{seg}")
        print("---" if not content_is_end else "===")

    s1 = "一些句子\n呵呵\n"
    s2 = "一些句子\n呵呵"
    print(s1.splitlines())
    print(s2.splitlines())

    text = "line1\nline2\nline3\n"
    print(text.split("\n"))
