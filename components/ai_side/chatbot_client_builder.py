import logging
import os
from enum import Enum

from components.ai_side.anthropic_chatbot_client import AnthropicChatBotClient
from components.ai_side.chatbot_client import ChatBotClient, ChatBotServerType
from components.ai_side.dashscope_chatbot_client import DashscopeChatBotClient
from components.ai_side.openai_chatbot_client import OpenaiChatBotClient
from components.tools import is_true


class ChatBotServerEnv(Enum):
    API_KEY = "CHATBOT_SERVER_API_KEY"
    BASE_URL = "CHATBOT_SERVER_BASE_URL"
    MODEL_NAME = "CHATBOT_SERVER_CHAT_MODEL"
    PRESET_SYSTEM_PROMPT = "CHATBOT_SERVER_SYSTEM_PROMPT"
    ENABLE_STREAMING = "CHATBOT_SERVER_STREAMING_ENABLE"
    ENABLE_MULTIMODAL = "CHATBOT_SERVER_MULTIMODAL_ENABLE"


class ChatBotClientBuilder:

    def build(self) -> ChatBotClient:
        if self.chatbot_server_type == ChatBotServerType.Anthropic:
            return AnthropicChatBotClient(self.api_key,
                                          self.base_url,
                                          self.model_name,
                                          self.preset_system_prompt,
                                          self.enable_streaming,
                                          self.enable_multimodal)
        elif self.chatbot_server_type == ChatBotServerType.OpenAI:
            return OpenaiChatBotClient(self.api_key,
                                       self.base_url,
                                       self.model_name,
                                       self.preset_system_prompt,
                                       self.enable_streaming,
                                       self.enable_multimodal)
        else:
            return DashscopeChatBotClient(self.api_key,
                                          self.base_url,
                                          self.model_name,
                                          self.preset_system_prompt,
                                          self.enable_streaming,
                                          self.enable_multimodal)

    def __init__(self,
                 chatbot_server_type: ChatBotServerType,
                 api_key: str = None,
                 base_url: str = None,
                 model_name: str = None,
                 preset_system_prompt: str = None,
                 enable_streaming: bool = None,
                 enable_multimodal: bool = None):

        self.chatbot_server_type = chatbot_server_type

        self.api_key = api_key if api_key is not None else os.environ.get(ChatBotServerEnv.API_KEY.value)
        if self.api_key is None:
            raise SystemError(f"Need to set environment variable: {ChatBotServerEnv.API_KEY.value}.")

        self.base_url = base_url if base_url is not None else os.environ.get(ChatBotServerEnv.BASE_URL.value)
        if self.base_url is not None:
            logging.info("Chatbot Server use base url: %s" % self.base_url)

        self.model_name = model_name if model_name is not None else os.environ.get(ChatBotServerEnv.MODEL_NAME.value)
        if self.model_name is not None:
            logging.info("Chatbot server default use model: %s" % self.model_name)

        self.enable_streaming = enable_streaming
        if self.enable_streaming is None and os.getenv(ChatBotServerEnv.ENABLE_STREAMING.value) is not None:
            self.enable_streaming = is_true(os.getenv(ChatBotServerEnv.ENABLE_STREAMING.value))
            if self.enable_streaming:
                logging.info("Chatbot Server streaming response enabled.")

        self.enable_multimodal = enable_multimodal
        if self.enable_multimodal is None and os.getenv(ChatBotServerEnv.ENABLE_MULTIMODAL.value) is not None:
            self.enable_multimodal = is_true(os.getenv(ChatBotServerEnv.ENABLE_MULTIMODAL.value))
            if self.enable_multimodal:
                logging.info("Chatbot Server multimodal conversation enabled.")

        self.preset_system_prompt = preset_system_prompt
        if preset_system_prompt is None and os.getenv(ChatBotServerEnv.PRESET_SYSTEM_PROMPT.value) is not None:
            self.preset_system_prompt = os.environ.get(ChatBotServerEnv.PRESET_SYSTEM_PROMPT.value)
            logging.info("Chatbot Server use a preset system prompt: %s ..." % self.preset_system_prompt[:20])


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    ChatBotClientBuilder(ChatBotServerType.OpenAI).build()
