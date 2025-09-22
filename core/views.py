from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from .models import Profile, Product, Order, SensitiveWord, BrandWord, ForbiddenWord, KeywordEntry, UserInfo, Category, Word, WordAlias, WordLog
import random
import string
import json
import os
from wechat_pay.pay import build_order
from aliyun_sms import SMS

# 简单的内存存储验证码，生产使用请改为缓存/Redis
SMS_CODE_STORE = {}


def home(request):
    products = Product.objects.all()
    return render(request, 'home.html', {'products': products})


def login_view(request):
    if request.method == 'POST':
        phone = request.POST.get('phone')
        code = request.POST.get('code')
        if not phone or not code:
            return render(request, 'login.html', {'error': '请输入手机号和验证码'})
        if SMS_CODE_STORE.get(phone) != code:
            return render(request, 'login.html', {'error': '验证码错误或已过期'})
        user, created = User.objects.get_or_create(username=phone)
        if created:
            Profile.objects.create(user=user, phone=phone)
        login(request, user)
        return redirect('dashboard')
    return render(request, 'login.html')


def send_code(request):
    phone = request.GET.get('phone')
    if not phone:
        return JsonResponse({'ok': False, 'msg': '手机号必填'})
    code = ''.join(random.choices(string.digits, k=6))
    SMS_CODE_STORE[phone] = code
    try:
        SMS.main(phone, code)
        ok = True
        msg = '验证码已发送'
    except Exception as e:
        ok = False
        msg = f'发送失败: {e}'
    return JsonResponse({'ok': ok, 'msg': msg})


# 暂时放行：未登录访问 /dashboard/ 时，自动以 chengong 登录
# 注意：仅用于演示，生产环境务必移除或加开关
def _ensure_default_login(request):
    if request.user.is_authenticated:
        return
    try:
        user = User.objects.filter(username='chengong').first()
        if not user:
            user = User.objects.create_superuser('chengong', email='', password='chengong123')
        if not Profile.objects.filter(user=user).exists():
            Profile.objects.create(user=user, phone='13800000000')
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    except Exception:
        pass


# 移除@login_required，确保自动登录逻辑先执行
def dashboard(request):
    _ensure_default_login(request)
    profile = Profile.objects.get(user=request.user)
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    products = Product.objects.all()
    return render(request, 'dashboard.html', {
        'profile': profile,
        'orders': orders,
        'products': products,
    })


@csrf_exempt
@login_required
def recharge(request):
    amount = float(request.POST.get('amount', '19.90'))
    resp = build_order(request.user.id, amount)
    try:
        data = json.loads(resp)
        if data.get('code') == 200:
            order_no = data.get('order_no')
            Order.objects.get_or_create(
                order_no=order_no,
                defaults={
                    'user': request.user,
                    'product': None,
                    'amount': amount,
                    'status': 'pending',
                }
            )
        return HttpResponse(resp, content_type='application/json')
    except Exception:
        return JsonResponse({'code': 1002, 'msg': '下单异常', 'data': ''})


@csrf_exempt
def wechat_notify(request):
    from wechat_pay.wechat_pay import WechatPayAPI
    api = WechatPayAPI()
    xml_data = request.body
    if not api.verify_payment(xml_data):
        return HttpResponse("<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA[SIGN ERROR]]></return_msg></xml>")
    data = api.parse_xml(xml_data)
    order_no = data.get('out_trade_no')
    total_fee = int(data.get('total_fee', '0')) / 100.0
    try:
        order = Order.objects.get(order_no=order_no, amount=total_fee)
        order.status = 'paid'
        order.save()
        profile = Profile.objects.get(user=order.user)
        profile.monthly_quota += 300
        profile.save()
    except Order.DoesNotExist:
        pass
    return HttpResponse("<xml><return_code><![CDATA[SUCCESS]]></return_code><return_msg><![CDATA[OK]]></return_msg></xml>")


def logout_view(request):
    logout(request)
    return redirect('home')


