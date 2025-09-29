import json
import random
import qrcode
from qrcode.image.svg import SvgImage

import os
import requests
from datetime import datetime, timezone
import hashlib


def random_str(randomlength=8):
    """
    生成随机字符串
    :param randomlength: 字符串长度
    :return:
    """
    strs = ''
    chars = 'AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQqRrSsTtUuVvWwXxYyZz0123456789'
    length = len(chars) - 1
    import random
    for i in range(randomlength):
        strs += chars[random.randint(0, length)]
    print(strs)
    return strs


def build_order(user_id,amount):
    total_price = amount  # 订单总价
    order_name = 'TK 灵犀-API-SERVICE'   # 订单名字
    order_detail = "TK 灵犀-API-SERVICE"
    order_id = random_str(16)    # 自定义的订单号
    data_dict = wxpay(order_id, order_name, order_detail, total_price)   # 调用统一支付接口
    print(data_dict)
    # 如果请求成功
    if data_dict.get('return_code') == 'SUCCESS':
        # 业务处理
        # 二维码名字
        qrcode_name = str(order_id) + '.svg'
        # 创建SVG二维码
        img = qrcode.make(data_dict.get('code_url'), image_factory=SvgImage)
        output_path = os.path.join('static', qrcode_name)
        with open(output_path, 'wb') as f:
            img.save(f)
        output_url = (os.getenv('DOMAIN_NAME') or 'http://localhost:8000') + f'/static/{qrcode_name}'
        # img_url = os.path.join(path, qrcode_name)
        # img.save(img_url)
        s = {
            "code": 200,
            "msg": "获取成功",
            "data": output_url,
            "order_no": order_id     
        }
        s = json.dumps(s, ensure_ascii=False)
        return s
    s = {
        "code": 1001,
        "msg": "获取失败",
        "data": ""
    }
    s = json.dumps(s, ensure_ascii=False)
    return s
    
from datetime import datetime, timedelta
from wechat_pay.wepay import generate_wechatpay_v3_sign

def wxpay(order_id, order_name, order_price_detail, order_total_price):
    nonce_str = random_str(32)  # 拼接出随机的字符串即可，我这里是用  时间+随机数字+5个随机字母
    total_fee = int(float(order_total_price) * 100)    # 付款金额，单位是分，必须是整数
      
    params = {
        'appid': os.getenv('WECHAT_PAY_APP_ID'),  # APPID
        'mch_id': os.getenv('WECHAT_PAY_MCH_ID'),  # 商户号
        'nonce_str': nonce_str,  # 随机字符串
        'out_trade_no': order_id,  # 订单编号，可自定义
        'total_fee': total_fee,  # 订单总   金额
        'spbill_create_ip': os.getenv('CREATE_IP'),  # 自己服务器的IP地址
        'notify_url': os.getenv('WECHAT_PAY_NOTIFY_URL'),  # ,  # 回调地址，微信支付成功后会回调这个url，告知商户支付结果
        'body': order_name,  # 商品描述
        # 'detail': order_price_detail,  # 商品描述
        'trade_type': 'NATIVE',  # 扫码支付类型
    }
    sign = get_sign(params, os.getenv('WECHAT_PAY_API_KEY'))  # 获取签名
    params['sign'] = sign  # 添加签名到参数字典
    # params['product_id'] = '1234567890'
    xml = trans_dict_to_xml(params)  # 转换字典为XML
    print("xml",xml)
    response = requests.request('post',os.getenv('UFDODER_URL'), data=xml.encode())  # 以POST方式向微信公众平台服务器发起请求
    data_dict = trans_xml_to_dict(response.content)  # 将请求返回的数据转为字典
    print("data_dict",data_dict)
    return data_dict


def get_sign(data_dict, key):
    
    # 过滤掉 sign 字段和空值字段
    filtered_data = {k: v for k, v in data_dict.items() if k != "sign" and v not in [None, ""]}

    # 排序 + 拼接
    params_list = sorted(filtered_data.items(), key=lambda e: e[0])
    params_str = "&".join(f"{k}={v}" for k, v in params_list) + f"&key={key}"
   
    # MD5加密
    md5 = hashlib.md5()
    md5.update(params_str.encode('utf-8'))
    sign = md5.hexdigest().upper()
    print("签名前字符串:", params_str)
    print("签名结果:", sign)
    return sign


def trans_dict_to_xml(data_dict):
    """
    定义字典转XML的函数
    :param data_dict:
    :return:
    """
    data_xml = []
    for k in sorted(data_dict.keys()):  # 遍历字典排序后的key
        v = data_dict.get(k)  # 取出字典中key对应的value
        if k == 'detail' and not v.startswith('<![CDATA['):  # 添加XML标记
            v = '<![CDATA[{}]]>'.format(v)
        data_xml.append('<{key}>{value}</{key}>'.format(key=k, value=v))
    return '<xml>{}</xml>'.format(''.join(data_xml))  # 返回XML


def trans_xml_to_dict(data_xml):
    """
    定义XML转字典的函数
    :param data_xml:
    :return:
    """
    data_dict = {}
    try:
        import xml.etree.cElementTree as ET
    except ImportError:
        import xml.etree.ElementTree as ET
    root = ET.fromstring(data_xml)
    for child in root:
        data_dict[child.tag] = child.text
    return data_dict