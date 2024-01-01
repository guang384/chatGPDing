import base64
import hashlib
import hmac
import json
import logging
import os
import time
from http.client import HTTPException
from urllib.parse import urlunparse, urlparse

import requests

logging.basicConfig(level=logging.WARN)


class DingtalkClient:
    def __init__(
            self,
            rewrite_host=None,
            rewrite_pathname=None,
            secret_keys=None

    ):
        self.rewrite_host = rewrite_host
        self.rewrite_pathname = rewrite_pathname
        self.secret_keys = secret_keys

        if rewrite_host is None:
            self.rewrite_host = os.environ.get("REWRITE_DINGTALK_HOST")
        if rewrite_pathname is None:
            self.rewrite_pathname = os.getenv("REWRITE_DINGTALK_PATHNAME")
        if self.rewrite_host is not None:
            print("rewrite http://oapi.dingtalk.com/robot/sendBySession to http://%s/%s" % (
                self.rewrite_host, self.rewrite_pathname))

        if secret_keys is None:
            self.secret_keys = os.getenv("DINGTALK_APP_SECRET")
        if self.secret_keys is None:
            logging.error("Need to set environment variable: DINGTALK_APP_SECRET.")
            raise ValueError("You need to set a DingTalk App Secret")

    def _rewrite_session_webhook(self, session_webhook):
        if self.rewrite_host is None:
            return session_webhook
        return urlunparse(urlparse(session_webhook)._replace(netloc=self.rewrite_host, path=self.rewrite_pathname))

    def _hmac_sha256_base64_encode(self, key, msg):
        hmac_key = bytes(key, 'utf-8')
        hmac_msg = bytes(msg, 'utf-8')

        hmac_hash = hmac.new(hmac_key, hmac_msg, hashlib.sha256).digest()
        base64_encoded = base64.b64encode(hmac_hash).decode('utf-8')

        return base64_encoded

    def check_signature(self, timestamp, sign):
        for secret_key in self.secret_keys.split(','):
            contents = timestamp + "\n" + secret_key
            signed = self._hmac_sha256_base64_encode(secret_key, contents)
            if signed == sign:
                return
        print("DINGTALK_APP_SECRET not right.", secret_key)
        raise HTTPException(status_code=401, detail="DingTalk signature verification failed.")

    async def send_markdown(self, title, text, session_webhook):
        url = session_webhook
        data = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text
            }
        }
        await self._send_to_dingtalk_server(data, url)

    async def send_text(self, answer, session_webhook):
        if len(answer.strip()) > 0:
            url = session_webhook
            data = {
                "msgtype": "text",
                "text": {
                    "content": answer.strip()
                }
            }
            await self._send_to_dingtalk_server(data, url)

    async def _send_to_dingtalk_server(self, data, url):
        # https://open.dingtalk.com/document/orgapp/robot-message-types-and-data-format
        url = self._rewrite_session_webhook(url)
        url = self._rewrite_session_webhook(url)

        headers = {'Content-Type': 'application/json'}
        try:
            print("Sending messages to {} ...".format(url))

            payload = json.dumps(data)
            dingtalk_start_time = time.perf_counter()
            response = requests.post(url, data=payload, headers=headers)
            dingtalk_end_time = time.perf_counter()
            print("Request duration: dingtalk {:.3f} s.".format((dingtalk_end_time - dingtalk_start_time)))
            if response.json()['errcode'] != 0:
                raise RuntimeError("Error while call dingtalk :" + json.dumps(response.json()))
        except Exception as e:
            dingtalk_end_time = time.perf_counter()
            print("Error Request duration: dingtalk {:.3f} s.".format((dingtalk_end_time - dingtalk_start_time)))
            raise e
