import math
import os
from typing import List
from PIL import Image

import logging
from anthropic import Stream, Anthropic
from anthropic.types import MessageStreamEvent, MessageParam, MessageStartEvent, MessageDeltaEvent, \
    ContentBlockStartEvent, ContentBlockDeltaEvent, ImageBlockParam, TextBlockParam
from anthropic.types.image_block_param import Source

from components.ai_side.chatbot_client import ChatMessage, ChatBotServerType, ChatBotClient, TokenUsage, ImageBlock, \
    DisabledMultiModalConversation
from components.tools import image_to_base64

logging.basicConfig(level=logging.WARN)


def _calculate_tokens_of_images(messages: List[ChatMessage], enable_multimodal=False) -> int:
    total_tokens = 0
    if not enable_multimodal:
        return total_tokens
    for message in messages:
        if isinstance(message.content, str):
            continue
        else:
            for content in list(message.content):
                if isinstance(content, ImageBlock):
                    file_path = content.image
                    image = Image.open(file_path)
                    width, height = image.size
                    tokens = math.ceil((width * height) / 750)
                    print("Content include a image size of {}x{}: cost {} tokens".format(width, height, tokens))
                    total_tokens += tokens
    return total_tokens


def _build_message_param(message: ChatMessage, enable_multimodal=False) -> MessageParam:
    if isinstance(message.content, str):
        return MessageParam(content=message.content, role=message.role)
    else:
        contents = []
        for content in list(message.content):
            if isinstance(content, ImageBlock):
                if not enable_multimodal:
                    raise DisabledMultiModalConversation()
                file_path = content.image
                file_name = os.path.basename(file_path)

                file_ext = os.path.splitext(file_name)[1]
                image_data = image_to_base64(file_path)

                contents.append(
                    ImageBlockParam(
                        type="image",
                        source=Source(
                            type="base64",
                            data=image_data,
                            media_type='image/png' if file_ext == '.png' else 'image/jpeg'
                        )
                    )
                )
            else:  # if isinstance(content, TextBlock):
                contents.append(TextBlockParam(type="text", text=content.text))
        return MessageParam(content=contents, role=message.role)


class IterableMessageChunk:
    def __init__(self, events: Stream[MessageStreamEvent], token_usage: TokenUsage):
        self.events = events
        self.token_usage = token_usage

    def __iter__(self):
        return self

    def __next__(self):
        try:
            event = self.events.__next__()
            if isinstance(event, MessageStartEvent):
                self.token_usage.input_tokens = event.message.usage.input_tokens
                self.token_usage.output_tokens = event.message.usage.output_tokens
            if isinstance(event, MessageDeltaEvent):
                self.token_usage.output_tokens = event.usage.output_tokens
            if isinstance(event, ContentBlockStartEvent):
                return event.content_block.text
            if isinstance(event, ContentBlockDeltaEvent):
                return event.delta.text
            return ""
        except StopIteration:
            raise StopIteration


class AnthropicChatBotClient(ChatBotClient):
    DEFAULT_SYSTEM_PROMPT = ("The assistant is Claude, created by Anthropic."
                             "Unless otherwise specified, answer in Chinese."
                             "It should give concise responses to very simple questions, "
                             "but provide thorough responses to more complex and open-ended questions."
                             "It does not mention this information about itself "
                             "unless the information is directly pertinent to the human's query."
                             "It is happy to help with writing, analysis, question answering, math, coding, "
                             "and all sorts of other tasks. It uses markdown for coding.")
    DEFAULT_MODEL_NAME = "claude-3-sonnet-20240229"

    # claude-3-opus-20240229

    def __init__(self,
                 api_key=None,
                 base_url: str = None,
                 model_name: str = None,
                 preset_system_prompt: str = None,
                 enable_streaming: bool = None,
                 enable_multimodal: bool = None):
        super().__init__(api_key, base_url, model_name, preset_system_prompt, enable_streaming, enable_multimodal)

        self.client = Anthropic(api_key=self.api_key, base_url=self.base_url)

    @property
    def chat_model_name(self) -> str:
        return self.model_name

    @property
    def server_type(self) -> ChatBotServerType:
        return ChatBotServerType.Anthropic

    def completions(self, messages: List[ChatMessage], system: str = None):
        # messages = [
        #     {
        #         "role": "user",
        #         "content": "Hello, Claude",
        #     }
        # ]
        response = self.client.messages.create(
            model=self.model_name,
            max_tokens=1024,
            temperature=0,
            system=self.preset_system_prompt if system is None else system,
            messages=[_build_message_param(message, self.enable_multimodal) for message in messages],
            stream=self.enable_streaming
        )
        image_tokens = _calculate_tokens_of_images(messages, self.enable_multimodal)
        if not self.enable_streaming:
            return (
                [response.content[0].text],
                TokenUsage(input_tokens=response.usage.input_tokens,
                           output_tokens=response.usage.output_tokens,
                           image_tokens=image_tokens)
            )
        else:
            token_usage = TokenUsage(input_tokens=0, output_tokens=0, image_tokens=image_tokens)
            return IterableMessageChunk(response, token_usage), token_usage


if __name__ == '__main__':
    os.environ['CHATBOT_SERVER_API_KEY'] = os.environ.get('ANTHROPIC_API_KEY')
    os.environ['CHATBOT_SERVER_BASE_URL'] = os.environ.get('ANTHROPIC_BASE_URL')

    client = AnthropicChatBotClient(enable_streaming=False)
    msgs = [
        {"role": "user", "content": "写一个Hello world"},
    ]
    result, usage = client.completions([ChatMessage(role=msg['role'], content=msg['content']) for msg in msgs])
    for chunk in result:
        print(chunk)
    print(usage)
