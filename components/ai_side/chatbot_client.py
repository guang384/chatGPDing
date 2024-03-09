import os
from abc import abstractmethod, ABC
from enum import Enum
from typing import Iterable, Literal, Union, List

from pydantic import BaseModel

from components.tools import is_true


class ChatBotServerType(Enum):
    DashScope = "dashscope"
    OpenAI = "openai"
    Anthropic = "anthropic"


class ChatBotServerEnv(Enum):
    API_KEY = "CHATBOT_SERVER_API_KEY"
    BASE_URL = "CHATBOT_SERVER_BASE_URL"
    MODEL_NAME = "CHATBOT_SERVER_CHAT_MODEL"
    PRESET_SYSTEM_PROMPT = "CHATBOT_SERVER_SYSTEM_PROMPT"
    ENABLE_STREAMING = "CHATBOT_SERVER_STREAMING_ENABLE"
    ENABLE_MULTIMODAL = "CHATBOT_SERVER_MULTIMODAL_ENABLE"


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


class ChatBotClient(ABC):
    DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant. "

    DEFAULT_MODEL_NAME = "Need to set environment variable: CHATBOT_SERVER_MODEL_NAME"

    def __init__(self,
                 api_key: str = None,
                 base_url: str = None,
                 model_name: str = None,
                 preset_system_prompt: str = None,
                 enable_streaming: bool = None,
                 enable_multimodal: bool = None):

        self.api_key = api_key if api_key is not None else os.environ.get(ChatBotServerEnv.API_KEY.value)
        if self.api_key is None:
            raise SystemError(f"Need to set environment variable: {ChatBotServerEnv.API_KEY.value}.")

        self.base_url = base_url if base_url is not None else os.environ.get(ChatBotServerEnv.BASE_URL.value)
        if self.base_url is not None:
            print("Rewrite the base URL of Chatbot Server to %s." % self.base_url)

        self.model_name = model_name if model_name is not None else os.environ.get(ChatBotServerEnv.MODEL_NAME.value)
        ''' https://docs.anthropic.com/claude/docs/models-overview '''
        if self.model_name is None:
            self.model_name = self.DEFAULT_MODEL_NAME
        print("Chatbot server use model:", self.model_name)

        self.enable_streaming = is_true(os.getenv(ChatBotServerEnv.ENABLE_STREAMING.value))
        if not self.enable_streaming and enable_streaming is not None:
            self.enable_streaming = enable_streaming
        if self.enable_streaming:
            print("Chatbot server streaming response enabled")

        self.enable_multimodal = is_true(os.getenv(ChatBotServerEnv.ENABLE_MULTIMODAL.value))
        if not self.enable_multimodal and enable_multimodal is not None:
            self.enable_multimodal = enable_multimodal
        if self.enable_multimodal:
            print("Chatbot server multimodal conversation enabled")

        self.preset_system_prompt = os.environ.get(ChatBotServerEnv.PRESET_SYSTEM_PROMPT.value)
        if preset_system_prompt is not None:
            self.preset_system_prompt = preset_system_prompt
        if preset_system_prompt is None:
            self.preset_system_prompt = self.DEFAULT_SYSTEM_PROMPT

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
    def multimodal_enabled(self) -> bool:
        return self.enable_multimodal

    @abstractmethod
    def completions(self,
                    messages: List[ChatMessage],
                    system: str = None) -> tuple[Iterable[str], TokenUsage]:
        raise NotImplementedError


if __name__ == '__main__':
    msg = ChatMessage(content="Hello", role="user")
    print("content: {}".format(msg.content))
