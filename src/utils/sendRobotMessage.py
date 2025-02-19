########################################################
# 发送企业微信机器人消息的基础程序，请不要在本地跑这个程序！！！
########################################################
import pandas as pd
from src import config
from src import robot_message_config
import base64, hashlib
import requests
import os


####################################################################
# SEND ROBOT MESSAGE API
####################################################################
# ------------------------------------------------------
# 通过企业微信群机器人发送消息，目前支持文字、图片、文件三种消息类型
# ------------------------------------------------------
def sendRobotMessage(
    send_to,                # 决定由哪个机器人发送，后台会根据群聊调用对应的机器人API
    content_type,           # 发送消息内容类型，目前支持简单文字、图片和文件
    text_content=None,      # 文字消息内容
    image_content=None,     # 图片消息内容(文件地址)
    file_content=None       # 文件地址
):
    assert content_type in ['TEXT', 'IMAGE', 'FILE'], "目前企业微信群机器人仅支持发送文字、图片两种消息类型，content_type对应设置为TEXT,IMAGE"
    assert send_to in ['FOF数据监控', 'FOF测试机器人', 'FOF数据监控助手', '私享服务支持', 'FOF私享服务(浙分)', 'FOF私募服务'], \
        "目前仅支持由 FOF数据监控 FOF测试 FOF数据监控助手 FOF私享服务(浙分) FOF私募服务 机器人发送消息"
    if content_type == 'TEXT':
        assert (text_content is not None) and (image_content is None) and (file_content is None), "发送某类型文件时请只输入对应的xxx_content参数"
        data = {
            "msgtype": "text",
            "text": {
                "content": text_content,
            }
        }
    if content_type == 'IMAGE':
        assert (text_content is None) and (image_content is not None) and (file_content is None), "发送IMAGE时请只输入image_content"
        with open(image_content, 'rb') as file:  # 转换图片成base64格式
            data = file.read()
            encodestr = base64.b64encode(data)
            image_data = str(encodestr, 'utf-8')
        with open(image_content, 'rb') as file:  # 图片的MD5值
            md = hashlib.md5()
            md.update(file.read())
            image_md5 = md.hexdigest()
            data = {
                "msgtype": "image",
                "image": {
                    "base64": image_data,
                    "md5": image_md5
                }
            }
    if content_type == 'FILE':
        assert (text_content is None) and (image_content is None) and (file_content is not None), "发送FILE时请只输入file_content"
        # 发送类型为FILE时，需先上传素材获取media_id，再使用media_id进行发送
        media_url = robot_message_config.robot_message_upload_media_destination_map[send_to]['url']  # upload_media url
        # request包会自动填写Content-Type为'multipart/form-data' 无须手动定义
        files = {'file': open(file_content, 'rb')}
        media_response = requests.post(media_url, files=files)
        file_media_id = media_response.json()['media_id']
        data = {
            "msgtype": "file",
            "file": {
                "media_id": file_media_id
            }
        }

    # 发送部分
    url = robot_message_config.robot_message_send_destination_map[send_to]['url']
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.post(url, headers=headers, json=data)

    return response