# -------- 统一的简单增改查API（不做删除） --------

def parse_json(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return {}


def build_pagination(qs, request):
    page = int(request.GET.get('page', '1'))
    size = int(request.GET.get('size', '20'))
    start = (page - 1) * size
    end = start + size
    total = qs.count()
    return qs[start:end], total, page, size


def list_response(qs, request, mapper):
    paged, total, page, size = build_pagination(qs, request)
    return JsonResponse({
        'code': 0,
        'msg': 'ok',
        'data': [mapper(o) for o in paged],
        'total': total,
        'page': page,
        'size': size,
    })


# 映射函数
word_mapper = lambda o: {
    'id': o.id,
    'level1': getattr(o, 'level1', ''),
    'level2': getattr(o, 'level2', ''),
    'level3': getattr(o, 'level3', ''),
    'category': getattr(o, 'category', ''),
    'word': o.word,
    'remark': o.remark,
    'created_at': o.created_at.strftime('%Y-%m-%d %H:%M:%S'),
}

user_info_mapper = lambda o: {
    'id': o.id,
    'user': o.user_id,
    'phone': o.phone,
    'permission': o.permission,
    'expire_at': o.expire_at.strftime('%Y-%m-%d %H:%M:%S') if o.expire_at else None,
    'store_count': o.store_count,
    'notes': o.notes,
    'created_at': o.created_at.strftime('%Y-%m-%d %H:%M:%S'),
}


# 敏感词库
@csrf_exempt
def sensitive_words(request):
    if request.method == 'GET':
        kw = request.GET.get('q', '').strip()
        qs = SensitiveWord.objects.all()
        if kw:
            qs = qs.filter(word__icontains=kw)
        return list_response(qs.order_by('-id'), request, word_mapper)
    elif request.method in ['POST', 'PUT', 'PATCH']:
        if not request.user.is_authenticated:
            return JsonResponse({'code': 401, 'msg': '未登录'})
        data = parse_json(request)
        obj_id = data.get('id')
        fields = {k: data.get(k, '') for k in ['level1','level2','level3','word','remark']}
        if obj_id:
            SensitiveWord.objects.filter(id=obj_id).update(**fields)
            obj = SensitiveWord.objects.get(id=obj_id)
        else:
            obj = SensitiveWord.objects.create(**fields)
        return JsonResponse({'code': 0, 'msg': 'ok', 'data': word_mapper(obj)})
    return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})


# 品牌词库（一级分类）
@csrf_exempt
def brand_words(request):
    if request.method == 'GET':
        kw = request.GET.get('q', '').strip()
        qs = BrandWord.objects.all()
        if kw:
            qs = qs.filter(word__icontains=kw)
        return list_response(qs.order_by('-id'), request, word_mapper)
    elif request.method in ['POST', 'PUT', 'PATCH']:
        if not request.user.is_authenticated:
            return JsonResponse({'code': 401, 'msg': '未登录'})
        data = parse_json(request)
        obj_id = data.get('id')
        fields = {k: data.get(k, '') for k in ['category','word','remark']}
        if obj_id:
            BrandWord.objects.filter(id=obj_id).update(**fields)
            obj = BrandWord.objects.get(id=obj_id)
        else:
            obj = BrandWord.objects.create(**fields)
        return JsonResponse({'code': 0, 'msg': 'ok', 'data': word_mapper(obj)})
    return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})


# 违禁词库（三级分类）
@csrf_exempt
def forbidden_words(request):
    if request.method == 'GET':
        kw = request.GET.get('q', '').strip()
        qs = ForbiddenWord.objects.all()
        if kw:
            qs = qs.filter(word__icontains=kw)
        return list_response(qs.order_by('-id'), request, word_mapper)
    elif request.method in ['POST', 'PUT', 'PATCH']:
        if not request.user.is_authenticated:
            return JsonResponse({'code': 401, 'msg': '未登录'})
        data = parse_json(request)
        obj_id = data.get('id')
        fields = {k: data.get(k, '') for k in ['level1','level2','level3','word','remark']}
        if obj_id:
            ForbiddenWord.objects.filter(id=obj_id).update(**fields)
            obj = ForbiddenWord.objects.get(id=obj_id)
        else:
            obj = ForbiddenWord.objects.create(**fields)
        return JsonResponse({'code': 0, 'msg': 'ok', 'data': word_mapper(obj)})
    return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})


