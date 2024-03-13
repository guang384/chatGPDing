import base64
import hashlib
import hmac
import json
import logging
import os
import time
from http.client import HTTPException
from urllib.parse import urlunparse, urlparse

import aiohttp

logging.basicConfig(level=logging.WARN)


def _hmac_sha256_base64_encode(key, msg):
    hmac_key = bytes(key, 'utf-8')
    hmac_msg = bytes(msg, 'utf-8')

    hmac_hash = hmac.new(hmac_key, hmac_msg, hashlib.sha256).digest()
    base64_encoded = base64.b64encode(hmac_hash).decode('utf-8')

    return base64_encoded


class DingtalkClient:
    def __init__(
            self,
            rewrite_host=None,
            rewrite_pathname=None,
            app_keys=None,
            secret_keys=None

    ):
        self.rewrite_host = rewrite_host
        self.rewrite_pathname = rewrite_pathname
        self.app_keys = app_keys
        self.secret_keys = secret_keys

        self.access_token = {}
        self.access_token_expires = {}

        if rewrite_host is None:
            self.rewrite_host = os.environ.get("REWRITE_DINGTALK_HOST")
        if rewrite_pathname is None:
            self.rewrite_pathname = os.getenv("REWRITE_DINGTALK_PATHNAME")
        if self.rewrite_host is not None:
            print("Rewrite the base URL of Dingtalk Server from %s to %s."
                  % ("https://oapi.dingtalk.com/robot/sendBySession",
                     self._rewrite_server_url("https://oapi.dingtalk.com/robot/sendBySession")))

        if app_keys is None:
            self.app_keys = os.getenv("DINGTALK_APP_KEY")
        if self.app_keys is None:
            logging.error("Need to set environment variable: DINGTALK_APP_KEY.")
            raise ValueError("You need to set a DingTalk App Key")

        if secret_keys is None:
            self.secret_keys = os.getenv("DINGTALK_APP_SECRET")
        if self.secret_keys is None:
            logging.error("Need to set environment variable: DINGTALK_APP_SECRET.")
            raise ValueError("You need to set a DingTalk App Secret")

    def _rewrite_server_url(self, url):
        if self.rewrite_host is None or '/v1.0/' in url:  # the `V1` interface will require whitelist verification!
            return url
        parsed_url = urlparse(url)
        return urlunparse(parsed_url._replace(netloc=self.rewrite_host, path=self.rewrite_pathname + parsed_url.path))

    def check_signature(self, timestamp, signature) -> str:
        """
        check_signature
        :param timestamp:
        :param signature:
        :return: app_key
        """
        for index, secret_key in enumerate(self.secret_keys.split(',')):
            contents = timestamp + "\n" + secret_key
            signed = _hmac_sha256_base64_encode(secret_key, contents)
            if signed == signature:
                return self.app_keys.split(',')[index]
        print("DINGTALK_APP_SECRET not right.", self.secret_keys)
        raise SystemError("DingTalk signature verification failed.")

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

    async def send_text(self, text, session_webhook):
        if len(text.strip()) > 0:
            url = session_webhook
            data = {
                "msgtype": "text",
                "text": {
                    "content": text.strip()
                }
            }
            await self._send_to_dingtalk_server(data, url)

    async def one_to_one_text(self, text, robotCode, userId, app_key):
        if len(text.strip()) > 0:
            url = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
            data = {
                "robotCode": robotCode,
                "userIds": [userId],
                "msgKey": "sampleText",
                "msgParam": json.dumps({
                    "content": text.strip()
                })
            }
            await self._send_to_dingtalk_server(data, url, app_key)

    async def _send_to_dingtalk_server(self, data, url, app_key=None):

        # By using this API to send messages proactively, you can obtain a message ID,
        # which helps to identify the message when being referenced.
        # This interface can be used to actively initiate a one-on-one chat conversation with the user.
        # https://open.dingtalk.com/document/orgapp/chatbots-send-one-on-one-chat-messages-in-batches

        # Sending messages through a webhook is the most convenient method, but it does not provide the message ID.
        # Through the webhook interface, it does not require whitelist verification,
        # but if the `V1` interface is used, it will strictly require whitelist verification!

        url = self._rewrite_server_url(url)

        headers = {'Content-Type': 'application/json'}

        if app_key is not None:
            headers['x-acs-dingtalk-access-token'] = await self._refresh_access_token(app_key)

        dingtalk_start_time = time.perf_counter()
        try:
            print("Sending messages to {} ...".format(url))

            payload = json.dumps(data)
            # https://open.dingtalk.com/document/orgapp/robot-message-types-and-data-format

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=payload, headers=headers) as response:
                    dingtalk_end_time = time.perf_counter()
                    print("Request duration: dingtalk {:.3f} s.".format((dingtalk_end_time - dingtalk_start_time)))
                    response_json = await response.json()
                    if 'errcode' in response_json and response_json['errcode'] != 0:  # old API response 'errcode'
                        raise RuntimeError(
                            "Error while call dingtalk :" + json.dumps(response_json, ensure_ascii=False))
                    elif 'code' in response_json:  # new api (v1.0) has 'code' when error
                        raise RuntimeError(
                            "Error while call dingtalk :" + json.dumps(response_json, ensure_ascii=False))
                    elif 'processQueryKey' in response_json:  # new api (v1.0) has 'processQueryKey' when sent
                        print('Message sent successfully - ', response_json['processQueryKey'])
        except Exception as e:
            dingtalk_end_time = time.perf_counter()
            print("Error Request duration: dingtalk {:.3f} s.".format((dingtalk_end_time - dingtalk_start_time)))
            raise e

    async def _refresh_access_token(self, app_key) -> str:
        if app_key not in self.access_token_expires or time.perf_counter() > self.access_token_expires[app_key]:
            api_url = self._rewrite_server_url("https://oapi.dingtalk.com/gettoken")

            print("Refresh access_token {} ...".format(app_key))
            params = {
                'appkey': app_key
            }
            for index, curr_app_key in enumerate(self.app_keys.split(',')):
                if curr_app_key == app_key:
                    params['appsecret'] = self.secret_keys.split(',')[index]
                    break
            dingtalk_access_token_start_time = time.perf_counter()

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url, params=params) as response:
                        dingtalk_access_token_end_time = time.perf_counter()
                        print("Request duration: refresh access_token {:.3f} s.".format(
                            (dingtalk_access_token_end_time - dingtalk_access_token_start_time)))
                        response_json = await response.json()
                        if response_json['errcode'] != 0:
                            raise RuntimeError("Error while refresh access_token :" + json.dumps(response_json,
                                                                                                 ensure_ascii=False))
                        self.access_token_expires[app_key] = time.perf_counter() + response_json['expires_in'] * 0.8
                        self.access_token[app_key] = response_json['access_token']
            except Exception as e:
                dingtalk_access_token_end_time = time.perf_counter()
                print("Error Request duration:  refresh access_token {:.3f} s.".format(
                    (dingtalk_access_token_end_time - dingtalk_access_token_start_time)))
                raise e
        return self.access_token[app_key]

    async def get_file_download_url(self, app_key, download_code):
        access_token = await self._refresh_access_token(app_key)
        api_url = self._rewrite_server_url("https://api.dingtalk.com/v1.0/robot/messageFiles/download")
        payload = json.dumps({
            "downloadCode": download_code,
            "robotCode": app_key
        })
        headers = {
            'x-acs-dingtalk-access-token': access_token,
            'Content-Type': 'application/json'
        }
        dingtalk_api_start_time = time.perf_counter()
        try:
            print("Require  download url of [{}]{} ...".format(app_key, download_code))
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, data=payload, headers=headers) as response:
                    dingtalk_api_end_time = time.perf_counter()
                    print("Request duration: require download url {:.3f} s.".format(
                        (dingtalk_api_end_time - dingtalk_api_start_time)))
                    response_json = await response.json()
                    if 'downloadUrl' not in response_json:
                        raise RuntimeError("Error while require download url :" + json.dumps(response_json,
                                                                                             ensure_ascii=False))
                    print("Required download url is [{}]{}".format(app_key, response_json['downloadUrl']))
                    return response_json['downloadUrl']
        except Exception as e:
            dingtalk_api_end_time = time.perf_counter()
            print("Error Request duration: require download url {:.3f} s.".format(
                (dingtalk_api_end_time - dingtalk_api_start_time)))
            raise e
