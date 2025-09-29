from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.db import models
from .models import Profile, Product, Order, UserInfo, Category, Word, WordAlias, WordLog, StoreKey, PointsBalance, UsageLog, Suggestion, Trial
import random
import string
import json
import os
import difflib
import requests
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
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        # 设置较长的会话有效期（优先使用全局配置，否则默认90天）
        try:
            request.session.set_expiry(getattr(settings, 'SESSION_COOKIE_AGE', 60*60*24*90))
        except Exception:
            pass
        return redirect('dashboard')
    return render(request, 'login.html')


# 已移除自动登录逻辑，统一使用手机号+验证码登录


@login_required
def dashboard(request):
    # 确保当前用户一定有 Profile
    profile, _ = Profile.objects.get_or_create(
        user=request.user,
        defaults={'phone': getattr(request.user, 'username', '') or ''}
    )
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    products = Product.objects.all()
    # 新增：当前用户的店铺密钥列表（只读展示）
    store_keys = StoreKey.objects.filter(user=request.user).order_by('-created_at')
    # 新增：剩余积分（汇总当前用户所有店铺）
    points_qs = PointsBalance.objects.filter(user=request.user)
    points_total = points_qs.aggregate(total=models.Sum('points')).get('total') or 0
    # 新增：调用日志（按该用户关联店铺代码筛选）
    store_codes = list(store_keys.values_list('store_code', flat=True))
    usage_logs = UsageLog.objects.filter(user=request.user, store_code__in=store_codes).order_by('-created_at')[:100]
    return render(request, 'dashboard.html', {
        'profile': profile,
        'orders': orders,
        'products': products,
        'store_keys': store_keys,
        'points_total': points_total,
        'usage_logs': usage_logs,
    })


def logout_view(request):
    logout(request)
    return redirect('home')


# -------- 统一的简单增改查API（不做删除） --------

def parse_json(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return {}

@csrf_exempt
def words_classification(request):
    if request.method != 'POST':
        return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})
    data = parse_json(request)
    # 更健壮的请求体处理，支持对象/数组/字符串
    if isinstance(data, dict):
        hotwords = data.get('hotwords') or []
    elif isinstance(data, list):
        hotwords = data
    elif isinstance(data, str):
        hotwords = [data]
    else:
        hotwords = []
    if not isinstance(hotwords, list) or not hotwords:
        return JsonResponse({'code': 400, 'msg': 'hotwords 必须为非空数组'})
    # DeepSeek 尝试
    
    api_key = os.getenv('DEEPSEEK_API_KEY') or getattr(settings, 'DEEPSEEK_API_KEY', None)
  
    if api_key:
        system_prompt = '你是一个商品词提取专家，擅长从热词中提炼商品名词。'
        user_prompt = (
                "【任务】\n"
                    "1. 输入包含多条商品标题，每条可能包含品牌、尺寸、材质、用途等描述。\n"
                    "2. 请在所有标题中，识别并聚类出相同或相似的商品词（即产品类别/产品核心名词），同义词/近义词视为同一类。\n"
                    "3. 统计这些商品词在所有标题中出现的频率，只要出现频率较高（即在多条标题中重复出现），就应当保留。\n"
                    "4. 商品词必须是产品类别或核心物品名称，不要输出品牌、型号、形容词、用途或场景词。\n"
                    "5. 输出时至少包含一个商品名词，不能返回空结果。\n"
                    "6. 输出格式：多个商品名词用英文逗号隔开。\n"
                    "\n"
                    "【示例】\n"
                    "输入：\n"
                    "Cast Iron Plate Weight Plate for Strength Training and Weightlifting, 2-Inch Center (Olympic), 2.5LB (Set of 4)\n"
                    "Cast Iron Olympic 2-Inch Grip Plate for Barbell, 5 Pound Set of 2 Plates Iron Grip Plates for Weightlifting\n"
                    "Fitness Change Weight Plates 1.25LB 2.5LB 5LB Pairs Support Plates Olympic Plates for Weight Lifting\n"
                    "Change Plates Set 1.25LB, 2.5LB, 5LB - Rubber-Coated Weight Plates in Pairs, Olympic Bumper Plates\n"
                    "输出：Weight Plate,Grip Plate,Change Plate\n"
                    "\n"
                    "输入：\n"
                    "Waist Trimmer Wrap, Waist Trainer for Women and Men, Sweat Band Waist Trainer\n"
                    "Waist Trainer for Women Men Sweat Belt Waist Trimmer Belly Band Stomach Wraps\n"
                    "输出：Waist Trainer,Waist Trimmer\n"
                    "\n"
                    "【要求】\n"
                    "- 仅输出最终提取出的商品名词，用英文逗号隔开，不要解释。控制数量少于20个。\n"
                f'- 现在请处理我的输入：{", ".join([str(w) for w in hotwords])}'
        )
        payload = {
            'model': 'deepseek-chat',
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'temperature': 0,
            'max_tokens': 512,
        }
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }
        try:
            resp = requests.post('https://api.deepseek.com/beta/chat/completions',
                                    headers=headers, json=payload, timeout=10)
            if resp.ok:
                rj = resp.json()
                text = (rj.get('choices') or [{}])[0].get('message', {}).get('content', '') or ''
                result = text.strip()
                result = result.replace('、', ',').replace('|', ',').strip().strip('"\'`')
                # 规范化逗号分隔
                parts = [p.strip() for p in result.split(',') if p.strip()]
                result = ','.join(parts)
               
                if result:
                    return JsonResponse({'code': 0, 'msg': 'ok', 'data': result})
        except requests.exceptions.RequestException:
            # DeepSeek 请求异常（超时、连接错误等）时，进入回退逻辑
            pass

    # 回退：基于词频与长度的启发式
    import re
    from collections import Counter
    tokens = []
    for w in hotwords:
        if not isinstance(w, str):
            continue
        s = w.strip()
        if not s:
            continue
        cleaned = re.sub(r'[^0-9A-Za-z\u4e00-\u9fa5]+', '', s)
        if not cleaned:
            continue
        tokens.append(cleaned.lower())
    if not tokens:
        return JsonResponse({'code': 0, 'msg': 'ok', 'data': ''})
    freq = Counter(tokens)
    def score(t):
        return freq[t] * 2 + len(t) * 0.3
    top = sorted(freq.keys(), key=lambda t: (-score(t), t))[:10]
    result = ','.join(top)
    return JsonResponse({'code': 0, 'msg': 'ok', 'data': result})


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

