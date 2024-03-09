import os
from typing import Iterable, List

import logging

import openai
import tiktoken
from openai import OpenAI, Stream
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionSystemMessageParam, \
    ChatCompletionUserMessageParam, ChatCompletionAssistantMessageParam, ChatCompletionChunk

from components.ai_side.chatbot_client import ChatMessage, ChatBotServerType, ChatBotClient, TokenUsage, \
    ContextLengthExceededException, UnsupportedMultiModalMessageError

logging.basicConfig(level=logging.WARN)


def _build_messages(messages: List[ChatMessage], system: str = None) -> Iterable[ChatCompletionMessageParam]:
    completion_messages = []
    if system is not None:
        completion_messages.append(ChatCompletionSystemMessageParam(role="system", content=system))
    for message in messages:
        if isinstance(message.content, str):
            if message.role == 'user':
                completion_messages.append(
                    ChatCompletionUserMessageParam(role="user", content=message.content))
            else:
                completion_messages.append(
                    ChatCompletionAssistantMessageParam(role="assistant", content=message.content))
        else:
            # Currently only supporting text completion
            raise UnsupportedMultiModalMessageError()
    return completion_messages


class OpenaiChatBotClient(ChatBotClient):
    DEFAULT_SYSTEM_PROMPT = ("You are a helpful assistant. "
                             "You and the user's conversation is only one round."
                             "Answer in Chinese unless specified otherwise.")

    DEFAULT_MODEL_NAME = "gpt-3.5-turbo"

    def __init__(self,
                 api_key=None,
                 model_name: str = None,
                 enable_streaming: bool = None,
                 base_url: str = None,
                 preset_system_prompt: str = None,
                 tiktoken_encoding_tokens_model='gpt-4'):
        super().__init__(api_key, base_url, model_name, preset_system_prompt, enable_streaming, False)

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        # cl100k_base       |	gpt-4, gpt-3.5-turbo, text-embedding-ada-002
        # p50k_base	        | Codex models, text-davinci-002, text-davinci-003
        # r50k_base(or gpt2)|	GPT-3 models like davinci
        self.tiktoken_encoding = tiktoken.encoding_for_model(tiktoken_encoding_tokens_model)
        self.tiktoken_encoding_tokens_model = tiktoken_encoding_tokens_model

    @property
    def server_type(self) -> ChatBotServerType:
        return ChatBotServerType.OpenAI

    def completions(self, messages: List[ChatMessage], system: str = None):
        # messages = [
        #     {
        #         "role": "user",
        #         "content": "Hello, Claude",
        #     }
        # ]
        openai_messages = _build_messages(messages, system if system is not None else self.preset_system_prompt)
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=openai_messages,
                stream=self.enable_streaming
            )
            if not self.enable_streaming:
                return (
                    [response.choices[0].message.content],
                    TokenUsage(input_tokens=response.usage.prompt_tokens,
                               output_tokens=response.usage.completion_tokens,
                               image_tokens=0)
                )
            else:
                token_usage = TokenUsage(
                    input_tokens=self._num_tokens_from_messages(openai_messages),
                    output_tokens=0, image_tokens=0
                )
                return IterableMessageChunk(response, token_usage, self), token_usage
        except openai.BadRequestError as e:
            if e.code == 'context_length_exceeded':
                raise ContextLengthExceededException(e.args)
            else:
                raise e

    def num_tokens_from_string(self, string) -> int:
        """Return the number of tokens used by a string."""

        return len(self.tiktoken_encoding.encode(string))

    def _num_tokens_from_messages(self, messages, model=None):
        """Return the number of tokens used by a list of messages."""

        model = model if model is not None else self.tiktoken_encoding_tokens_model
        encoding = self.tiktoken_encoding

        if model in {
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-0613",
            "gpt-3.5-turbo-16k-0613",
            "gpt-4-0314",
            "gpt-4-32k-0314",
            "gpt-4-0613",
            "gpt-4-32k-0613",
            "gpt-4",
        }:
            tokens_per_message = 3
            tokens_per_name = 1
        elif model == "gpt-3.5-turbo-0301":
            tokens_per_message = 4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
            tokens_per_name = -1  # if there's a name, the role is omitted
        else:
            raise NotImplementedError(
                f"""num_tokens_from_messages() is not implemented for model {model}.
                  See https://github.com/openai/openai-python/blob/main/chatml.md for information 
                  on how messages are converted to tokens."""
            )
        num_tokens = 0
        for message in messages:
            num_tokens += tokens_per_message
            for key, value in message.items():
                num_tokens += len(encoding.encode(value))
                if key == "name":
                    num_tokens += tokens_per_name
        num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
        return num_tokens


class IterableMessageChunk:
    def __init__(self, chunks: Stream[ChatCompletionChunk], token_usage: TokenUsage,
                 chatbot_client: OpenaiChatBotClient):
        self.chunks = chunks
        self.token_usage = token_usage
        self.chatbot_client = chatbot_client

    def __iter__(self):
        return self

    def __next__(self):
        try:
            chunk = self.chunks.__next__()
            chunk_content = chunk.choices[0].delta.content
            if chunk_content is not None and len(chunk_content) > 0:
                self.token_usage.output_tokens += self.chatbot_client.num_tokens_from_string(chunk_content)
                return chunk_content
            return ""
        except StopIteration:
            raise StopIteration


if __name__ == '__main__':
    os.environ['CHATBOT_SERVER_API_KEY'] = os.environ.get('OPENAI_API_KEY')
    os.environ['CHATBOT_SERVER_BASE_URL'] = os.environ.get('OPENAI_BASE_URL')
    os.environ['CHATBOT_SERVER_STREAMING_ENABLE'] = 'false'
    client = OpenaiChatBotClient()
    msgs = [
        {"role": "user", "content": "Hello, Claude"},
    ]
    results, usage = client.completions([ChatMessage(role=msg['role'], content=msg['content']) for msg in msgs])
    for result in results:
        print(result)
    print(usage)