# 关键词库（三级分类）
@csrf_exempt
def keywords(request):
    if request.method == 'GET':
        kw = request.GET.get('q', '').strip()
        qs = KeywordEntry.objects.all()
        if kw:
            qs = qs.filter(word__icontains=kw)
        return list_response(qs.order_by('-id'), request, word_mapper)
    elif request.method in ['POST', 'PUT', 'PATCH']:
        if not request.user.is_authenticated:
            return JsonResponse({'code': 401, 'msg': '未登录'})
        data = parse_json(request)
        obj_id = data.get('id')
        fields = {k: data.get(k, '') for k in ['level1','level2','level3','word','remark']}
        if obj_id:
            KeywordEntry.objects.filter(id=obj_id).update(**fields)
            obj = KeywordEntry.objects.get(id=obj_id)
        else:
            obj = KeywordEntry.objects.create(**fields)
        return JsonResponse({'code': 0, 'msg': 'ok', 'data': word_mapper(obj)})
    return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})


# 用户信息库
@csrf_exempt
def user_infos(request):
    if request.method == 'GET':
        kw = request.GET.get('q', '').strip()
        qs = UserInfo.objects.all()
        if kw:
            qs = qs.filter(phone__icontains=kw)
        return list_response(qs.order_by('-id'), request, user_info_mapper)
    elif request.method in ['POST', 'PUT', 'PATCH']:
        if not request.user.is_authenticated:
            return JsonResponse({'code': 401, 'msg': '未登录'})
        data = parse_json(request)
        obj_id = data.get('id')
        fields = {
            'user_id': data.get('user'),
            'phone': data.get('phone', ''),
            'permission': data.get('permission', ''),
            'store_count': int(data.get('store_count', 0) or 0),
            'notes': data.get('notes', ''),
        }
        # expire_at 可选
        expire_at = data.get('expire_at')
        if expire_at:
            try:
                from datetime import datetime
                fields['expire_at'] = datetime.fromisoformat(expire_at)
            except Exception:
                pass
        if obj_id:
            UserInfo.objects.filter(id=obj_id).update(**fields)
            obj = UserInfo.objects.get(id=obj_id)
        else:
            obj = UserInfo.objects.create(**fields)
        return JsonResponse({'code': 0, 'msg': 'ok', 'data': user_info_mapper(obj)})
    return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})


# 新增：标准化词库映射函数
category_mapper = lambda o: {
    'id': o.id,
    'name': o.name,
    'description': o.description,
    'created_at': o.created_at.strftime('%Y-%m-%d %H:%M:%S'),
    'updated_at': o.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
}

word_std_mapper = lambda o: {
    'id': o.id,
    'word': o.word,
    'severity': o.severity,
    'is_active': o.is_active,
    'category_id': o.category_id,
    'category_name': o.category.name if getattr(o, 'category', None) else None,
    'created_at': o.created_at.strftime('%Y-%m-%d %H:%M:%S'),
    'updated_at': o.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
}

word_alias_mapper = lambda o: {
    'id': o.id,
    'word_id': o.word_id,
    'alias': o.alias,
}

word_log_mapper = lambda o: {
    'id': o.id,
    'word_id': o.word_id,
    'context': o.context,
    'matched_at': o.matched_at.strftime('%Y-%m-%d %H:%M:%S'),
}