@csrf_exempt
def suggestion(request):
    if request.method != 'POST':
        return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})
    data = parse_json(request)
    # 兼容 JSON 与表单提交
    shop_code = None
    suggest_text = ''
    phone = ''
    if isinstance(data, dict):
        shop_code = data.get('ShopCode') or data.get('shop_code')
        suggest_text = data.get('suggest') or ''
        phone = data.get('phone') or ''
    if not shop_code:
        shop_code = request.POST.get('ShopCode') or request.POST.get('shop_code')
    if not suggest_text:
        suggest_text = request.POST.get('suggest') or ''
    if not phone:
        phone = request.POST.get('phone') or ''

    if not shop_code:
        return JsonResponse({'code': 400, 'msg': 'ShopCode 必填'})

    try:
        # 通过数据库路由写入 suggests 库
        Suggestion.objects.create(
            shop_code=str(shop_code),
            suggest=str(suggest_text or ''),
            phone=str(phone or ''),
        )
    except Exception as e:
        return JsonResponse({'code': 500, 'msg': f'写入失败: {str(e)}'})

    return JsonResponse({'code': 200})


@csrf_exempt
def is_valid_customer(request):
    if request.method != 'POST':
        return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'code': 400, 'msg': '请求体必须是有效JSON'})
    shopcode = (payload.get('shopcode') or '').strip()
    function = (payload.get('function') or '').strip()
    if not shopcode:
        return JsonResponse({'code': 400, 'msg': 'shopcode 必填'})

    exists_in_store = StoreKey.objects.filter(store_code=shopcode).exists()
    ok = False
    message = ''
    if exists_in_store:
        ok = True
        message = 'StoreKey 已存在，允许使用'
    else:
        obj, _ = Trial.objects.get_or_create(shopcode=shopcode, defaults={'times': 0})
        if obj.times >= 5:
            ok = False
            message = '试用次数达到上限'
        else:
            obj.times += 1
            obj.save()
            ok = True
            message = '试用次数+1，允许使用'

    try:
        UsageLog.objects.create(
            user=request.user if getattr(request, 'user', None) and request.user.is_authenticated else None,
            content=f"is_valid_customer: {function}",
            store_code=shopcode,
            points_consumed=0,
            status='success' if ok else 'failure'
        )
    except Exception:
        pass

    return JsonResponse({'code': 0, 'msg': 'ok', 'data': {'valid': ok, 'shopcode': shopcode, 'function': function, 'reason': message}})

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

