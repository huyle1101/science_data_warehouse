import scrapy
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
from science_dwh.items import sofl_item
import os
import re

OUTPUT_DIR = 'f:/science_data_warehouse_repo/output/hust/sofl/raw_data'
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'sofl.jsonl')

LOG_DIR = 'f:/science_data_warehouse_repo/output/hust/sofl/logs'
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f'sofl_{timestamp}.log')


class SoflSpider(scrapy.Spider):
    name = "sofl_spider"
    allowed_domains = ["sofl.hust.edu.vn"]

    DANH_MUC_CANBO_URLS = [
        ("Văn phòng Khoa",                                     "https://sofl.hust.edu.vn/danh-muc-can-bo6"),
        ("Bộ môn Tiếng Anh Chuyên nghiệp",                    "https://sofl.hust.edu.vn/danh-muc-can-bo"),
        ("Bộ môn Tiếng Anh Cơ sở",                            "https://sofl.hust.edu.vn/danh-muc-can-bo1"),
        ("Bộ môn Tiếng Anh Kỹ thuật",                         "https://sofl.hust.edu.vn/danh-muc-can-bo2"),
        ("Bộ môn Lý thuyết tiếng và Văn hóa Văn minh Anh-Mỹ", "https://sofl.hust.edu.vn/danh-muc-can-bo3"),
        ("Nhóm chuyên môn Tiếng Pháp",                        "https://sofl.hust.edu.vn/danh-muc-can-bo4"),
        ("Nhóm chuyên môn Ngôn ngữ và Văn hóa Á Đông",        "https://sofl.hust.edu.vn/danh-muc-can-bo5"),
        ("Nhóm chuyên môn Lý thuyết tiếng",                   "https://sofl.hust.edu.vn/danh-muc-can-bo7"),
    ]

    custom_settings = {
        "LOG_FILE": LOG_FILE,
        "LOG_LEVEL": "INFO",
        "ROBOTSTXT_OBEY": False,
        "FEEDS": {
            OUTPUT_FILE: {
                'format': 'jsonlines',
                "encoding": "utf8",
                "overwrite": False
            }
        },
        "CONCURRENT_REQUESTS": 32,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 16,
        "DOWNLOAD_DELAY": 1,
        "RANDOMIZED_DOWNLOAD_DELAY": True,
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 3,
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429, 403],
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 0.5,
        "AUTOTHROTTLE_MAX_DELAY": 60,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 16,
        "FEED_EXPORT_FIELDS": [
            "url", "avt_url", "ho_ten", "chuc_vu", "noi_lam_viec",
            "email", "tel", "gioi_thieu", "linh_vuc_nghien_cuu",
            "giang_day", "bai_bao_khoa_hoc", "sach", "de_tai_nghien_cuu",
            "html_text", "nhom_chuyen_mon", "dai_hoc", "don_vi_truc_thuoc",
            "thong_tin_khong_cong_bo", "is_extracted", "is_checked",
        ]
    }

    def start_requests(self):
        for nhom_ten, url in self.DANH_MUC_CANBO_URLS:
            yield scrapy.Request(url, callback=self.parse,
                                 cb_kwargs={'nhom_chuyen_mon': nhom_ten})

    def clean_html_text(self, html_text):
        if not html_text:
            return ""
        html_text = re.sub(r'<script\b[^>]*>[\s\S]*?<\/script>', '', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'<style\b[^>]*>[\s\S]*?<\/style>', '', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'<[^>]+>', '', html_text)
        html_text = re.sub(r'&nbsp;', ' ', html_text)
        html_text = re.sub(r'&[a-z]+;', '', html_text)
        html_text = re.sub(r'\n+', '\n', html_text)
        return '\n'.join([line.strip() for line in html_text.splitlines() if line.strip()])

    def parse(self, response, nhom_chuyen_mon):

        scholar_links = response.css(
            'a[href*="/-/asset_publisher/"][href*="/content/"]::attr(href)'
        ).getall()

        for url in scholar_links:
            yield response.follow(url, callback=self.parse_scholar,
                                  cb_kwargs={'nhom_chuyen_mon': nhom_chuyen_mon})

    def parse_scholar(self, response, nhom_chuyen_mon):
        item = sofl_item()
        item['url'] = response.url

        breadcrumb_last = response.css(
            'ol.breadcrumb li:last-child::text, '
            '.breadcrumb li:last-child::text, '
            '.portlet-breadcrumb li:last-child::text'
        ).get('').strip()

        if not breadcrumb_last:
            breadcrumb_last = response.css('h3::text').get('').strip()

        if ' - ' in breadcrumb_last:
            parts = breadcrumb_last.split(' - ', 1)
            item['ho_ten'] = parts[0].strip()
        else:
            item['ho_ten'] = breadcrumb_last


        content = (
            response.css('div.journal-content-article')
            or response.css('div.asset-content')
            or response.css('div.portlet-body div.entry-content')
            or response.css('div[class*="portlet-content"]')
        )
        if not content:
            content = response.css('div#main-content, div#content, body')


        avt_src = ''
        for img_src in response.css('img::attr(src)').getall():
            if 'img_id=' in img_src and 'VienNN-theme' not in img_src:
                avt_src = img_src
                break
        if not avt_src:
            for img_src in content.css('img::attr(src)').getall():
                if 'VienNN-theme' not in img_src and 'documents/195978/197681' not in img_src:
                    avt_src = img_src
                    break
        item['avt_url'] = response.urljoin(avt_src) if avt_src else ''


        chuc_vu_list = []
        noi_lam_viec = None
        email_val = None
        tel_val = None

        linh_vuc_nghien_cuu = []
        giang_day = []
        bai_bao_khoa_hoc = []
        de_tai_nghien_cuu = []
        sach = []
        gioi_thieu = []

        current_section = 'intro'

        elements = content.xpath('.//p | .//ul | .//ol | .//h3 | .//h4')

        for el in elements:
            tag = el.xpath('name()').get('').lower()
            css_class = el.xpath('@class').get('') or ''
            full_text = ' '.join(el.css('::text').getall()).strip()
            
            if not full_text and tag not in ['ul', 'ol']:
                continue

            heading_text = ""
            if 'vienNN_title' in css_class or 'vienNN_title1' in css_class or tag in ['h3', 'h4']:
                heading_text = full_text.lower()
            else:
                strong_text = ' '.join(el.css('strong::text, b::text').getall()).strip().lower()
                if strong_text and len(strong_text) < 100:
                    if any(kw in strong_text for kw in ['lĩnh vực', 'giảng dạy', 'giới thiệu', 'bài báo', 'đề tài', 'sách']):
                        heading_text = strong_text

            if heading_text:
                if 'giới thiệu' in heading_text:
                    current_section = 'gioi_thieu'
                    continue
                elif 'lĩnh vực' in heading_text:
                    current_section = 'linh_vuc'
                    continue
                elif 'giảng dạy' in heading_text:
                    current_section = 'giang_day'
                    continue
                elif 'bài báo' in heading_text:
                    current_section = 'bai_bao'
                    continue
                elif 'đề tài' in heading_text:
                    current_section = 'de_tai'
                    continue
                elif 'sách' in heading_text:
                    current_section = 'sach'
                    continue

            if current_section == 'intro':
                if tag == 'p' and full_text:
                    if re.search(r'[Nn]ơi\s*làm\s*việc|[Pp]\d+|[Pp]hòng', full_text, re.IGNORECASE):
                        if not noi_lam_viec: noi_lam_viec = full_text
                    elif re.search(r'Email[:\s]+([^\s<]+@[^\s<]+)', full_text, re.IGNORECASE):
                        m = re.search(r'Email[:\s]+([^\s<]+@[^\s<]+)', full_text, re.IGNORECASE)
                        if not email_val: email_val = m.group(1).strip().rstrip('.')
                    elif re.search(r'Tel|ĐT:|tel:', full_text, re.IGNORECASE):
                        m = re.search(r'[\d\s\-\+\.]{7,}', full_text)
                        if m and not tel_val: tel_val = m.group().strip()
                    elif 'vienNN_gachdo' not in css_class:
                        if full_text not in chuc_vu_list:
                            chuc_vu_list.append(full_text)

            elif current_section == 'gioi_thieu':
                if tag == 'p' and full_text:
                    if 'vienNN_gachdo' not in css_class and full_text not in gioi_thieu:
                        gioi_thieu.append(full_text)

            elif current_section in ['linh_vuc', 'giang_day', 'bai_bao', 'de_tai', 'sach']:
                if tag in ['ul', 'ol']:
                    for li in el.xpath('.//li'):
                        li_text = ' '.join(li.css('::text').getall()).strip()
                        if li_text:
                            if current_section == 'linh_vuc' and li_text not in linh_vuc_nghien_cuu:
                                linh_vuc_nghien_cuu.append(li_text)
                            elif current_section == 'giang_day' and li_text not in giang_day:
                                giang_day.append(li_text)
                            elif current_section == 'bai_bao' and li_text not in bai_bao_khoa_hoc:
                                bai_bao_khoa_hoc.append(li_text)
                            elif current_section == 'de_tai' and li_text not in de_tai_nghien_cuu:
                                de_tai_nghien_cuu.append(li_text)
                            elif current_section == 'sach' and li_text not in sach:
                                sach.append(li_text)

        if not email_val:
            for href in response.css('a[href^="mailto:"]::attr(href)').getall():
                addr = href.replace('mailto:', '').strip()
                if addr and addr.lower() != 'sofl@hust.edu.vn':
                    email_val = addr
                    break

        if not tel_val:
            for t in response.xpath('//*[contains(text(),"Tel") or contains(text(),"ĐT:") or contains(text(),"tel:")]//text()').getall():
                m = re.search(r'[\d\s\-\+\.]{7,}', t)
                if m:
                    tel_val = m.group().strip()
                    break

        item['chuc_vu'] = ' - '.join(chuc_vu_list) if chuc_vu_list else None
        item['noi_lam_viec'] = noi_lam_viec
        item['email'] = email_val
        item['tel'] = tel_val
        item['linh_vuc_nghien_cuu'] = linh_vuc_nghien_cuu
        item['giang_day'] = giang_day
        item['bai_bao_khoa_hoc'] = bai_bao_khoa_hoc
        item['sach'] = sach
        item['de_tai_nghien_cuu'] = de_tai_nghien_cuu
        item['gioi_thieu'] = ' '.join(gioi_thieu)


        raw_html = ' '.join(content.getall())
        item['html_text'] = self.clean_html_text(raw_html)


        item['nhom_chuyen_mon']         = nhom_chuyen_mon
        item['dai_hoc']                 = 'Đại học Bách khoa Hà Nội'
        item['don_vi_truc_thuoc']       = 'Khoa Ngoại ngữ'
        item['thong_tin_khong_cong_bo'] = False
        item['is_extracted']            = True
        item['is_checked']              = False

        yield item

    def closed(self, reason):
        stats = self.crawler.stats
        crawled = stats.get_value('response_received_count', 0)
        scraped = stats.get_value('item_scraped_count', 0)
        if crawled > 0:
            stats.set_value('coverage_percent', round((scraped / crawled) * 100, 2))