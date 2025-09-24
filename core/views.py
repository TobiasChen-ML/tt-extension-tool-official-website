from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from .models import Profile, Product, Order, UserInfo, Category, Word, WordAlias, WordLog, StoreKey
import random
import string
import json
import os
import difflib
import requests
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
    # 新增：当前用户的店铺密钥列表（只读展示）
    store_keys = StoreKey.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'dashboard.html', {
        'profile': profile,
        'orders': orders,
        'products': products,
        'store_keys': store_keys,
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
      "categories": ["forbidden","brand"],  # 可选，默认同时处理 forbidden 与 brand
      "keywords": ["...", "..."]             # 可选，按需求追加到文本末尾
    }

    新逻辑：
    1) 获取到 text，先分词；
    2) 每个 token 去模糊搜索违禁词、品牌词（词条与别名），对模糊搜索到的候选，用 DeepSeek API 判断候选词与该 token 是否为同义/等价；若是，则将该 token 在原文本中替换为 ''；
    3) 关于 keywords：对每个关键词进行模糊搜索，选出最相关的一个词（若存在），将其追加到文本末尾；否则跳过。
    返回：cleaned_text、removed_tokens（被删除的分词）、removed_by_category（按分类聚合）、appended_keywords（追加到末尾的词列表）。
    """
    if request.method != 'POST':
        return JsonResponse({'code': 405, 'msg': 'Method Not Allowed'})

    data = parse_json(request)
    text = (data.get('text') or '')
    if not text.strip():
        return JsonResponse({'code': 400, 'msg': 'text不能为空'})

    # 解析参数
    req_categories = data.get('categories') or ['forbidden', 'brand']
    req_categories = [str(c).strip().lower() for c in req_categories if str(c).strip()]
    keywords = data.get('keywords') or []
    keywords = [str(k).strip() for k in keywords if str(k).strip()]

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
            if _is_synonym(tk, phrase):
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

    # 关键词：模糊搜索最相关词并追加到文本末尾
    appended_keywords = []
    def _best_match_for_keyword(kw: str):
        cands = []
        # 全库按子串匹配（词条+别名），不限定分类
        w_qs = Word.objects.select_related('category').filter(is_active=True, word__icontains=kw)[:300]
        for w in w_qs:
            s = (w.word or '').strip()
            if s:
                cands.append((s, difflib.SequenceMatcher(None, kw.lower(), s.lower()).ratio()))
        a_qs = WordAlias.objects.select_related('word__category').filter(alias__icontains=kw)[:300]
        for a in a_qs:
            s = (a.alias or '').strip()
            if s:
                cands.append((s, difflib.SequenceMatcher(None, kw.lower(), s.lower()).ratio()))
        if not cands:
            return None
        cands.sort(key=lambda x: (-x[1], -len(x[0]), x[0].lower()))
        best = cands[0]
        return best if best[1] >= 0.6 else None

    for kw in keywords:
        m = _best_match_for_keyword(kw)
        if not m:
            continue
        best_phrase = m[0]
        # 末尾以空格追加一次
        if best_phrase:
            cleaned = (cleaned.rstrip() + (' ' if cleaned and not cleaned.endswith(' ') else '') + best_phrase)
            appended_keywords.append(best_phrase)

    # 去重与排序清理
    removed_tokens = sorted(set(removed_tokens), key=lambda s: (-len(s), s.lower()))
    for c in list(removed_by_category.keys()):
        removed_by_category[c] = sorted(set(removed_by_category[c]), key=lambda s: (-len(s), s.lower()))
    print(f'cleaned_text: {cleaned}')
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


@csrf_exempt
def wechat_notify(request):
    # 简化实现：直接返回 SUCCESS，生产环境请验证签名并更新订单状态
    return HttpResponse("<xml><return_code>SUCCESS</return_code><return_msg>OK</return_msg></xml>", content_type='application/xml')