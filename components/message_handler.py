import abc
import asyncio
import logging
import os
import threading
import time
from enum import Enum
from queue import Queue
from typing import Any

from pydantic import BaseModel

from components.ai_side.chatbot_client import ChatBotClient
from components.ai_side.chatbot_client_builder import ChatBotClientBuilder
from components.tools import is_true


class MessageHandlerEnv(Enum):
    WORKER_THREADS = "MESSAGE_HANDLER_WORKER_THREADS"
    ENABLE_GROUP_MESSAGES_HANDLING = "GROUP_MESSAGES_HANDLING_ENABLE"


class QueuedRequest(BaseModel):
    unique_identifier: str
    parameters: dict[str, Any]


class ConcurrentRequestException(Exception):
    pass


class MessageHandler:
    DEFAULT_WORKER_THREADS = 4

    def __init__(self,
                 chatbot_client_builder: ChatBotClientBuilder,
                 worker_threads: int = None):
        self._chatbot_client_builder = chatbot_client_builder
        self.queue = Queue()
        self.stopped = False
        self.processing: dict[str, QueuedRequest] = {}  # 'Unique identifier' map to 'request being processed'

        self.worker_threads = self.DEFAULT_WORKER_THREADS
        if os.getenv(MessageHandlerEnv.WORKER_THREADS.value) is not None:
            self.worker_threads = int(os.getenv(MessageHandlerEnv.WORKER_THREADS.value))
        if worker_threads is not None:
            self.worker_threads = worker_threads
        if self.worker_threads < 1:
            self.worker_threads = 1

        self.handlingGroupMessages = is_true(os.getenv(MessageHandlerEnv.ENABLE_GROUP_MESSAGES_HANDLING.value))
        if self.handlingGroupMessages:
            logging.info("Group message handling enabled. Server is now listening for messages from groups.")

    def get_request_being_processed(self, unique_identifier: str) -> QueuedRequest:
        return self.processing[unique_identifier] if unique_identifier in self.processing else None

    def add_new_request_to_queue(self, unique_identifier: str, request: dict[str, Any]) -> None:
        new_request = QueuedRequest(unique_identifier=unique_identifier, parameters=request)

        being_processed = self.get_request_being_processed(unique_identifier)
        if being_processed is not None:
            # Concurrency Control
            raise ConcurrentRequestException(
                "The request with the same unique_identifier is already being processed.",
                being_processed, new_request
            )

        self.queue.put(new_request)
        self.processing[unique_identifier] = new_request

    def start_workers(self):
        for i in range(self.worker_threads):
            worker = threading.Thread(target=asyncio.run,
                                      args=(self._process_request_in_queue(i, self._chatbot_client_builder),))
            worker.start()

    def stop_workers(self):
        self.stopped = True
        for i in range(self.worker_threads):
            self.queue.put({})
            time.sleep(0.001)

    async def _process_request_in_queue(self, num, chatbot_client_builder: ChatBotClientBuilder) -> None:
        chatbot_client = chatbot_client_builder.build()
        logging.info("Started Message processing Worker: #%d %s" % (num, chatbot_client))

        while not self.stopped:
            request: QueuedRequest = self.queue.get()
            if request == {}:
                self.queue.task_done()
                break
            # main logic
            await self.process_request(request, chatbot_client)

            # remove processed
            del self.processing[request.unique_identifier]

            self.queue.task_done()
        logging.info("Stopped Message processing Worker: #" + str(num))

    @abc.abstractmethod
    async def process_request(self, request: QueuedRequest, chatbot_client: ChatBotClient) -> None:
        raise NotImplementedError("process_request method not implemented")


if __name__ == '__main__':
    class MyMessageHandler(MessageHandler):
        async def process_request(self, request: QueuedRequest, chatbot_client: ChatBotClient) -> None:
            print("Received:" + str(request))


    handler = MyMessageHandler()
    handler.start_workers()
    try:
        handler.add_new_request_to_queue("111", {"a": "3"})
        print(3)
        handler.add_new_request_to_queue("222", {"a": "4"})
        print(4)
    except Exception as e:
        print(e)
        handler.stop_workers()
        exit()

    time.sleep(5)
    handler.stop_workers()
