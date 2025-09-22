import json
import hashlib
import hmac
import base64
import random
import string
from datetime import datetime, timezone
from django.http import JsonResponse
from django.conf import settings
 
def generate_wechatpay_v3_sign(request_method, request_url, request_body, merchant_id, merchant_serial_number, private_key):
    """
    生成微信支付V3版本的签名
    
    参数:
        request_method: HTTP请求方法 (GET/POST/PUT等)
        request_url: 完整的请求URL (如 "/v3/pay/transactions/native")
        request_body: 请求体JSON字符串
        merchant_id: 商户号
        merchant_serial_number: 商户API证书序列号
        private_key: 商户私钥内容(字符串)
    
    返回:
        Authorization头字符串和签名所需的时间戳、随机字符串
    """
    # 生成时间戳 (UTC时间)
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    
    # 生成随机字符串
    nonce_str = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32))
    
    # 构造签名字符串
    # 格式: {method}\n{url}\n{timestamp}\n{nonce}\n{body}\n
    message = f"{request_method}\n{request_url}\n{timestamp}\n{nonce_str}\n{request_body}\n"
    
    # 使用HMAC-SHA256进行签名
    # 注意: 这里简化处理，实际应从私钥文件中加载私钥
    hmac_code = hmac.new(
        private_key.encode('utf-8'),  # 实际项目中应从文件读取私钥内容
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    # Base64编码签名结果
    signature = base64.b64encode(hmac_code).decode('utf-8')
    
    # 构造Authorization头
    authorization = (
        f'WECHATPAY2-SHA256-RSA2048 '
        f'mchid="{merchant_id}",'
        f'nonce_str="{nonce_str}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{merchant_serial_number}",'
        f'signature="{signature}"'
    )
    
    return authorization, timestamp, nonce_str
 
