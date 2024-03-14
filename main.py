import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from components.ai_side.chatbot_client import ChatBotServerType
from components.ai_side.chatbot_client_builder import ChatBotClientBuilder
from components.dingtalk_message_handler import DingtalkMessageHandler
from components.im_side.dingtalk_client import DingtalkClient

# Deciding on the type of server
if os.getenv('CHATBOT_SERVER_TYPE') is None:
    print("Please set CHATBOT_SERVER_TYPE. ", [member.value for member in ChatBotServerType])
    exit()

logging.getLogger().setLevel(logging.INFO)

chatbot_server_type = ChatBotServerType(os.getenv('CHATBOT_SERVER_TYPE').lower())
logging.info("ChatBot Server Type: " + chatbot_server_type.name)

chatbot_client_builder = ChatBotClientBuilder(chatbot_server_type)

# create dingtalk_client
dingtalk_client = DingtalkClient()

# create handler
handler = DingtalkMessageHandler(chatbot_client_builder, dingtalk_client)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The logic here is executed after startup. The logic here is executed before stopping.
    logging.info('DingtalkMessagesHandler workers Starting up.')
    handler.start_workers()

    yield

    # The logic here is executed before stopping.
    logging.info('DingtalkMessagesHandler workers Shutting down.')
    handler.stop_workers()


application = FastAPI(lifespan=lifespan)


@application.post("/")
async def root(request: Request):
    # check signature
    timestamp = request.headers.get('timestamp')
    signature = request.headers.get('sign')
    app_key = handler.check_signature(timestamp, signature)

    # receive from dingtalk
    message = await request.json()

    # handle and return
    return await handler.handle_message_from_dingtalk(app_key, message)


if __name__ == '__main__':
    import uvicorn
    import os

    port = 8000

    if os.getenv("SERVER_PORT") is not None:
        port = int(os.getenv("SERVER_PORT"))

    uvicorn.run(application, host="0.0.0.0", port=port)
