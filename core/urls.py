from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('send_code/', views.send_code, name='send_code'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('recharge/', views.recharge, name='recharge'),
    path('wechat/notify/', views.wechat_notify, name='wechat_notify'),

    # 标准化词库 APIs
    path('api/categories/', views.categories, name='categories'),
    path('api/words/', views.words, name='words'),
    path('api/word-aliases/', views.word_aliases, name='word_aliases'),
    path('api/words/logs', views.word_logs),
    path('api/words/rm_forbiden', views.rm_forbiden),
    path('api/words/rm_brand', views.rm_brand),
    path('api/words/clean_multi', views.clean_text_multi),
    path('api/analyze-text', views.analyze_text, name='analyze_text'),

    # 用户信息
    path('api/user-infos/', views.user_infos, name='user_infos'),
    path('api/image/is_watermark/', views.image_is_watermark, name='image_is_watermark'),
]