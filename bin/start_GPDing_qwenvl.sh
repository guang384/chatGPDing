#!/bin/bash

source secure_key_setup.sh

cd /home/cui/chatGPDing

export CHATBOT_SERVER_TYPE=dashscope

export CHATBOT_SERVER_API_KEY=$DASHSCOPE_API_KEY

export CHATBOT_SERVER_CHAT_MODEL=qwen-vl-max

export CHATBOT_SERVER_STREAMING_ENABLE=false
export CHATBOT_SERVER_MULTIMODAL_ENABLE=true

export MESSAGE_HANDLER_WORKER_THREADS=2

export DINGTALK_APP_KEY=$DINGTALK_APP_KEY_QWENVL
export DINGTALK_APP_SECRET=$DINGTALK_APP_SECRET_QWENVL

export SERVER_PORT=8006

source venv/bin/activate && python main.py