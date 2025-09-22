import hashlib
import time
import uuid
import xml.etree.ElementTree as ET
import requests
import os

class WechatPayAPI:
    def __init__(self):
        self.app_id = os.getenv('WECHAT_PAY_APP_ID')
        self.mch_id = os.getenv('WECHAT_PAY_MCH_ID')
        self.api_key = os.getenv('WECHAT_PAY_API_KEY')
        self.notify_url = os.getenv('WECHAT_PAY_NOTIFY_URL')

    def create_order(self, order_no, amount, description):
        """创建微信支付订单"""
        # 生成随机字符串
        nonce_str = str(uuid.uuid4()).replace('-', '')
        
        # 生成时间戳
        timestamp = str(int(time.time()))
        
        # 构建请求参数
        params = {
            'appid': self.app_id,
            'mch_id': self.mch_id,
            'nonce_str': nonce_str,
            'body': description,
            'out_trade_no': order_no,
            'total_fee': int(amount * 100),  # 转换为分
            'spbill_create_ip': '127.0.0.1',
            'notify_url': self.notify_url,
            'trade_type': 'NATIVE'  # 生成二维码支付链接
        }
        
        # 生成签名
        params['sign'] = self._generate_sign(params)
        
        # 构建XML数据
        xml_data = self._dict_to_xml(params)
        
        # 发送请求到微信支付接口
        response = requests.post(
            'https://api.mch.weixin.qq.com/pay/unifiedorder',
            data=xml_data.encode('utf-8'),
            headers={'Content-Type': 'application/xml'}
        )
        
        # 解析响应
        result = self._parse_xml(response.content)
        
        if result.get('return_code') == 'SUCCESS' and result.get('result_code') == 'SUCCESS':
            return {
                'code_url': result.get('code_url'),
                'order_no': order_no,
                'timestamp': timestamp,
                'nonce_str': nonce_str
            }
        else:
            raise Exception(f"创建微信支付订单失败: {result.get('return_msg')}")

    def verify_payment(self, xml_data):
        """验证支付回调签名"""
        def trans_xml_to_dict(xml_data):
            root = ET.fromstring(xml_data)
            return {child.tag: child.text for child in root}
        data = trans_xml_to_dict(xml_data)
        if not data:
            return False
            
        # 获取签名
        sign = data.pop('sign', None)
        if not sign:
            return False
            
        # 重新生成签名
        new_sign = self._generate_sign(data)
        
        return sign == new_sign

    def _generate_sign(self, params):
        """生成签名"""
        # 按键排序
        sorted_params = sorted(params.items(), key=lambda x: x[0])
        
        # 构建签名字符串
        sign_str = '&'.join([f"{k}={v}" for k, v in sorted_params if v])
        sign_str += f"&key={self.api_key}"
        
        # MD5加密
        return hashlib.md5(sign_str.encode('utf-8')).hexdigest().upper()

    def _dict_to_xml(self, data):
        """字典转XML"""
        xml_elements = ['<xml>']
        for k, v in data.items():
            xml_elements.append(f'<{k}><![CDATA[{v}]]></{k}>')
        xml_elements.append('</xml>')
        return ''.join(xml_elements)

    def _parse_xml(self, xml_data):
        """解析XML数据"""
        try:
            root = ET.fromstring(xml_data)
            return {child.tag: child.text for child in root}
        except Exception:
            return None 
    
    def parse_xml(self, xml_data):
        """解析XML数据"""
        try:
            root = ET.fromstring(xml_data)
            return {child.tag: child.text for child in root}
        except Exception:
            return None 