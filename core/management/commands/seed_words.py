from django.core.management.base import BaseCommand
from core.models import Category, Word, WordAlias, WordLog
import re

class Command(BaseCommand):
    help = "Reset and seed standardized word library with English categories and TikTok-related terms"

    def handle(self, *args, **options):
        # 1) Purge existing data
        self.stdout.write(self.style.WARNING("Resetting existing word library data..."))
        WordAlias.objects.all().delete()
        WordLog.objects.all().delete()
        Word.objects.all().delete()
        Category.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("All previous Categories, Words, Aliases, Logs deleted."))

        # 2) Define English categories with severities
        category_defs = {
            'forbidden': (3, 'Forbidden Claims'),
            'illegal_crime': (3, 'Illegal / Crime'),
            'violence_extremism': (3, 'Violence / Extremism'),
            'adult_sexual': (2, 'Adult / Sexual Content'),
            'hate_harassment': (2, 'Hate Speech / Harassment'),
            'brand': (1, 'Brand Words'),
            'trending': (1, 'Trending / Buzzwords'),
        }
        cat_objs = {}
        for name, (severity, display) in category_defs.items():
            cat, _ = Category.objects.get_or_create(name=name, defaults={'description': display})
            if cat.description != display:
                cat.description = display
                cat.save(update_fields=['description'])
            cat_objs[name] = (cat, severity)
        self.stdout.write(self.style.SUCCESS("Categories ensured: " + ", ".join([f"{k}=>{cat_objs[k][0].description}" for k in category_defs.keys()])))

        # 3) Forbidden marketing/absolute claims (keep from previous seed)
        forbidden_terms = [
            'best','number one','no.1','top','leading','world-class','national','global','exclusive','only','unique','ultimate','perfect',
            'guaranteed','warranty','refund guaranteed','money-back guarantee','zero risk','official','certified','authority certified',
            'permanent','cure','no side effects','instant','immediate','fastest','first','unlimited','limitless','ever','all-time',
            'lowest price','cheapest','rock-bottom price','never before','unprecedented','once-in-a-lifetime','the most','the best',
            'superior','supreme','premium','luxury','elite','state-of-the-art','cutting-edge','high-end','ultimate quality',
        ]

        # 4) Illegal / Crime (user-provided, two batches merged)
        illegal_crime_terms = [
            # batch 1
            'drugs','dealer','heroin','marijuana','meth','ecstasy','needle','lab','gambling','casino','bet',
            'bookmaker','money laundering','counterfeit','scam','phishing','hacker','malware','trojan',
            'fake passport','fake ID','smuggling','trafficking','gun','firearm','pistol','rifle','bomb',
            'explosive','homemade bomb','dark web','underground bank','organ trade','human trafficking',
            'assassination','mafia','gang','terrorist','attack','smuggle car','illegal arms',
            # batch 2
            'cocaine','crack','opium','hashish','LSD','ketamine','shrooms','cartel','money mule',
            'loan shark','illegal betting','poker ring','pyramid scheme','darknet','fake license',
            'counterfeit money','smurfing','identity theft','ransomware','spyware','keylogger',
            'exploit kit','carding','skimmer','fake diploma','stolen credit card','arms trade',
            'illegal auction','cybercrime','blackmail','extortion','bribery','hitman','insider trading',
            'tax evasion','underground market','contract killing','street gang','mob boss','crime ring',
        ]

        # 5) Violence / Extremism (two batches merged)
        violence_extremism_terms = [
            # batch 1
            'murder','suicide','cut wrist','jump off','hanging','burning alive','fight','gang fight',
            'blood','stabbing','dismember','beating','domestic violence','rape','sexual assault',
            'kidnap','robbery','massacre','terrorism','extremist','bomb attack','execute','death penalty',
            'gunfight','violent video','gore','torture','jihad','insurgent','violent protest','riot','kill',
            # batch 2
            'shooting','drive-by','sniper','execute hostage','burning car','knife fight','throat slit',
            'bloodbath','car bomb','acid attack','violent riot','lynching','extremist group',
            'beheading','war crime','genocide','hate rally','violent uprising','insurrection',
            'Molotov cocktail','riot gear','ambush','guerilla','assault rifle','violent strike',
            'school shooting','hate march','terror cell','insurgency','civil war',
        ]

        # 6) Adult / Sexual Content (two batches merged)
        adult_sexual_terms = [
            # batch 1
            'porn','xxx','sex video','adult film','hookup','naked','nude','strip','blowjob','anal','fetish',
            'escort','prostitute','hentai','erotic manga','camgirl','camshow','bdsm','kink','bondage',
            'roleplay','mistress','sex toy','dildo','vibrator','condom','threesome','gangbang','incest',
            'teen porn','milf','cougar','swinger','dirty talk','erotic novel','sexual chat','live sex',
            'amateur porn','erotic massage','erotic story','xxx site','hentai comic',
            # batch 2
            'sex tape','leaked video','cam site','erotic art','erotic photo','strip club','sex worker',
            'escort service','erotic cosplay','bondage gear','latex fetish','pegging','foot fetish',
            'role play','swinger party','amateur video','porn site','porn star','NSFW','xxx chat',
            'hooker','slut','dirty pics','wet dream','sexting','nude selfie','topless','sex blog',
            'cam model','webcam show','erotic dance','private show','red light','adult shop',
            'kamasutra','oral sex','hentai site','porn gif','dirty cam','sex stories','sex comics',
        ]

        # 7) Hate Speech / Harassment (two batches merged)
        hate_harassment_terms = [
            # batch 1
            'racist','n-word','faggot','tranny','hate','nazi','fascist','terrorist slur','sexist',
            'misogynist','misandrist','pig','loser','dumbass','retard','idiot','moron','trash','garbage',
            'worthless','useless','scum','parasite','piggy','bitch','whore','bastard','jerk','ugly','clown',
            'disgusting','creep',
            # batch 2
            'bigot','racial slur','monkey','ape insult','kike','jew-hater','islamophobe','homophobe',
            'transphobe','gay-bash','bully','cyberbully','troll','flame','insult','abusive',
            'offensive','toxic','degenerate','lowlife','bottomfeeder','pigface','dumb cow',
            'hoe','slut-shaming','fat-shaming','ugly freak','weirdo','psycho','lunatic','stalker',
        ]

        # 8) Brand words (merge with previous list and user-provided additions)
        brand_terms = [
            # tech & internet (existing)
            'TikTok','ByteDance','Apple','Google','Microsoft','Amazon','Meta','Facebook','Instagram','WhatsApp','YouTube','Snapchat','Twitter','X',
            'WeChat','QQ','Baidu','Alibaba','Taobao','Tmall','JD','Pinduoduo','Tencent','Netflix','Disney','Hulu','HBO',
            # sportswear
            'Nike','Adidas','Puma','New Balance','Under Armour','Lululemon','Converse','Skechers',
            # luxury & fashion
            'Gucci','Prada','Louis Vuitton','LV','Chanel','Dior','Hermes','YSL','Burberry','Fendi','Versace','Balenciaga','Moncler','Armani','Valentino',
            # automotive
            'Toyota','Honda','Nissan','Lexus','Mazda','Subaru','Mitsubishi','Hyundai','Kia','GM','Chevrolet','Ford','Tesla','Volkswagen','Audi',
            'Porsche','Bentley','Bugatti','Lamborghini','Ferrari','Maserati','BMW','Mercedes-Benz','MINI','Jaguar','Land Rover','Volvo',
            # appliances & retail & F&B
            'Haier','Midea','Gree','Hisense','TCL','Kelon','Robam','Fotile','Walmart','Carrefour','Costco','IKEA',
            'Starbucks','McDonald\'s','KFC','Burger King','Subway','Pizza Hut','Domino\'s','Pepsi','Coca-Cola',
            # user-provided brand lists
            'iPhone','Samsung','Huawei','Xiaomi','Douyin','YouTube','Facebook','Instagram','Twitter',
            'WhatsApp','Telegram','WeChat','Microsoft','Google','Amazon','Netflix','Tesla','Nike',
            'Sony','Playstation','Xbox','Nintendo','LinkedIn','TikTok Shop','Shein','Zara','Adidas','Puma',
            'CocaCola','Pepsi','Starbucks','McDonalds','KFC','BurgerKing','Uber','Lyft','Airbnb','Spotify',
        ]

        # 9) Trending / Buzzwords (two batches merged)
        trending_terms = [
            # batch 1
            'slay','lit','savage','vibes','no cap','drip','sus','yeet','bet','flex','ghosted','stan',
            'simp','cringe','mood','glow up','ratio','cancel','viral','trending','meme','fyp','POV',
            'challenge','duet','collab','rewatch','binge','fan edit','cosplay','unboxing','haul',
            'behind the scenes','storytime','ASMR','aesthetic','OOTD','GRWM','influencer','reaction','prank',
            # batch 2
            'stan army','fan cam','thirst trap','viral dance','challenge trend','duet chain',
            'reaction video','parody','mashup','POV skit','cosplay trend','storytime drama',
            'ship','fanfic','soft launch','hard launch','main character','delulu','agenda',
            'chronically online','girl dinner','boy math','girl math','alpha male','sigma male',
            'beta male','glowdown','NPC trend','cap or no cap','green flag','red flag',
            'gatekeep','gaslight','girlboss','slaps','core','aesthetic edit','mood board',
            'viral sound','sped up song','slow reverb',
        ]

        # Build batches with high severity first so duplicates prefer stricter categories
        batches = [
            ('forbidden', forbidden_terms),
            ('illegal_crime', illegal_crime_terms),
            ('violence_extremism', violence_extremism_terms),
            ('adult_sexual', adult_sexual_terms),
            ('hate_harassment', hate_harassment_terms),
            ('brand', brand_terms),
            ('trending', trending_terms),
        ]

        # Helper: generate alias variants for a base word
        def gen_aliases(base: str):
            s = (base or '').strip()
            if not s:
                return set()
            variants = set()
            lower = s.lower()
            upper = s.upper()
            title = s.title()
            variants.update([lower, upper, title])
            # remove spaces, hyphens, apostrophes
            compact = re.sub(r"[\s\-']+", "", s)
            if compact and compact.lower() != lower:
                variants.add(compact)
            # swap hyphen/space
            hyphen_to_space = s.replace('-', ' ')
            space_to_hyphen = re.sub(r"\s+", '-', s)
            variants.update([hyphen_to_space, space_to_hyphen])
            # simple pluralization
            if re.search(r"[A-Za-z]$", s):
                if re.search(r"[^aeiou]y$", s, re.IGNORECASE):
                    variants.add(re.sub(r"y$", "ies", s, flags=re.IGNORECASE))
                elif not s.lower().endswith('s'):
                    variants.add(s + 's')
                else:
                    variants.add(s + 'es')
            # leet speak
            leet = lower.translate(str.maketrans({'a':'4','e':'3','i':'1','o':'0','s':'5','t':'7'}))
            variants.add(leet)
            # cleanup: dedupe and remove original case-insensitively
            norm_orig = s.lower()
            variants = {v for v in variants if v and v.lower() != norm_orig}
            # trim
            variants = {v[:200] for v in variants}
            return variants

        # Helper for progress
        total_created = 0
        total_skipped_existing = 0
        total_aliases = 0

        for cat_name, words in batches:
            cat, sev = cat_objs[cat_name]
            created_count = 0
            skipped_count = 0
            for w in words:
                w = (w or '').strip()
                if not w:
                    continue
                obj, created = Word.objects.get_or_create(
                    word=w,
                    defaults={'category': cat, 'severity': sev, 'is_active': True}
                )
                if created:
                    total_created += 1
                    created_count += 1
                    # generate aliases for new words
                    alias_created_count = 0
                    for alias in gen_aliases(w):
                        try:
                            _, alias_created = WordAlias.objects.get_or_create(word=obj, alias=alias)
                            if alias_created:
                                alias_created_count += 1
                                total_aliases += 1
                        except Exception:
                            pass
                else:
                    skipped_count += 1
            self.stdout.write(self.style.SUCCESS(
                f"Seeded {len(words)} words for category '{cat_name}' (created {created_count}, existing {skipped_count})"
            ))
            total_skipped_existing += skipped_count

        self.stdout.write(self.style.SUCCESS(
            f"Total newly created words: {total_created}; existing encountered: {total_skipped_existing}; total aliases: {total_aliases}"
        ))