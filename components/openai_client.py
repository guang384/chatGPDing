import logging
import os
from http.client import HTTPException
import tiktoken
from openai import OpenAI, Stream
from openai.types.chat import ChatCompletion, ChatCompletionChunk

logging.basicConfig(level=logging.WARN)


class OpenaiClient:
    def __init__(
            self,
            api_key=None,
            chat_model='gpt-4-1106-preview',
            tiktoken_encoding_tokens_model='gpt-4-0613',
            if_stream=False
    ):
        self.api_key = api_key
        if api_key is None:
            self.api_key = os.getenv("OPENAI_API_KEY")
        if self.api_key is None:
            logging.error("Need to set environment variable: OPENAI_API_KEY.")
            raise HTTPException(status_code=500, detail="Need to set environment variable: OPENAI_API_KEY.")

        self.openai = OpenAI(
            api_key=self.api_key
        )

        # cl100k_base       |	gpt-4, gpt-3.5-turbo, text-embedding-ada-002
        # p50k_base	        | Codex models, text-davinci-002, text-davinci-003
        # r50k_base(or gpt2)|	GPT-3 models like davinci
        self.tiktoken_encoding = tiktoken.encoding_for_model(tiktoken_encoding_tokens_model)
        self.tiktoken_encoding_tokens_model = tiktoken_encoding_tokens_model

        # gpt-4
        # gpt-4-1106-preview
        # gpt-3.5-turbo
        self.chat_model = chat_model

        # Another small drawback of streaming responses is that the response no longer includes the usage field
        # to tell you how many tokens were consumed. After receiving and combining all of the responses, you can
        # calculate this yourself using tiktoken.
        self.if_stream = if_stream

    def chat_completions(self, messages):  # -> ChatCompletion | Stream[ChatCompletionChunk]:
        return self.openai.chat.completions.create(
            model=self.chat_model,
            messages=messages,
            stream=self.if_stream
        )

    def num_tokens_from_string(self, string):
        """Return the number of tokens used by a string."""

        return len(self.tiktoken_encoding.encode(string))

    def num_tokens_from_messages(self, messages):
        """Return the number of tokens used by a list of messages."""
        model = self.tiktoken_encoding_tokens_model
        encoding = self.tiktoken_encoding

        if model in {
            "gpt-3.5-turbo-0613",
            "gpt-3.5-turbo-16k-0613",
            "gpt-4-0314",
            "gpt-4-32k-0314",
            "gpt-4-0613",
            "gpt-4-32k-0613",
        }:
            tokens_per_message = 3
            tokens_per_name = 1
        elif model == "gpt-3.5-turbo-0301":
            tokens_per_message = 4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
            tokens_per_name = -1  # if there's a name, the role is omitted
        elif "gpt-3.5-turbo" in model:
            print("Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-3.5-turbo-0613.")
            return self.num_tokens_from_messages(messages, model="gpt-3.5-turbo-0613")
        elif "gpt-4" in model:
            print("Warning: gpt-4 may update over time. Returning num tokens assuming gpt-4-0613.")
            return self.num_tokens_from_messages(messages, model="gpt-4-0613")
        else:
            raise NotImplementedError(
                f"""num_tokens_from_messages() is not implemented for model {model}. See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens."""
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