# 新增：调整用户积分接口
@csrf_exempt
def adjust_points(request):
    if request.method != 'POST':
        return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})
    # 需要登录
    if not request.user.is_authenticated:
        return JsonResponse({'code': 401, 'msg': '未登录'})
    data = parse_json(request)
    store_code = (data.get('store_code') or '').strip()
    try:
        delta = int(data.get('delta'))
    except Exception:
        return JsonResponse({'code': 400, 'msg': '参数错误：delta 必须是整数'})
    if not store_code:
        return JsonResponse({'code': 400, 'msg': '缺少 store_code'})
    # 仅允许操作当前用户拥有的店铺
    if not StoreKey.objects.filter(user=request.user, store_code=store_code).exists():
        return JsonResponse({'code': 403, 'msg': '无权操作该店铺'})
    pb, _ = PointsBalance.objects.get_or_create(user=request.user, store_code=store_code)
    new_points = pb.points + delta
    if new_points < 0:
        return JsonResponse({'code': 400, 'msg': '积分不足，无法扣减'})
    pb.points = new_points
    pb.save()
    # 写入调用日志（调整积分不消耗积分，记录状态）
    try:
        UsageLog.objects.create(
            user=request.user,
            points_consumed=0,
            content=f"adjust_points delta={delta}",
            store_code=store_code,
            status='success'
        )
    except Exception:
        pass
    return JsonResponse({'code': 0, 'msg': 'ok', 'data': {'store_code': store_code, 'points': pb.points}})

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
    import base64
    import os
    import requests
    import imghdr


    if request.method != 'POST':
        return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})

    data = parse_json(request)
    urls = data.get('image_urls') or data.get('urls')
    if not isinstance(urls, list) or not urls:
        return JsonResponse({'code': 400, 'msg': 'image_urls必须是非空数组'})

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
            data_url = compress_b64_image(data_url)


            print(response.content)
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
      "categories": ["forbidden","brand","keyword"],
      "hotwords": ""  # 新增，可选，默认为空字符串
    }
    """
    if request.method != 'POST':
        return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})

    data = parse_json(request)
    text = (data.get('text') or '')
    if not text.strip():
        return JsonResponse({'code': 400, 'msg': 'text不能为空'})

    # 新增：热词参数，默认空字符串
    hotwords = str(data.get('hotwords', '') or '').strip()

    # 新增：当 categories 为空列表时，直接返回原文本与空结果
    categories_param = data.get('categories')
    if isinstance(categories_param, list) and len(categories_param) == 0:
        cleaned = text
        removed_tokens = []
        removed_by_category = []
        appended_keywords = []
        return JsonResponse({'code': 0, 'msg': 'ok', 'data': {
            'cleaned_text': cleaned,
            'removed_tokens': removed_tokens,
            'removed_by_category': removed_by_category,
            'appended_keywords': appended_keywords,
        }})

    # 解析参数
    req_categories = categories_param or ['forbidden', 'brand', 'keyword']
    req_categories = [str(c).strip().lower() for c in req_categories if str(c).strip()]
    # 若 hotwords 非空，则移除 keyword 类别，不执行 keyword 相关逻辑
    if hotwords:
        req_categories = [c for c in req_categories if c != 'keyword']

    import re
    from django.db.models import Q
    # 分词：按非字母数字与撇号拆分，保留较有意义的 token（长度>=2）
    tokens = [t.lower() for t in re.split(r"[^A-Za-z0-9']+", text) if len(t) >= 2]
    uniq_tokens = sorted(set(tokens))

    # DeepSeek API（OpenAI兼容）判断同义助手
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')
    def _is_synonym(a: str, b: str) -> bool:
        # 若未配置密钥，降级为严格相似度判断
        a1 = (a or '').strip().lower()
        b1 = (b or '').strip().lower()
        if not a1 or not b1:
            return False
        # 先用本地相似度快速过滤，避免无意义调用
        ratio = difflib.SequenceMatcher(None, a1, b1).ratio()
        if ratio >= 0.92:
            return True
        if not DEEPSEEK_API_KEY:
            return False
        try:
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "You are a strict synonym/equivalence checker. Reply only 'yes' or 'no'."},
                    {"role": "user", "content": f"Are '{a1}' and '{b1}' synonyms or representing the same brand/company/product? Answer yes or no."}
                ],
                "stream": False
            }
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            }
            resp = requests.post("https://api.deepseek.com/chat/completions", json=payload, headers=headers, timeout=6)
            if resp.status_code == 200:
                jr = resp.json()
                content = str(jr.get('choices', [{}])[0].get('message', {}).get('content', '')).strip().lower()
                return content.startswith('y') or ('yes' in content)
        except Exception:
            # 网络或API错误时，不判定为同义
            return False
        return False

    # 模糊搜索候选（按 token 局部匹配），返回 [(phrase, category, score)]
    def _fuzzy_candidates(token: str):
        cands = []
        # 词条
        w_qs = Word.objects.select_related('category').filter(
            is_active=True,
            category__name__in=req_categories,
            word__icontains=token
        )[:200]
        for w in w_qs:
            s = (w.word or '').strip()
            if not s:
                continue
            score = difflib.SequenceMatcher(None, token.lower(), s.lower()).ratio()
            cands.append((s, w.category.name.lower(), score))
        # 别名
        a_qs = WordAlias.objects.select_related('word__category').filter(
            word__category__name__in=req_categories,
            alias__icontains=token
        )[:200]
        for a in a_qs:
            s = (a.alias or '').strip()
            if not s:
                continue
            score = difflib.SequenceMatcher(None, token.lower(), s.lower()).ratio()
            cands.append((s, a.word.category.name.lower(), score))
        # 选取得分较高的前若干个
        cands.sort(key=lambda x: (-x[2], -len(x[0]), x[0].lower()))
        return cands[:5]

    cleaned = text
    removed_tokens = []
    removed_by_category = {c: [] for c in req_categories}

    # 对每个 token：模糊搜索候选→DeepSeek判断同义→同义则删除该 token（按词边界）
    for tk in uniq_tokens:
        candidates = _fuzzy_candidates(tk)
        # 仅当存在较相关候选时才尝试判断
        if not candidates:
            continue
        # 若任一候选与该token同义/等价，则删除该token
        synonym_hit = None
        for phrase, cat, score in candidates:
            # 先做分数门槛（避免过低匹配触发API）
            if score < 0.6:
                continue
            # 仅对 forbidden 执行删除（品牌改为通过 DeepSeek 整体识别后统一删除）
            if cat in ('forbidden',) and _is_synonym(tk, phrase):
                synonym_hit = (phrase, cat)
                break
        if synonym_hit:
            pattern = re.compile(rf"\b{re.escape(tk)}\b", flags=re.IGNORECASE)
            if pattern.search(cleaned):
                cleaned = pattern.sub('', cleaned)
                removed_tokens.append(tk)
                cat = synonym_hit[1]
                removed_by_category.setdefault(cat, [])
                removed_by_category[cat].append(tk)

    # 品牌词：调用 DeepSeek API 从整段文本中抽取品牌词，并统一从原文本中移除
    def _extract_brands_with_deepseek(full_text: str):
        api_key = os.getenv('DEEPSEEK_API_KEY', '')
        if not api_key or not (full_text or '').strip():
            return []
        try:
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "你是一个严格的品牌词抽取器。必须100%确认是品牌词才能提取，宁可漏判不可误判。，返回JSON数组。"},
                    {"role": "user", "content": (
                        "请从下面文本中找出品牌词，规则："
                        "1) 排除规则优先：以下情况绝对不是品牌词："
                        "   - 通用产品名称（如knife, tool, drill, machine等）"
                        "   - 产品特性描述（如rainbow, cute, small, legal等）"
                        "   - 产品用途描述（如self defense, camping, EDC等）"
                        "   - 含数字的型号代码（如6655 R）"
                        "   - 目标人群（如women, womens）"
                        "   - 节日/场合（如birthday, gifts）"
                        ""
                        "2) 品牌词特征（符合2个及以上）："
                        "   - 是专有名词，不是普通英文单词"
                        "   - 在商业语境中已知是品牌名称"
                        "   - 无法自然地直译成中文"
                        "   - 不包含产品功能描述"
                        "   - 一般全部都大写的单词或词组"
                        ""
                        "3) 严格标准："
                        "   - 如果不确定100%是品牌词，就排除"
                        "   - 只提取明确知名品牌的品牌名称"
                        "   - 不要猜测或推断品牌"
                        "4) 输出格式：严格返回JSON：{\"brands\": [\"brand1\", \"brand2\"]}，如果没有品牌词就返回空数组"
                        f"文本：{full_text}"
                    )}
                ],
                "stream": False
            }
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            resp = requests.post("https://api.deepseek.com/chat/completions", json=payload, headers=headers, timeout=8)
            if resp.status_code != 200:
                return []
            jr = resp.json()
            content = str(jr.get('choices', [{}])[0].get('message', {}).get('content', '')).strip()
            import json as _json
            brands = []
            try:
                obj = _json.loads(content)
                if isinstance(obj, dict) and isinstance(obj.get('brands'), list):
                    brands = [str(x).strip() for x in obj.get('brands') if str(x).strip()]
                elif isinstance(obj, list):
                    brands = [str(x).strip() for x in obj if str(x).strip()]
            except Exception:
                # 宽松解析：逗号/换行分隔
                parts = [p.strip() for p in re.split(r"[,]", content) if p.strip()]
                brands = parts
            # 过滤掉全数字/主要为数字的项
            def _is_mostly_digits(s: str):
                digits = sum(ch.isdigit() for ch in s)
                return digits >= max(3, len(s) * 0.6)
            brands = [b for b in brands if len(b) >= 2 and not _is_mostly_digits(b)]
            return brands
        except Exception:
            return []

    if 'brand' in req_categories:
        brands = _extract_brands_with_deepseek(text)
        if brands:
            # 按长度降序移除，避免子串影响
            phrases = sorted(set(b for b in brands if b), key=lambda s: (-len(s.strip()), s.lower()))
            for p in phrases:
                if not p:
                    continue
                # 使用词边界匹配，避免删除非品牌词的子串（如 Pineapple 中的 apple）
                pattern = re.compile(rf"\b{re.escape(p)}\b", flags=re.IGNORECASE)
                if pattern.search(cleaned):
                    cleaned = pattern.sub('', cleaned)
                    removed_tokens.append(p)
                    removed_by_category.setdefault('brand', [])
                    removed_by_category['brand'].append(p)

    # 关键词：基于分词在 keyword 类别中模糊搜索最相关词并追加到文本末尾
    appended_keywords = []

    def _best_keyword_for_token(token: str):
        cands = []
        # 仅在 keyword 分类中查找
        w_qs = Word.objects.select_related('category').filter(
            is_active=True, category__name__iexact='keyword', word__icontains=token
        )[:300]
        for w in w_qs:
            s = (w.word or '').strip()
            if s:
                cands.append((s, difflib.SequenceMatcher(None, token.lower(), s.lower()).ratio()))
        a_qs = WordAlias.objects.select_related('word__category').filter(
            word__category__name__iexact='keyword', alias__icontains=token
        )[:300]
        for a in a_qs:
            s = (a.alias or '').strip()
            if s:
                cands.append((s, difflib.SequenceMatcher(None, token.lower(), s.lower()).ratio()))
        if not cands:
            return None
        cands.sort(key=lambda x: (-x[1], -len(x[0]), x[0].lower()))
        best = cands[0]
        return best if best[1] >= 0.6 else None

    # 仅对未被删除的 token 做关键词追加，降低噪声
    tokens_for_keywords = [t for t in uniq_tokens if t not in set(removed_tokens)]
    if 'keyword' in req_categories:
        for tk in tokens_for_keywords:
            m = _best_keyword_for_token(tk)
            if not m:
                continue
            best_phrase = m[0]
            if best_phrase and best_phrase.lower() not in [x.lower() for x in appended_keywords]:
                # 末尾以空格追加一次
                cleaned = (cleaned.rstrip() + (' ' if cleaned and not cleaned.endswith(' ') else '') + best_phrase)
                appended_keywords.append(best_phrase)

    # 新增：在程序末尾确保 hotwords 中每个词都包含在 cleaned 中
    if hotwords:
        for w in [x for x in hotwords.split(' ') if x.strip()]:
            # 用词边界判断是否已存在，避免子串误判
            if not re.search(rf"\b{re.escape(w)}\b", cleaned, flags=re.IGNORECASE):
                cleaned = (cleaned.rstrip() + (' ' if cleaned and not cleaned.endswith(' ') else '') + w)

    # 去重与排序清理
    removed_tokens = sorted(set(removed_tokens), key=lambda s: (-len(s), s.lower()))
    for c in list(removed_by_category.keys()):
        removed_by_category[c] = sorted(set(removed_by_category[c]), key=lambda s: (-len(s), s.lower()))

    # 智能长度裁剪：确保 cleaned_text 不超过 255 字符
    def _smart_trim(text: str):
        if len(text) <= 250:
            return text
        import re
        # 分词，保留原大小写用于保留度判断
        tokens = [t for t in re.split(r"[^A-Za-z0-9']+", text) if len(t) >= 1]
        if not tokens:
            return text[:250]
        # 停用词（英文常见介词/连词/语气词）
        stopwords = {
            'a','an','the','and','or','but','if','then','than','so','too','very','just','really','quite','rather','some','any',
            'in','on','at','by','for','to','of','from','with','without','about','into','over','under','between','among','through','during',
            'up','down','out','off','again','still','ever','never','not','no','yes','as','is','are','was','were','be','been','being',
            'this','that','these','those','here','there','now','today','yesterday','tomorrow','i','you','he','she','it','we','they'
        }
        # 计算每个词的重要度：是否为关键词、是否在 removed_tokens 中、长度、是否停用词
        import collections
        Counter = collections.Counter
        freq = Counter([t.lower() for t in tokens])
        # 保护已追加的关键词与 hotwords（若存在），避免被裁剪优先移除
        appended_set = {k.lower() for k in appended_keywords} | {w.lower() for w in (hotwords.split(' ') if hotwords else []) if w.strip()}
        removed_set = {k.lower() for k in removed_tokens}
        def importance(t: str):
            tl = t.lower()
            score = 0
            # 关键词/热词加权
            if tl in appended_set:
                score += 3
            # 被删除过的词（通常是敏感/品牌）若仍出现，避免误删，适度加权
            if tl in removed_set:
                score += 2
            # 词长、频次
            score += min(len(t), 10) * 0.3
            score += min(freq[tl], 5) * 0.5
            # 停用词降权
            if tl in stopwords:
                score -= 3
            return score
        # 生成移除顺序：先删除重要度低的、再短的、再频次低的
        order = sorted([(t, importance(t)) for t in tokens], key=lambda x: (x[1], len(x[0]), freq[x[0].lower()]))
        # 逐步移除词（仅在文本中替换一次），直到长度<=255
        trimmed = text
        for t, _ in order:
            if len(trimmed) <= 255:
                break
            # 以词边界移除一次出现，避免数字/撇号破坏
            pattern = re.compile(rf"\b{re.escape(t)}\b")
            trimmed_new = pattern.sub('', trimmed, count=1)
            if trimmed_new != trimmed:
                trimmed = trimmed_new
        # 如果仍超长，做末尾截断（保留完整词边界尽量）
        return trimmed[:255]

    # 根据 hotwords 非空决定是否进行长度裁剪到255
    if hotwords:
        cleaned = _smart_trim(cleaned)
    # 移除amazon相关字符(不区分大小写)
    cleaned = cleaned.replace('amazon', '').replace('AMAZON', '').replace('Amazon', '')

    return JsonResponse({'code': 0, 'msg': 'ok', 'data': {
        'cleaned_text': cleaned,
        'removed_tokens': removed_tokens,
        'removed_by_category': removed_by_category,
        'appended_keywords': appended_keywords,
    }})


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


@csrf_exempt
def recharge(request):
    if request.method != 'POST':
        return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})
    # 从表单、JSON或查询参数获取金额，默认19.90
    amount = request.POST.get('amount')
    if not amount:
        try:
            body = request.body.decode('utf-8') or ''
            import json as _json
            amount = (_json.loads(body).get('amount') if body else None)
        except Exception:
            amount = None
    if not amount:
        amount = '19.90'
    try:
        payload_json = build_order(request.user.id if request.user.is_authenticated else 0, amount)
        return HttpResponse(payload_json, content_type='application/json')
    except Exception as e:
        return JsonResponse({'code': 500, 'msg': f'下单失败: {e}'})




def find_user_by_username_or_phone(value):
    value = (value or '').strip()
    if not value:
        return None
    try:
        # 先按用户名
        user = User.objects.get(username=value)
        return user
    except User.DoesNotExist:
        pass
    try:
        # 再按手机号关联的 Profile
        from .models import Profile
        p = Profile.objects.get(phone=value)
        return p.user
    except Profile.DoesNotExist:
        return None

@csrf_exempt
def super_settings(request):
    # 简单的会话标记验证，通过后才能操作
    verified = request.session.get('super_verified') == True
    error = None
    msg = None

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'verify':
            pwd = request.POST.get('password', '')
            if pwd == 'tklingxi666':
                request.session['super_verified'] = True
                verified = True
                msg = '验证成功'
            else:
                error = '超级密码错误'
        elif action == 'set_storekey':
            if not verified:
                error = '请先完成超级密码验证'
            else:
                username = request.POST.get('username')
                store_code = (request.POST.get('store_code') or '').strip()
                secret = (request.POST.get('secret') or '').strip()
                user = find_user_by_username_or_phone(username)
                if not user:
                    error = '未找到该用户（用户名或手机号）'
                elif not store_code:
                    error = '店铺代码不能为空'
                elif not secret:
                    error = '密钥不能为空'
                else:
                    sk, created = StoreKey.objects.update_or_create(
                        user=user, store_code=store_code,
                        defaults={'secret': secret}
                    )
                    msg = '已保存' if created else '已更新'
    # 展示已有 store keys，若未验证则为空
    store_keys = StoreKey.objects.all().order_by('-created_at') if verified else []
    return render(request, 'super_settings.html', {
        'verified': verified,
        'error': error,
        'msg': msg,
        'store_keys': store_keys,
    })


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
      "categories": ["forbidden","brand","keyword"],
      "hotwords": ""  # 新增，可选，默认为空字符串
    }
    """
    if request.method != 'POST':
        return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})

    data = parse_json(request)
    text = (data.get('text') or '')
    if not text.strip():
        return JsonResponse({'code': 400, 'msg': 'text不能为空'})

    # 新增：热词参数，默认空字符串
    hotwords = str(data.get('hotwords', '') or '').strip()

    # 新增：当 categories 为空列表时，直接返回原文本与空结果
    categories_param = data.get('categories')
    if isinstance(categories_param, list) and len(categories_param) == 0:
        cleaned = text
        removed_tokens = []
        removed_by_category = []
        appended_keywords = []
        return JsonResponse({'code': 0, 'msg': 'ok', 'data': {
            'cleaned_text': cleaned,
            'removed_tokens': removed_tokens,
            'removed_by_category': removed_by_category,
            'appended_keywords': appended_keywords,
        }})

    # 解析参数
    req_categories = categories_param or ['forbidden', 'brand', 'keyword']
    req_categories = [str(c).strip().lower() for c in req_categories if str(c).strip()]
    # 若 hotwords 非空，则移除 keyword 类别，不执行 keyword 相关逻辑
    if hotwords:
        req_categories = [c for c in req_categories if c != 'keyword']

    import re
    from django.db.models import Q
    # 分词：按非字母数字与撇号拆分，保留较有意义的 token（长度>=2）
    tokens = [t.lower() for t in re.split(r"[^A-Za-z0-9']+", text) if len(t) >= 2]
    uniq_tokens = sorted(set(tokens))

    # DeepSeek API（OpenAI兼容）判断同义助手
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')
    def _is_synonym(a: str, b: str) -> bool:
        # 若未配置密钥，降级为严格相似度判断
        a1 = (a or '').strip().lower()
        b1 = (b or '').strip().lower()
        if not a1 or not b1:
            return False
        # 先用本地相似度快速过滤，避免无意义调用
        ratio = difflib.SequenceMatcher(None, a1, b1).ratio()
        if ratio >= 0.92:
            return True
        if not DEEPSEEK_API_KEY:
            return False
        try:
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "You are a strict synonym/equivalence checker. Reply only 'yes' or 'no'."},
                    {"role": "user", "content": f"Are '{a1}' and '{b1}' synonyms or representing the same brand/company/product? Answer yes or no."}
                ],
                "stream": False
            }
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            }
            resp = requests.post("https://api.deepseek.com/chat/completions", json=payload, headers=headers, timeout=6)
            if resp.status_code == 200:
                jr = resp.json()
                content = str(jr.get('choices', [{}])[0].get('message', {}).get('content', '')).strip().lower()
                return content.startswith('y') or ('yes' in content)
        except Exception:
            # 网络或API错误时，不判定为同义
            return False
        return False

    # 模糊搜索候选（按 token 局部匹配），返回 [(phrase, category, score)]
    def _fuzzy_candidates(token: str):
        cands = []
        # 词条
        w_qs = Word.objects.select_related('category').filter(
            is_active=True,
            category__name__in=req_categories,
            word__icontains=token
        )[:200]
        for w in w_qs:
            s = (w.word or '').strip()
            if not s:
                continue
            score = difflib.SequenceMatcher(None, token.lower(), s.lower()).ratio()
            cands.append((s, w.category.name.lower(), score))
        # 别名
        a_qs = WordAlias.objects.select_related('word__category').filter(
            word__category__name__in=req_categories,
            alias__icontains=token
        )[:200]
        for a in a_qs:
            s = (a.alias or '').strip()
            if not s:
                continue
            score = difflib.SequenceMatcher(None, token.lower(), s.lower()).ratio()
            cands.append((s, a.word.category.name.lower(), score))
        # 选取得分较高的前若干个
        cands.sort(key=lambda x: (-x[2], -len(x[0]), x[0].lower()))
        return cands[:5]

    cleaned = text
    removed_tokens = []
    removed_by_category = {c: [] for c in req_categories}

    # 对每个 token：模糊搜索候选→DeepSeek判断同义→同义则删除该 token（按词边界）
    for tk in uniq_tokens:
        candidates = _fuzzy_candidates(tk)
        # 仅当存在较相关候选时才尝试判断
        if not candidates:
            continue
        # 若任一候选与该token同义/等价，则删除该token
        synonym_hit = None
        for phrase, cat, score in candidates:
            # 先做分数门槛（避免过低匹配触发API）
            if score < 0.6:
                continue
            # 仅对 forbidden 执行删除（品牌改为通过 DeepSeek 整体识别后统一删除）
            if cat in ('forbidden',) and _is_synonym(tk, phrase):
                synonym_hit = (phrase, cat)
                break
        if synonym_hit:
            pattern = re.compile(rf"\b{re.escape(tk)}\b", flags=re.IGNORECASE)
            if pattern.search(cleaned):
                cleaned = pattern.sub('', cleaned)
                removed_tokens.append(tk)
                cat = synonym_hit[1]
                removed_by_category.setdefault(cat, [])
                removed_by_category[cat].append(tk)

    # 品牌词：调用 DeepSeek API 从整段文本中抽取品牌词，并统一从原文本中移除
    def _extract_brands_with_deepseek(full_text: str):
        api_key = os.getenv('DEEPSEEK_API_KEY', '')
        if not api_key or not (full_text or '').strip():
            return []
        try:
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "你是一个严格的品牌词抽取器。必须100%确认是品牌词才能提取，宁可漏判不可误判。，返回JSON数组。"},
                    {"role": "user", "content": (
                           "请从下面文本中找出品牌词，规则：\n"
                            "1) 排除规则（以下情况绝对不是品牌词）：\n"
                            "   - 通用产品名称（如 knife, tool, drill, machine 等）\n"
                            "   - 产品特性描述（如 rainbow, cute, small, legal 等）\n"
                            "   - 产品用途描述（如 self defense, camping, EDC 等）\n"
                            "   - 含数字的型号代码（如 6655 R）\n"
                            "   - 目标人群（如 women, womens）\n"
                            "   - 节日/场合（如 birthday, gifts）\n"
                            "\n"
                            "2) 品牌词特征（符合1个及以上即可判断为品牌词）：\n"
                            "   - 专有名词，不是普通英文单词\n"
                            "   - 在商业语境中常作为品牌或卖家名出现\n"
                            "   - 无法自然直译成中文\n"
                            "   - 不包含产品功能描述\n"
                            "   - 一般首字母大写的单词或全部大写的单词\n"
                            "   - 拼写看似不规范，或不是常见英文词汇\n"
                            "\n"
                            "3) 判断标准：\n"
                            "   - 如果一个词既不是常见英文单词，又不是常见产品通用词，那么优先作为品牌词保留\n"
                            "   - 即使不是国际知名品牌，也要提取出来（例如小众品牌、店铺品牌）\n"
                            "   - 如果完全无法判断，可以标注为【可能是品牌词】并输出\n"
                            "4) 输出格式：严格返回JSON：{\"brands\": [\"brand1\", \"brand2\"]}，如果没有品牌词就返回空数组"
                            f"文本：{full_text}"
                    )}
                ],
                "stream": False
            }
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            resp = requests.post("https://api.deepseek.com/chat/completions", json=payload, headers=headers, timeout=8)
            if resp.status_code != 200:
                return []
            jr = resp.json()
            content = str(jr.get('choices', [{}])[0].get('message', {}).get('content', '')).strip()
            import json as _json
            brands = []
            try:
                obj = _json.loads(content)
                if isinstance(obj, dict) and isinstance(obj.get('brands'), list):
                    brands = [str(x).strip() for x in obj.get('brands') if str(x).strip()]
                elif isinstance(obj, list):
                    brands = [str(x).strip() for x in obj if str(x).strip()]
            except Exception:
                # 宽松解析：逗号/换行分隔
                parts = [p.strip() for p in re.split(r"[,]", content) if p.strip()]
                brands = parts
            # 过滤掉全数字/主要为数字的项
            def _is_mostly_digits(s: str):
                digits = sum(ch.isdigit() for ch in s)
                return digits >= max(3, len(s) * 0.6)
            brands = [b for b in brands if len(b) >= 2 and not _is_mostly_digits(b)]
            return brands
        except Exception:
            return []

    if 'brand' in req_categories:
        brands = _extract_brands_with_deepseek(text)
        if brands:
            # 按长度降序移除，避免子串影响
            phrases = sorted(set(b for b in brands if b), key=lambda s: (-len(s.strip()), s.lower()))
            for p in phrases:
                if not p:
                    continue
                # 使用词边界匹配，避免删除非品牌词的子串（如 Pineapple 中的 apple）
                pattern = re.compile(rf"\b{re.escape(p)}\b", flags=re.IGNORECASE)
                if pattern.search(cleaned):
                    cleaned = pattern.sub('', cleaned)
                    removed_tokens.append(p)
                    removed_by_category.setdefault('brand', [])
                    removed_by_category['brand'].append(p)

    # 关键词：基于分词在 keyword 类别中模糊搜索最相关词并追加到文本末尾
    appended_keywords = []

    def _best_keyword_for_token(token: str):
        cands = []
        # 仅在 keyword 分类中查找
        w_qs = Word.objects.select_related('category').filter(
            is_active=True, category__name__iexact='keyword', word__icontains=token
        )[:300]
        for w in w_qs:
            s = (w.word or '').strip()
            if s:
                cands.append((s, difflib.SequenceMatcher(None, token.lower(), s.lower()).ratio()))
        a_qs = WordAlias.objects.select_related('word__category').filter(
            word__category__name__iexact='keyword', alias__icontains=token
        )[:300]
        for a in a_qs:
            s = (a.alias or '').strip()
            if s:
                cands.append((s, difflib.SequenceMatcher(None, token.lower(), s.lower()).ratio()))
        if not cands:
            return None
        cands.sort(key=lambda x: (-x[1], -len(x[0]), x[0].lower()))
        best = cands[0]
        return best if best[1] >= 0.6 else None

    # 仅对未被删除的 token 做关键词追加，降低噪声
    tokens_for_keywords = [t for t in uniq_tokens if t not in set(removed_tokens)]
    if 'keyword' in req_categories:
        for tk in tokens_for_keywords:
            m = _best_keyword_for_token(tk)
            if not m:
                continue
            best_phrase = m[0]
            if best_phrase and best_phrase.lower() not in [x.lower() for x in appended_keywords]:
                # 末尾以空格追加一次
                cleaned = (cleaned.rstrip() + (' ' if cleaned and not cleaned.endswith(' ') else '') + best_phrase)
                appended_keywords.append(best_phrase)

    # 新增：在程序末尾确保 hotwords 中每个词都包含在 cleaned 中
    if hotwords:
        for w in [x for x in hotwords.split(' ') if x.strip()]:
            # 用词边界判断是否已存在，避免子串误判
            if not re.search(rf"\b{re.escape(w)}\b", cleaned, flags=re.IGNORECASE):
                cleaned = (cleaned.rstrip() + (' ' if cleaned and not cleaned.endswith(' ') else '') + w)

    # 去重与排序清理
    removed_tokens = sorted(set(removed_tokens), key=lambda s: (-len(s), s.lower()))
    for c in list(removed_by_category.keys()):
        removed_by_category[c] = sorted(set(removed_by_category[c]), key=lambda s: (-len(s), s.lower()))

    # 修复：移除重复的智能长度裁剪尾部片段，避免SyntaxError

    # 智能长度裁剪，最多255字符
    cleaned = cleaned.strip()
    if len(cleaned) > 255:
        cleaned = cleaned[:255].rstrip()

    return JsonResponse({
        "cleaned_text": cleaned,
        "removed_tokens": removed_tokens,
        "removed_by_category": removed_by_category,
        "appended_keywords": appended_keywords,
    })


