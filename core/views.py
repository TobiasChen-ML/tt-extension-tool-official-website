from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from .models import Profile, Product, Order, UserInfo, Category, Word, WordAlias, WordLog
import random
import string
import json
import os
from wechat_pay.pay import build_order
from aliyun_sms import SMS
from dotenv import load_dotenv
load_dotenv()
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
    try:
        # 若已登录，也要确保 Profile 存在
        if request.user.is_authenticated:
            if not Profile.objects.filter(user=request.user).exists():
                Profile.objects.create(user=request.user, phone=getattr(request.user, 'username', '') or '')
            return
        # 未登录则使用默认账号自动登录
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
    # 确保当前用户一定有 Profile
    profile, _ = Profile.objects.get_or_create(
        user=request.user,
        defaults={'phone': getattr(request.user, 'username', '') or ''}
    )
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


# 映射函数（保留）
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
    elif request.method == 'DELETE':
        if not request.user.is_authenticated:
            return JsonResponse({'code': 401, 'msg': '未登录'})
        obj_id = request.GET.get('id') or parse_json(request).get('id')
        if not obj_id:
            return JsonResponse({'code': 400, 'msg': '缺少id'})
        deleted, _ = Category.objects.filter(id=obj_id).delete()
        return JsonResponse({'code': 0, 'msg': 'deleted', 'data': {'deleted': deleted}})
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
    elif request.method == 'DELETE':
        if not request.user.is_authenticated:
            return JsonResponse({'code': 401, 'msg': '未登录'})
        obj_id = request.GET.get('id') or parse_json(request).get('id')
        if not obj_id:
            return JsonResponse({'code': 400, 'msg': '缺少id'})
        deleted, _ = Word.objects.filter(id=obj_id).delete()
        return JsonResponse({'code': 0, 'msg': 'deleted', 'data': {'deleted': deleted}})
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
    elif request.method == 'DELETE':
        if not request.user.is_authenticated:
            return JsonResponse({'code': 401, 'msg': '未登录'})
        obj_id = request.GET.get('id') or parse_json(request).get('id')
        if not obj_id:
            return JsonResponse({'code': 400, 'msg': '缺少id'})
        deleted, _ = WordAlias.objects.filter(id=obj_id).delete()
        return JsonResponse({'code': 0, 'msg': 'deleted', 'data': {'deleted': deleted}})
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
    elif request.method == 'DELETE':
        if not request.user.is_authenticated:
            return JsonResponse({'code': 401, 'msg': '未登录'})
        obj_id = request.GET.get('id') or parse_json(request).get('id')
        if not obj_id:
            return JsonResponse({'code': 400, 'msg': '缺少id'})
        deleted, _ = WordLog.objects.filter(id=obj_id).delete()
        return JsonResponse({'code': 0, 'msg': 'deleted', 'data': {'deleted': deleted}})
    return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})

# 文本分析接口：分词并检索词库与别名，返回命中分类统计
@csrf_exempt
def analyze_text(request):
    if request.method != 'POST':
        return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})
    data = parse_json(request)
    text = (data.get('text') or '').strip()
    if not text:
        return JsonResponse({'code': 400, 'msg': 'text不能为空'})
    # 简单分词：按非字母数字拆分，并保留原文本用于模糊匹配
    import re
    tokens = [t.lower() for t in re.split(r"[^A-Za-z0-9']+", text) if t]

    # 构建查询：词本身或别名包含这些token，或原文本中包含词/别名（短语）
    hits = {}
    def ensure_cat(cat_name):
        if cat_name not in hits:
            hits[cat_name] = []

    # 1) 直接匹配 Word 中的短语出现在原文本
    word_qs = Word.objects.select_related('category').filter(is_active=True)
    for w in word_qs:
        phrase = w.word
        if not phrase:
            continue
        p = phrase.lower()
        if p in text.lower() or any(p in tok for tok in tokens):
            cat = w.category.name if w.category else 'unknown'
            ensure_cat(cat)
            hits[cat].append(phrase)
            WordLog.objects.create(word=w, context=text[:500])

    # 2) 匹配别名别称出现在原文本
    alias_qs = WordAlias.objects.select_related('word__category').all()
    for a in alias_qs:
        alias = (a.alias or '').lower()
        if not alias:
            continue
        if alias in text.lower() or any(alias in tok for tok in tokens):
            w = a.word
            cat = w.category.name if w and w.category else 'unknown'
            ensure_cat(cat)
            hits[cat].append(w.word)
            WordLog.objects.create(word=w, context=text[:500])

    # 去重与排序
    for cat in list(hits.keys()):
        uniq = sorted(set(hits[cat]), key=lambda x: (len(x), x))
        hits[cat] = uniq

    # 统计汇总：违禁词、品牌词等常用标签
    summary = {
        'forbidden': hits.get('forbidden', []),
        'illegal_crime': hits.get('illegal_crime', []),
        'violence_extremism': hits.get('violence_extremism', []),
        'adult_sexual': hits.get('adult_sexual', []),
        'hate_harassment': hits.get('hate_harassment', []),
        'brand': hits.get('brand', []),
        'trending': hits.get('trending', []),
    }
    counts = {k: len(v) for k, v in summary.items()}

    # 返回 category 显示名（description）映射，便于前端友好展示
    cat_display = {c.name: c.description for c in Category.objects.all()}

    return JsonResponse({'code': 0, 'msg': 'ok', 'data': {
        'hits': summary,
        'counts': counts,
        'display': cat_display,
        'tokens': tokens,
    }})

