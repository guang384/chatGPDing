import json
import logging
import time
from http import HTTPStatus
import dashscope
logging.basicConfig(level=logging.WARN)


class DashscopeClient:
    def __init__(
            self,
            model='qwen-vl-max'
    ):
        self.model = model

    async def multimodal_conversation(self, contents):
        """
        Single round multimodal conversation call.

        message example:
        [
            {
                "role": "user",
                "content": [
                    {"image": "file://" + os.path.abspath(
                        './downloads/iwEeAqNwbmcDAQTRAN4F0QCJBrAIQueS5J8XwwWjHQtVPvUAB9IoF1_BCAAJomltCgAL0QmP.png')},
                    {"text": "这是什么?"}
                ]
            }
        ]

        :param contents:
        :return: (content, usage)
        """
        messages = [
            {
                "role": "user",
                "content": contents
            }
        ]
        start_time = time.perf_counter()
        response = dashscope.MultiModalConversation.call(model=self.model,
                                                         messages=messages)
        end_time = time.perf_counter()
        print("Request duration: dashscope {:.3f} s. Token usage: {}.".format(
            (end_time - start_time), str(response['usage'])))

        # The response status_code is HTTPStatus.OK indicate success,
        # otherwise indicate request is failed, you can get error code
        # and message from code and message.
        if response.status_code == HTTPStatus.OK:
            return response['output']['choices'][0]['message']['content'][0]['text'], response['usage']
        else:
            raise RuntimeError("Error while call dashscope :" + json.dumps(response,ensure_ascii=False))
