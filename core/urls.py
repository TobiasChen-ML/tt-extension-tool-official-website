from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('send_code/', views.send_code, name='send_code'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    path('recharge/', views.recharge, name='recharge'),
    path('wechat/notify/', views.wechat_notify, name='wechat_notify'),

    # 词库与用户信息库 API（不做删除）
    path('api/sensitive-words/', views.sensitive_words, name='sensitive_words'),
    path('api/brand-words/', views.brand_words, name='brand_words'),
    path('api/forbidden-words/', views.forbidden_words, name='forbidden_words'),
    path('api/keywords/', views.keywords, name='keywords'),
    path('api/user-infos/', views.user_infos, name='user_infos'),

    # 新增：标准化词库 API
    path('api/categories/', views.categories, name='categories'),
    path('api/words/', views.words, name='words'),
    path('api/word-aliases/', views.word_aliases, name='word_aliases'),
    path('api/word-logs/', views.word_logs, name='word_logs'),
]