# 检测图片是否含水印
@csrf_exempt
def image_is_watermark(request):
    if request.method != 'POST':
        return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})

    data = parse_json(request)
    urls = data.get('image_urls') or data.get('urls')
    if not isinstance(urls, list) or not urls:
        return JsonResponse({'code': 400, 'msg': 'image_urls必须是非空数组'})

    import os
    import base64
    import requests
    import imghdr

    deepseek_key = os.getenv('DEEPSEEK_API_KEY') or os.getenv('DEEPSEEK_APIKEY')
  

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage
    except Exception:
        return JsonResponse({'code': 500, 'msg': '缺少依赖，请安装: langchain, langchain-openai。并在环境变量配置DEEPSEEK_API_KEY或OPENAI_API_KEY'})

    if not deepseek_key and not openai_key:
        return JsonResponse({'code': 500, 'msg': '缺少API Key，请配置DEEPSEEK_API_KEY或OPENAI_API_KEY'})


    model = ChatOpenAI(
        model_name = "deepseek-chat",
        openai_api_key = deepseek_key,
        openai_api_base = "https://api.deepseek.com/v1"
    )
    system_prompt =  """You are an image watermark detector. Given a single image, decide if it contains a visible watermark 
        such as stock-photo marks, semi-transparent text overlays, corner stamps, or company logos intended 
        to prevent unauthorized use. Respond with exactly one word: 'yes' or 'no'."""
    


    

    watermark_urls = []
    errors = {}

    for url in urls:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                errors[url] = f'HTTP {resp.status_code}'
                continue
            content = resp.content
            if len(content) > 10 * 1024 * 1024:
                errors[url] = 'image too large (>10MB)'
                continue
            kind = imghdr.what(None, h=content) or 'jpeg'
            b64 = base64.b64encode(content).decode('ascii')
            data_url = f'data:image/{kind};base64,{b64}'
            message = HumanMessage(
                content = json.dumps([
                    {"type":"text","text":f"{system_prompt}"},
                    {"type":"image","image_url":{"url":data_url}},
                ])
            )

            response = model.invoke([message])
            if response.content == 'yes':
                watermark_urls.append(url)
        except Exception as e:
            errors[url] = str(e)

    return JsonResponse({'code': 0, 'msg': 'ok', 'data': {'watermark_images': watermark_urls, 'errors': errors}})


@csrf_exempt
def rm_brand(request):
    """
    POST /api/words/rm_brand
    body: {"text": "..."}

    逻辑：将文本中出现的【品牌词库】(Category.name == 'brand') 的词条及其别名替换为''直接删除。
    大小写不敏感，按子串直接移除（中英文统一处理）。
    返回清洗后的文本和被移除的词列表。
    """
    if request.method != 'POST':
        return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})

    data = parse_json(request)
    text = (data.get('text') or '')
    if not text.strip():
        return JsonResponse({'code': 400, 'msg': 'text不能为空'})

    # 收集品牌词与别名
    phrases = []
    brand_words = Word.objects.select_related('category').filter(is_active=True, category__name__iexact='brand')
    phrases.extend([w.word for w in brand_words if (w.word or '').strip()])
    brand_aliases = WordAlias.objects.select_related('word__category').filter(word__category__name__iexact='brand')
    phrases.extend([a.alias for a in brand_aliases if (a.alias or '').strip()])

    # 去重并按长度降序，避免较短词先删造成重叠影响
    uniq_phrases = sorted(set(p.strip() for p in phrases if p), key=lambda s: (-len(s), s.lower()))

    import re
    cleaned = text
    removed = []
    for p in uniq_phrases:
        if not p:
            continue
        pattern = re.compile(re.escape(p), flags=re.IGNORECASE)
        if pattern.search(cleaned):
            cleaned = pattern.sub('', cleaned)
            removed.append(p)

    return JsonResponse({'code': 0, 'msg': 'ok', 'data': {
        'cleaned_text': cleaned,
        'removed': sorted(set(removed), key=lambda s: (-len(s), s.lower()))
    }})

