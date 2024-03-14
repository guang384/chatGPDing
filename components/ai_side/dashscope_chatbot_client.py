import json
import logging
import os
from http import HTTPStatus
from typing import List, Iterable

import dashscope
from dashscope.api_entities.dashscope_response import MultiModalConversationResponse

from components.ai_side.chatbot_client import ChatBotClient, ChatMessage, TokenUsage, ChatBotServerType, ImageBlock, \
    DisabledMultiModalConversation


class DashscopeChatBotClient(ChatBotClient):

    @property
    def supports_streaming_response(self) -> bool:
        return False

    @property
    def has_multi_modal_ability(self) -> bool:
        return True

    DEFAULT_SYSTEM_PROMPT = "你是达摩院的生活助手机器人。除非特别说明，请使用中文回复。"

    DEFAULT_MODEL_NAME = 'qwen-vl-max'

    @property
    def server_type(self) -> ChatBotServerType:
        return ChatBotServerType.DashScope

    def __init__(self,
                 api_key=None,
                 base_url: str = None,
                 model_name: str = None,
                 preset_system_prompt: str = None,
                 enable_streaming: bool = None,
                 enable_multimodal: bool = None):
        super().__init__(api_key, base_url, model_name, preset_system_prompt, enable_streaming, enable_multimodal)

        if self.base_url is not None:
            logging.warning("The Dashscope ChatBot Client is currently unable "
                            "to accommodate the customization of the base URL.")

    def completions(self, messages: List[ChatMessage], system: str = None) -> tuple[Iterable[str], TokenUsage]:
        chat_messages = [{
            "role": "system",
            "content": [
                {"text": self.preset_system_prompt if system is None else system}
            ]
        }]
        for message in messages:
            if isinstance(message.content, str):
                chat_messages.append({
                    "role": message.role,
                    "content": [
                        {"text": message.content}
                    ]
                })
            else:
                contents = []
                for content in message.content:
                    if isinstance(content, ImageBlock):
                        if not self.enable_multimodal:
                            raise DisabledMultiModalConversation()
                        contents.append({"image": "file://" + content.image})
                    else:
                        contents.append({"text": content.text})
                chat_messages.append({
                    "role": message.role,
                    "content": contents
                })

        response: MultiModalConversationResponse = dashscope.MultiModalConversation.call(api_key=self.api_key,
                                                                                         model=self.chat_model_name,
                                                                                         messages=chat_messages)

        # The response status_code is HTTPStatus.OK indicate success,
        # otherwise indicate request is failed, you can get error code
        # and message from code and message.
        if response.status_code == HTTPStatus.OK:
            return (
                [response.output.choices[0].message.content[0]['text']],
                TokenUsage(input_tokens=response.usage.input_tokens,
                           output_tokens=response.usage.output_tokens,
                           image_tokens=response.usage.image_tokens if 'image_tokens' in response.usage else 0)
            )
        else:
            raise RuntimeError("Error while call dashscope :" + json.dumps(response, ensure_ascii=False))


if __name__ == '__main__':
    os.environ['CHATBOT_SERVER_API_KEY'] = os.environ.get('DASHSCOPE_API_KEY')

    client = DashscopeChatBotClient()
    msgs = [
        {"role": "user", "content": "Hello, Claude"},
    ]
    result, usage = client.completions([ChatMessage(role=msg['role'], content=msg['content']) for msg in msgs])
    for chunk in result:
        print(chunk)
    print(usage)
