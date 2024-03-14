import logging
import os
from abc import abstractmethod, ABC
from enum import Enum
from typing import Iterable, Literal, Union, List

from pydantic import BaseModel

from components.tools import is_true


class ImageBlock(BaseModel):
    image: str


class TextBlock(BaseModel):
    text: str


class ChatMessage(BaseModel):
    content: Union[str, List[Union[ImageBlock, TextBlock]]]
    role: Literal["user", "assistant"]


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    image_tokens: int


class ContextLengthExceededException(Exception):
    pass


class UnsupportedMultiModalMessageError(Exception):
    pass


class DisabledMultiModalConversation(Exception):
    pass


class UploadingTooManyImagesException(Exception):
    pass


class ChatBotServerType(Enum):
    DashScope = "dashscope"
    OpenAI = "openai"
    Anthropic = "anthropic"


class ChatBotClient(ABC):
    DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant. "

    DEFAULT_MODEL_NAME = "Need to set environment variable: CHATBOT_SERVER_MODEL_NAME"

    def __init__(self,
                 api_key: str,
                 base_url: str = None,
                 model_name: str = None,
                 preset_system_prompt: str = None,
                 enable_streaming: bool = None,
                 enable_multimodal: bool = None, ):
        self.api_key = api_key
        self.base_url = base_url

        self.model_name = self.DEFAULT_MODEL_NAME if model_name is None else model_name
        self.preset_system_prompt = self.DEFAULT_SYSTEM_PROMPT if preset_system_prompt is None else preset_system_prompt

        self.enable_streaming = self.supports_streaming_response if enable_streaming is None else enable_streaming
        if self.enable_streaming and not self.supports_streaming_response:
            logging.warning("The service has enabled the stream response mode through configuration, "
                            "but the service does not support this mode yet.")
        self.enable_multimodal = self.has_multi_modal_ability if enable_multimodal is None else enable_multimodal
        if self.enable_multimodal and not self.has_multi_modal_ability:
            logging.warning("The multimodal capability has been enabled through configuration, "
                            "but the service does not yet support this capability.")

    @property
    @abstractmethod
    def server_type(self) -> ChatBotServerType:
        raise NotImplementedError

    @property
    def chat_model_name(self) -> str:
        return self.model_name

    @property
    def stream_enabled(self) -> bool:
        return self.enable_streaming

    @property
    @abstractmethod
    def supports_streaming_response(self) -> bool:
        raise NotImplementedError

    @property
    def multimodal_enabled(self) -> bool:
        return self.enable_multimodal

    @property
    @abstractmethod
    def has_multi_modal_ability(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def completions(self,
                    messages: List[ChatMessage],
                    system: str = None) -> tuple[Iterable[str], TokenUsage]:
        raise NotImplementedError


if __name__ == '__main__':
    msg = ChatMessage(content="Hello", role="user")
    print("content: {}".format(msg.content))