# 分类 API
@csrf_exempt
def categories(request):
    if request.method == 'GET':
        kw = request.GET.get('q', '').strip()
        qs = Category.objects.all()
        if kw:
            qs = qs.filter(name__icontains=kw)
        return list_response(qs.order_by('name'), request, category_mapper)
    elif request.method in ['POST', 'PUT', 'PATCH']:
        if not request.user.is_authenticated:
            return JsonResponse({'code': 401, 'msg': '未登录'})
        data = parse_json(request)
        obj_id = data.get('id')
        fields = {k: data.get(k, '') for k in ['name','description']}
        if obj_id:
            Category.objects.filter(id=obj_id).update(**fields)
            obj = Category.objects.get(id=obj_id)
        else:
            obj = Category.objects.create(**fields)
        return JsonResponse({'code': 0, 'msg': 'ok', 'data': category_mapper(obj)})
    return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})

# 词条 API
@csrf_exempt
def words(request):
    if request.method == 'GET':
        kw = request.GET.get('q', '').strip()
        cat = request.GET.get('category_id')
        qs = Word.objects.select_related('category').all()
        if kw:
            qs = qs.filter(word__icontains=kw)
        if cat:
            qs = qs.filter(category_id=cat)
        return list_response(qs.order_by('-id'), request, word_std_mapper)
    elif request.method in ['POST', 'PUT', 'PATCH']:
        if not request.user.is_authenticated:
            return JsonResponse({'code': 401, 'msg': '未登录'})
        data = parse_json(request)
        obj_id = data.get('id')
        fields = {
            'word': data.get('word', ''),
            'category_id': data.get('category_id'),
            'severity': int(data.get('severity', 1) or 1),
            'is_active': bool(data.get('is_active', True)),
        }
        if obj_id:
            Word.objects.filter(id=obj_id).update(**fields)
            obj = Word.objects.select_related('category').get(id=obj_id)
        else:
            obj = Word.objects.create(**fields)
        return JsonResponse({'code': 0, 'msg': 'ok', 'data': word_std_mapper(obj)})
    return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})

# 别名 API
@csrf_exempt
def word_aliases(request):
    if request.method == 'GET':
        kw = request.GET.get('q', '').strip()
        wid = request.GET.get('word_id')
        qs = WordAlias.objects.all()
        if kw:
            qs = qs.filter(alias__icontains=kw)
        if wid:
            qs = qs.filter(word_id=wid)
        return list_response(qs.order_by('-id'), request, word_alias_mapper)
    elif request.method in ['POST', 'PUT', 'PATCH']:
        if not request.user.is_authenticated:
            return JsonResponse({'code': 401, 'msg': '未登录'})
        data = parse_json(request)
        obj_id = data.get('id')
        fields = {
            'word_id': data.get('word_id'),
            'alias': data.get('alias', ''),
        }
        if obj_id:
            WordAlias.objects.filter(id=obj_id).update(**fields)
            obj = WordAlias.objects.get(id=obj_id)
        else:
            obj = WordAlias.objects.create(**fields)
        return JsonResponse({'code': 0, 'msg': 'ok', 'data': word_alias_mapper(obj)})
    return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})

# 命中记录 API
@csrf_exempt
def word_logs(request):
    if request.method == 'GET':
        wid = request.GET.get('word_id')
        qs = WordLog.objects.all()
        if wid:
            qs = qs.filter(word_id=wid)
        return list_response(qs.order_by('-id'), request, word_log_mapper)
    elif request.method in ['POST', 'PUT', 'PATCH']:
        if not request.user.is_authenticated:
            return JsonResponse({'code': 401, 'msg': '未登录'})
        data = parse_json(request)
        obj_id = data.get('id')
        fields = {
            'word_id': data.get('word_id'),
            'context': data.get('context', ''),
        }
        if obj_id:
            WordLog.objects.filter(id=obj_id).update(**fields)
            obj = WordLog.objects.get(id=obj_id)
        else:
            obj = WordLog.objects.create(**fields)
        return JsonResponse({'code': 0, 'msg': 'ok', 'data': word_log_mapper(obj)})
    return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})