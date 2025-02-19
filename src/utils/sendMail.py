#######################################
# 发送邮件程序，请不要在本地跑这个程序！！！
#######################################
import io
import smtplib
from os.path import basename
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from src import config
from io import BytesIO, IOBase


####################################################################
# SEND MAIL API
####################################################################

# ------------------------------------------------------
# 通过个人邮箱发送可带有附件的邮件
# ------------------------------------------------------
def sendMail(
    send_from="zhaozekun@citics.com",           # 发件人
    send_to=["zhaozekun@citics.com"],           # 收件人列表
    subject="Test Mail From 172.22.218.207",    # 邮件主题
    text="Test Mail From 172.22.218.207",       # 邮件内容
    attached_files=None,                        # 附件，默认为None不带附件，若发送请传入(文件名-k,文件路径-v)的dict
    carbon_copy_to=None                         # 抄送地址，默认为None，代表无抄送地址，如有抄送地址请传入list
):
    assert send_from in list(config.send_mail_passwords.keys()), "目前发件人只配置了amfof/amfofdata/zhaozekun的邮箱密码信息，如需新增请找赵泽坤"
    assert isinstance(send_to, list), "收件人地址需为列表形式传入"

    # 基础信息生成
    msg = MIMEMultipart()
    msg['From'] = send_from
    msg['To'] = ', '.join(send_to)
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject
    if carbon_copy_to is not None:
        assert isinstance(carbon_copy_to, list), "抄送地址需为列表形式传入，或为None"
        msg['CC'] = ', '.join(carbon_copy_to)
        send_to = send_to + carbon_copy_to
    msg.attach(MIMEText(text))

    # 附件上传
    if attached_files:
        assert isinstance(attached_files, dict), "附件路径需为字典形式传入(文件名-k,文件路径-v)"
        for file_name, file_path in attached_files.items():
            if isinstance(file_path, str):
                with open(file_path, "rb") as fil:
                    part = MIMEApplication(
                        fil.read(),
                    )
            elif isinstance(file_path, io.BytesIO):
                part = MIMEApplication(
                    file_path.getvalue(),
                )
            else:
                raise AssertionError("附件路径类型需为str或BytesIO")
            # After the file is closed
            part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", file_name))
            msg.attach(part)

    # 发送邮件
    server = "10.23.161.236"    # 原来使用newmail.citicsinfo.com,现改为邮件系统的IP,两台堡垒机均可发送邮件
    smtp = smtplib.SMTP(server)
    smtp.login(send_from, config.send_mail_passwords[send_from])
    smtp.sendmail(send_from, send_to, msg.as_string())
    smtp.close()
