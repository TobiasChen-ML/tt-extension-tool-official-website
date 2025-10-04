from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('send_code/', views.send_code, name='send_code'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('recharge/', views.recharge, name='recharge'),
    path('privacy/', views.privacy, name='privacy'),

    # 标准化词库 APIs
    path('api/categories/', views.categories, name='categories'),
    path('api/words/', views.words, name='words'),
    path('api/word-aliases/', views.word_aliases, name='word_aliases'),
    path('api/words/logs', views.word_logs),
    path('api/words/rm_forbiden', views.rm_forbiden),
    path('api/words/rm_brand', views.rm_brand),
    path('api/words/clean_multi', views.clean_text_multi),
    # 新增：批量商品词分类与提取
    path('api/words/clean_multi/batch', views.clean_text_multi_batch),



    path('api/analyze-text', views.analyze_text, name='analyze_text'),

    # 新增：积分调整接口
    path('api/points/adjust', views.adjust_points, name='adjust_points'),

    # 用户信息
    path('api/user-infos/', views.user_infos, name='user_infos'),
    path('api/image/is_watermark/', views.image_is_watermark, name='image_is_watermark'),
    path('super/settings/', views.super_settings, name='super_settings'),

    # 新增：商品词分类与提取
    path('api/words/classification', views.words_classification),

    # 新增：建议收集接口
    path('api/suggestion', views.suggestion),

    # 新增：客户有效性校验接口
    path('api/is_valid_customer', views.is_valid_customer),

    # 新增：识别图片是否带品牌
    path('api/image/has_brand/', views.image_has_brand, name='image_has_brand'),
]