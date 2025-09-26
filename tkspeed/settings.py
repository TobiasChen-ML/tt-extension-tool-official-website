import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-insecure-key')
DEBUG = os.getenv('DJANGO_DEBUG', '1') == '1'
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core.apps.CoreConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'tkspeed.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'tkspeed.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = False

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'

# Aliyun SMS settings (from env)
ALIYUN_SMS_SIGN_NAME = os.getenv('ALIYUN_SMS_SIGN_NAME', 'Vectorizer')
ALIYUN_SMS_TEMPLATE_CODE = os.getenv('ALIYUN_SMS_TEMPLATE_CODE', 'SMS_307081209')

# WeChat Pay settings (from env)
WECHAT_PAY_APP_ID = os.getenv('WECHAT_PAY_APP_ID', '')
WECHAT_PAY_MCH_ID = os.getenv('WECHAT_PAY_MCH_ID', '')
WECHAT_PAY_API_KEY = os.getenv('WECHAT_PAY_API_KEY', '')
WECHAT_PAY_NOTIFY_URL = os.getenv('WECHAT_PAY_NOTIFY_URL', '')
CREATE_IP = os.getenv('CREATE_IP', '127.0.0.1')
UFDODER_URL = os.getenv('UFDODER_URL', 'https://api.mch.weixin.qq.com/pay/unifiedorder')
DOMAIN_NAME = os.getenv('DOMAIN_NAME', 'http://localhost:8000')

# Session settings for long-lived login
SESSION_COOKIE_AGE = int(os.getenv('SESSION_COOKIE_AGE', str(60 * 60 * 24 * 90)))  # 90 天
SESSION_SAVE_EVERY_REQUEST = True  # 每次请求刷新过期时间
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # 关闭浏览器不退出登录