from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Category, Word, WordAlias
import os
import csv
import re

class Command(BaseCommand):
    help = "批量导入指定类别(默认 keyword)的词条，可从 --words 或 --file 读取，并可生成别名"

    def add_arguments(self, parser):
        parser.add_argument(
            '--category',
            type=str,
            default='keyword',
            help='导入到的分类名称，默认 keyword'
        )
        parser.add_argument(
            '--words',
            type=str,
            default='',
            help='以逗号、分号或换行分隔的一组词条字符串'
        )
        parser.add_argument(
            '--file',
            type=str,
            default='',
            help='文件路径：支持 .txt(每行一个词)、.csv(存在列名 word)'
        )
        parser.add_argument(
            '--severity',
            type=int,
            default=1,
            help='严重程度：1/2/3，默认 1'
        )
        parser.add_argument(
            '--aliases',
            action='store_true',
            help='生成词条别名(最多10个变体)'
        )
        parser.add_argument(
            '--force-update',
            action='store_true',
            help='当词已存在时，更新其 category/severity'
        )

    def handle(self, *args, **options):
        category_name = (options.get('category') or 'keyword').strip()
        severity = int(options.get('severity') or 1)
        severity = 1 if severity not in (1,2,3) else severity
        words_str = options.get('words') or ''
        file_path = options.get('file') or ''
        gen_aliases_flag = bool(options.get('aliases'))
        force_update = bool(options.get('force-update'))

        # 收集词列表
        words = []
        if words_str:
            # 支持逗号/分号/换行分隔
            parts = re.split(r'[\n,;]+', words_str)
            words.extend([p.strip() for p in parts if p.strip()])

        if file_path:
            if not os.path.isfile(file_path):
                raise CommandError(f'文件不存在: {file_path}')
            ext = os.path.splitext(file_path)[1].lower()
            try:
                if ext == '.csv':
                    with open(file_path, 'r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        # 优先列名 word，其次第一列
                        for row in reader:
                            if 'word' in row and row['word']:
                                w = row['word'].strip()
                            else:
                                # 取第一列
                                first_key = next(iter(row.keys()))
                                w = (row.get(first_key) or '').strip()
                            if w:
                                words.append(w)
                else:
                    # .txt / 其他：按行读取
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            w = line.strip()
                            if not w:
                                continue
                            # 如果一行有逗号或分号，拆分
                            for part in re.split(r'[\n,;]+', w):
                                p = part.strip()
                                if p:
                                    words.append(p)
            except Exception as e:
                raise CommandError(f'读取文件失败: {e}')

        # 去重+清理
        cleaned = []
        seen = set()
        for w in words:
            c = self._clean_word(w)
            if not c:
                continue
            if c.lower() in seen:
                continue
            seen.add(c.lower())
            cleaned.append(c)

        if not cleaned:
            raise CommandError('未检测到有效词条，请通过 --words 或 --file 提供内容')

        # 确保分类存在
        category_obj, _ = Category.objects.get_or_create(name=category_name)

        created_count = 0
        updated_count = 0
        alias_count = 0
        skipped_count = 0

        with transaction.atomic():
            for w in cleaned:
                obj, created = Word.objects.get_or_create(
                    word=w,
                    defaults={'category': category_obj, 'severity': severity, 'is_active': True}
                )
                if created:
                    created_count += 1
                    # 生成别名
                    if gen_aliases_flag:
                        for alias in self._gen_aliases(w):
                            try:
                                _, alias_created = WordAlias.objects.get_or_create(word=obj, alias=alias)
                                if alias_created:
                                    alias_count += 1
                            except Exception:
                                # 忽略别名重复/长度异常
                                pass
                else:
                    if force_update:
                        changed = False
                        if obj.category_id != category_obj.id:
                            obj.category = category_obj
                            changed = True
                        if obj.severity != severity:
                            obj.severity = severity
                            changed = True
                        if changed:
                            obj.save(update_fields=['category', 'severity'])
                            updated_count += 1
                        # 已存在也可补充别名
                        if gen_aliases_flag:
                            for alias in self._gen_aliases(w):
                                try:
                                    WordAlias.objects.get_or_create(word=obj, alias=alias)
                                    alias_count += 1
                                except Exception:
                                    pass
                    else:
                        skipped_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"导入完成：分类='{category_name}', 新增 {created_count}, 更新 {updated_count}, 跳过 {skipped_count}, 新增别名 {alias_count}"
        ))

    def _clean_word(self, word: str):
        if not word:
            return None
        s = str(word).strip()
        # 去掉两端引号
        s = re.sub(r'^[\"\']|[\"\']$', '', s)
        # 移除不可见字符
        s = re.sub(r'[\u0000-\u001f\u007f]', '', s)
        # 合并多空格
        s = re.sub(r'\s+', ' ', s)
        if len(s) < 1 or len(s) > 200:
            return None
        return s

    def _gen_aliases(self, base: str):
        s = (base or '').strip()
        if not s:
            return []
        variants = set()
        lower = s.lower()
        upper = s.upper()
        title = s.title()
        variants.update([lower, upper, title])
        # 去空格/连字符/撇号
        compact = re.sub(r"[\s\-']+", "", s)
        if compact and compact.lower() != lower:
            variants.add(compact)
        # 互换空格/连字符
        hyphen_to_space = s.replace('-', ' ')
        space_to_hyphen = re.sub(r"\s+", '-', s)
        variants.update([hyphen_to_space, space_to_hyphen])
        # 简单复数
        if re.search(r"[A-Za-z]$", s):
            if re.search(r"[^aeiou]y$", s, re.IGNORECASE):
                variants.add(re.sub(r"y$", "ies", s, flags=re.IGNORECASE))
            elif not s.lower().endswith('s'):
                variants.add(s + 's')
            else:
                variants.add(s + 'es')
        # leet 变体
        leet = lower.translate(str.maketrans({'a':'4','e':'3','i':'1','o':'0','s':'5','t':'7'}))
        variants.add(leet)
        # 去除原词(case-insensitive)
        norm_orig = s.lower()
        variants = {v for v in variants if v and v.lower() != norm_orig}
        # 截断长度并限制数量
        trimmed = [v[:200] for v in variants]
        return trimmed[:10]
