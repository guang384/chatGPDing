import base64
import hashlib
import os
from urllib.parse import urlparse

import requests


def download_file(url, dir_path, file_extension=None):
    response = requests.get(url)
    if response.status_code == 200:
        file_content = response.content
        md5_hash = hashlib.md5(file_content).hexdigest()
        parsed_url = urlparse(url)
        file_name = os.path.basename(parsed_url.path)
        if file_extension is None:
            file_extension = os.path.splitext(file_name)[1]
        file_name = md5_hash[:8].upper() + file_extension
        dir_name = os.path.abspath(dir_path)
        os.makedirs(dir_name, exist_ok=True)

        file_path = os.path.join(dir_name, file_name)
        with open(file_path, 'wb') as file:
            file.write(response.content)
        print(f'File has been saved as：{file_path}')
        return file_path
    else:
        print('File download error')


def truncate_string(s):
    s = s.replace('\n', '')
    if len(s) > 100:
        s = s[:50] + ' ... ' + s[-30:]
    return s


def image_to_base64(image_path):
    with open(image_path, 'rb') as img:
        base64_data = base64.b64encode(img.read())
        return base64_data.decode('utf-8')
