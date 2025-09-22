# -*- coding: utf-8 -*-
# This file is auto-generated, don't edit it. Thanks.
import os
import sys

from typing import List

from alibabacloud_dysmsapi20170525.client import Client as Dysmsapi20170525Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_dysmsapi20170525 import models as dysmsapi_20170525_models
from alibabacloud_tea_util import models as util_models
from alibabacloud_tea_util.client import Client as UtilClient
# 从环境变量读取短信AK/SK，避免将密钥硬编码到仓库
SMS_ACCESS_ID = os.getenv('ALIYUN_SMS_ACCESS_ID', '')
SMS_ACCESS_SECRET = os.getenv('ALIYUN_SMS_ACCESS_SECRET', '')
# 从环境变量读取短信签名和模板
SMS_SIGN_NAME = os.getenv('ALIYUN_SMS_SIGN_NAME', 'Vectorizer')
SMS_TEMPLATE_CODE = os.getenv('ALIYUN_SMS_TEMPLATE_CODE', 'SMS_307081209')

class SMS:
    def __init__(self):
        pass

    @staticmethod
    def create_client() -> Dysmsapi20170525Client:
        """
        使用AK&SK初始化账号Client
        @return: Client
        @throws Exception
        """
        # 工程代码泄露可能会导致 AccessKey 泄露，并威胁账号下所有资源的安全性。以下代码示例仅供参考。
        # 建议使用更安全的 STS 方式，更多鉴权访问方式请参见：https://help.aliyun.com/document_detail/378659.html。
        config = open_api_models.Config(
            # 必填，请确保代码运行环境设置了环境变量 ALIBABA_CLOUD_ACCESS_KEY_ID。, 
            access_key_id=SMS_ACCESS_ID,
            # 必填，请确保代码运行环境设置了环境变量 ALIBABA_CLOUD_ACCESS_KEY_SECRET。, 
            access_key_secret=SMS_ACCESS_SECRET
        )
        # Endpoint 请参考 https://api.aliyun.com/product/Dysmsapi
        config.endpoint = f'dysmsapi.aliyuncs.com'
        return Dysmsapi20170525Client(config)

    @staticmethod
    def main(phone_number, code2):
        """发送短信验证码；若未配置AK/SK则在开发环境打印验证码并直接返回。"""
        # 开发环境未配置短信AK/SK，模拟发送以便本地调试
        if not SMS_ACCESS_ID or not SMS_ACCESS_SECRET:
            print(f"[DEV] 未配置阿里云短信AK/SK，模拟发送验证码到 {phone_number}，验证码：{code2}")
            return

        client = SMS.create_client()
        send_sms_request = dysmsapi_20170525_models.SendSmsRequest(
            sign_name=SMS_SIGN_NAME,
            template_code=SMS_TEMPLATE_CODE,  # 例如 SMS_307081209
            phone_numbers='{}'.format(phone_number),
            template_param='{"code":"'+str(code2)+'"}',
        )
        runtime = util_models.RuntimeOptions()
        try:
            # 复制代码运行请自行打印 API 的返回值
            client.send_sms_with_options(send_sms_request, runtime)
        except Exception as error:
            # 此处仅做打印展示，请谨慎对待异常处理，在工程项目中切勿直接忽略异常。
            # 错误 message
            try:
                print(str(error))
            except Exception:
                pass
            # 诊断地址
            try:
                print(getattr(error, 'data', {}).get("Recommend"))
            except Exception:
                pass
            UtilClient.assert_as_string(str(error))
    
    @staticmethod
    async def main_async(
        phone_number, code2
    ) -> None:
        # 开发环境未配置短信AK/SK，模拟发送以便本地调试
        if not SMS_ACCESS_ID or not SMS_ACCESS_SECRET:
            print(f"[DEV] 未配置阿里云短信AK/SK，模拟(异步)发送验证码到 {phone_number}，验证码：{code2}")
            return
        client = SMS.create_client()
        send_sms_request = dysmsapi_20170525_models.SendSmsRequest(
            sign_name=SMS_SIGN_NAME,
            template_code=SMS_TEMPLATE_CODE,
            phone_numbers='{}'.format(phone_number),
            template_param='{"code":"'+str(code2)+'"}',
        )
        runtime = util_models.RuntimeOptions()
        try:
            # 复制代码运行请自行打印 API 的返回值
            await client.send_sms_with_options_async(send_sms_request, runtime)
        except Exception as error:
            # 此处仅做打印展示，请谨慎对待异常处理，在工程项目中切勿直接忽略异常。
            # 错误 message
            try:
                print(str(error))
            except Exception:
                pass
            # 诊断地址
            try:
                print(getattr(error, 'data', {}).get("Recommend"))
            except Exception:
                pass
            UtilClient.assert_as_string(str(error))


if __name__ == '__main__':
    SMS.main(sys.argv[1:])
