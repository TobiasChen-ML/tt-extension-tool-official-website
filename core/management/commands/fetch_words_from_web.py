"""
Django管理命令：从公开词库抓取并导入违禁词/品牌词
运行命令: python manage.py fetch_words_from_web --limit 1000
"""
import json
import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Category, Word, WordAlias
import re


class Command(BaseCommand):
    help = '从公开词库抓取并导入违禁词/品牌词'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=1000,
            help='限制导入的词汇数量上限（默认1000）'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='强制重新抓取，即使词汇已存在'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        force = options['force']
        
        self.stdout.write(f'开始抓取词汇，限制数量：{limit}')
        
        # 统计开始前的数量
        initial_word_count = Word.objects.count()
        initial_alias_count = WordAlias.objects.count()
        
        # 确保分类存在
        forbidden_category, _ = Category.objects.get_or_create(name='forbidden')
        brand_category, _ = Category.objects.get_or_create(name='brand')
        
        imported_count = 0
        
        try:
            # 1. 抓取 LDNOOBW 英文脏话词库（forbidden类别）
            if imported_count < limit:
                ldnoobw_count = self._fetch_ldnoobw_words(forbidden_category, limit - imported_count, force)
                imported_count += ldnoobw_count
                self.stdout.write(f'LDNOOBW 词库导入 {ldnoobw_count} 个词汇')
            
            # 2. 抓取 zacanger/profane-words（forbidden类别）
            if imported_count < limit:
                zacanger_count = self._fetch_zacanger_words(forbidden_category, limit - imported_count, force)
                imported_count += zacanger_count
                self.stdout.write(f'zacanger 词库导入 {zacanger_count} 个词汇')
            
            # 3. 抓取 dsojevic/profanity-list（forbidden类别）
            if imported_count < limit:
                dsojevic_count = self._fetch_dsojevic_words(forbidden_category, limit - imported_count, force)
                imported_count += dsojevic_count
                self.stdout.write(f'dsojevic 词库导入 {dsojevic_count} 个词汇')
            
            # 4. 抓取汽车品牌词库（brand类别）
            if imported_count < limit:
                brand_count = self._fetch_car_brands(brand_category, limit - imported_count, force)
                imported_count += brand_count
                self.stdout.write(f'汽车品牌词库导入 {brand_count} 个词汇')
            
        except Exception as e:
            raise CommandError(f'抓取过程中出现错误: {str(e)}')
        
        # 统计结果
        final_word_count = Word.objects.count()
        final_alias_count = WordAlias.objects.count()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'抓取完成！\n'
                f'本次导入词汇: {imported_count}\n'
                f'词汇总数: {initial_word_count} -> {final_word_count} (+{final_word_count - initial_word_count})\n'
                f'别名总数: {initial_alias_count} -> {final_alias_count} (+{final_alias_count - initial_alias_count})'
            )
        )

    def _fetch_ldnoobw_words(self, category, limit, force):
        """抓取 LDNOOBW 英文脏话词库"""
        url = 'https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/en'
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            words = [word.strip().lower() for word in response.text.split('\n') if word.strip()]
            return self._import_words(words[:limit], category, force)
            
        except requests.RequestException as e:
            self.stdout.write(self.style.WARNING(f'LDNOOBW 词库抓取失败: {str(e)}'))
            return 0

    def _fetch_zacanger_words(self, category, limit, force):
        """抓取 zacanger/profane-words 词库"""
        url = 'https://raw.githubusercontent.com/zacanger/profane-words/master/words.json'
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            words_data = response.json()
            # words.json 应该是一个数组
            if isinstance(words_data, list):
                words = [word.strip().lower() for word in words_data if word.strip()]
            else:
                self.stdout.write(self.style.WARNING('zacanger 词库格式不符合预期'))
                return 0
                
            return self._import_words(words[:limit], category, force)
            
        except (requests.RequestException, json.JSONDecodeError) as e:
            self.stdout.write(self.style.WARNING(f'zacanger 词库抓取失败: {str(e)}'))
            return 0

    def _fetch_dsojevic_words(self, category, limit, force):
        """抓取 dsojevic/profanity-list 词库"""
        url = 'https://raw.githubusercontent.com/dsojevic/profanity-list/master/en.json'
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            words_data = response.json()
            words = []
            
            # 解析 dsojevic 的 JSON 格式
            for item in words_data:
                if isinstance(item, dict) and 'match' in item:
                    match_text = item['match']
                    # 处理多个匹配项（用|分隔）
                    if '|' in match_text:
                        words.extend([w.strip().lower() for w in match_text.split('|')])
                    else:
                        # 移除通配符*，只保留基础词汇
                        clean_word = re.sub(r'\*+', '', match_text).strip().lower()
                        if clean_word and len(clean_word) > 1:  # 排除太短的词
                            words.append(clean_word)
                            
            return self._import_words(words[:limit], category, force)
            
        except (requests.RequestException, json.JSONDecodeError) as e:
            self.stdout.write(self.style.WARNING(f'dsojevic 词库抓取失败: {str(e)}'))
            return 0

    def _fetch_car_brands(self, category, limit, force):
        """抓取汽车品牌词库"""
        url = 'https://raw.githubusercontent.com/matthlavacka/car-list/master/car-list.json'
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            cars_data = response.json()
            brands = set()
            
            # 提取品牌名称
            for car in cars_data:
                if isinstance(car, dict) and 'brand' in car:
                    brand = car['brand'].strip().lower()
                    if brand and len(brand) > 1:
                        brands.add(brand)
            
            return self._import_words(list(brands)[:limit], category, force)
            
        except (requests.RequestException, json.JSONDecodeError) as e:
            self.stdout.write(self.style.WARNING(f'汽车品牌词库抓取失败: {str(e)}'))
            return 0

    def _import_words(self, words, category, force):
        """批量导入词汇并生成别名"""
        imported_count = 0
        
        with transaction.atomic():
            for word_text in words:
                # 清理和验证词汇
                clean_word = self._clean_word(word_text)
                if not clean_word:
                    continue
                
                # 检查是否已存在
                if not force and Word.objects.filter(word=clean_word).exists():
                    continue
                
                try:
                    # 创建或获取词汇
                    word_obj, created = Word.objects.get_or_create(
                        word=clean_word,
                        defaults={'category': category}
                    )
                    
                    if created or force:
                        # 生成别名
                        aliases = self._gen_aliases(clean_word)
                        for alias in aliases:
                            WordAlias.objects.get_or_create(
                                word=word_obj,
                                alias=alias
                            )
                        
                        imported_count += 1
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'导入词汇 "{clean_word}" 失败: {str(e)}')
                    )
                    continue
        
        return imported_count

    def _clean_word(self, word):
        """清理和验证词汇"""
        if not word:
            return None
        
        # 转换为小写并移除首尾空格
        clean = word.strip().lower()
        
        # 只保留字母、数字和常见符号
        clean = re.sub(r'[^\w\-\'\s]', '', clean)
        
        # 移除多余空格
        clean = re.sub(r'\s+', ' ', clean).strip()
        
        # 验证长度和内容
        if len(clean) < 2 or len(clean) > 50:
            return None
        
        # 排除纯数字
        if clean.isdigit():
            return None
        
        return clean

    def _gen_aliases(self, word):
        """生成词汇别名（复用 seed_words.py 中的逻辑）"""
        aliases = set()
        
        # 字母替换映射
        replacements = {
            'a': ['@', '4'],
            'e': ['3'],
            'i': ['1', '!'],
            'o': ['0'],
            's': ['$', '5'],
            't': ['7'],
            'g': ['9'],
        }
        
        # 生成基础别名
        aliases.add(word)
        
        # 首字母大写
        aliases.add(word.capitalize())
        
        # 全大写
        aliases.add(word.upper())
        
        # 字母替换变体
        for original, replacements_list in replacements.items():
            if original in word:
                for replacement in replacements_list:
                    alias = word.replace(original, replacement)
                    aliases.add(alias)
                    aliases.add(alias.capitalize())
                    aliases.add(alias.upper())
        
        # 添加分隔符变体
        if len(word) > 3:
            # 添加连字符
            mid = len(word) // 2
            aliases.add(word[:mid] + '-' + word[mid:])
            # 添加空格
            aliases.add(word[:mid] + ' ' + word[mid:])
        
        # 移除原词本身
        aliases.discard(word)
        
        # 限制别名数量，避免过多
        return list(aliases)[:10]