@csrf_exempt
def rm_forbiden(request):
    """
    POST /api/words/rm_forbiden
    body: {"text": "..."}
    
    逻辑：将文本中出现的【违禁词库】(Category.name == 'forbidden') 的词条及其别名替换为''直接删除。
    大小写不敏感，按子串直接移除（中英文统一处理）。
    返回清洗后的文本和被移除的词列表。
    """
    if request.method != 'POST':
        return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})

    data = parse_json(request)
    text = (data.get('text') or '')
    if not text.strip():
        return JsonResponse({'code': 400, 'msg': 'text不能为空'})

    # 收集违禁词与别名
    phrases = []
    forbidden_words = Word.objects.select_related('category').filter(is_active=True, category__name__iexact='forbidden')
    phrases.extend([w.word for w in forbidden_words if (w.word or '').strip()])
    forbidden_aliases = WordAlias.objects.select_related('word__category').filter(word__category__name__iexact='forbidden')
    phrases.extend([a.alias for a in forbidden_aliases if (a.alias or '').strip()])

    # 去重并按长度降序，避免较短词先删造成重叠影响
    uniq_phrases = sorted(set(p.strip() for p in phrases if p), key=lambda s: (-len(s), s.lower()))

    import re
    cleaned = text
    removed = []
    for p in uniq_phrases:
        # 忽略空
        if not p:
            continue
        # 构建不区分大小写的安全替换（转义正则特殊符号）
        pattern = re.compile(re.escape(p), flags=re.IGNORECASE)
        if pattern.search(cleaned):
            cleaned = pattern.sub('', cleaned)
            removed.append(p)

    return JsonResponse({'code': 0, 'msg': 'ok', 'data': {
        'cleaned_text': cleaned,
        'removed': sorted(set(removed), key=lambda s: (-len(s), s.lower()))
    }})


@csrf_exempt
def clean_text_multi(request):
    """
    POST /api/words/clean_multi
    body: {
      "text": "...",
      "categories": ["forbidden","brand"],  # 可选，默认同时删除 forbidden 与 brand
      "keywords": ["...", "..."],           # 可选，模糊匹配进行替换
      "replace_with": "***"                   # 可选，关键词替换用的字符串，默认 ***
    }

    规则：
    - categories：收集指定分类（词条 + 别名），大小写不敏感，按子串直接删除（替换为''），为避免短词影响长词，按长度降序处理；
    - keywords：对提供的关键词进行大小写不敏感的子串匹配，将命中部分替换为 replace_with；
    - 先执行分类删除，再执行关键词替换；
    返回：cleaned_text、removed（按长度降序去重）、removed_by_category、replaced_keywords（含替换次数）。
    """
    if request.method != 'POST':
        return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})

    data = parse_json(request)
    text = (data.get('text') or '')
    if not text.strip():
        return JsonResponse({'code': 400, 'msg': 'text不能为空'})

    # 解析参数
    req_categories = data.get('categories') or [
        'forbidden', 'brand'
    ]
    # 规范化为小写
    req_categories = [str(c).strip().lower() for c in req_categories if str(c).strip()]
    keywords = data.get('keywords') or []
    keywords = [str(k).strip() for k in keywords if str(k).strip()]
    replace_with = data.get('replace_with')
    if replace_with is None:
        replace_with = '***'

    # 收集分类词及别名，并建立反向映射（phrase -> category）
    from django.db.models import Q
    phrases = []
    phrase_cat_map = {}

    # 词条
    word_qs = Word.objects.select_related('category').filter(
        is_active=True,
        category__name__in=req_categories
    )
    for w in word_qs:
        s = (w.word or '').strip()
        if s:
            phrases.append(s)
            phrase_cat_map.setdefault(s, w.category.name)
    # 别名
    alias_qs = WordAlias.objects.select_related('word__category').filter(
        word__category__name__in=req_categories
    )
    for a in alias_qs:
        s = (a.alias or '').strip()
        if s:
            phrases.append(s)
            phrase_cat_map.setdefault(s, a.word.category.name)

    # 去重 + 长度降序，避免短词优先导致重叠问题
    uniq_phrases = sorted(set(p.strip() for p in phrases if p), key=lambda s: (-len(s), s.lower()))

    import re
    cleaned = text
    removed = []
    removed_by_category = {c: [] for c in req_categories}

    # 先执行分类词删除
    for p in uniq_phrases:
        if not p:
            continue
        pattern = re.compile(re.escape(p), flags=re.IGNORECASE)
        if pattern.search(cleaned):
            cleaned = pattern.sub('', cleaned)
            removed.append(p)
            cat = phrase_cat_map.get(p)
            if cat:
                removed_by_category.setdefault(cat, [])
                removed_by_category[cat].append(p)

    # 再执行关键词替换（模糊子串，不区分大小写）
    replaced_keywords = []
    for kw in keywords:
        if not kw:
            continue
        pattern = re.compile(re.escape(kw), flags=re.IGNORECASE)
        # 统计替换次数：先找所有命中数
        matches = list(pattern.finditer(cleaned))
        count = len(matches)
        if count > 0:
            cleaned = pattern.sub(replace_with, cleaned)
        replaced_keywords.append({'keyword': kw, 'count': count})

    # 去重与排序（长度降序）
    removed = sorted(set(removed), key=lambda s: (-len(s), s.lower()))
    for c in list(removed_by_category.keys()):
        removed_by_category[c] = sorted(set(removed_by_category[c]), key=lambda s: (-len(s), s.lower()))

    return JsonResponse({'code': 0, 'msg': 'ok', 'data': {
        'cleaned_text': cleaned,
        'removed': removed,
        'removed_by_category': removed_by_category,
        'replaced_keywords': replaced_keywords,
    }})