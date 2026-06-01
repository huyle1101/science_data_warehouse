import scrapy
from datetime import datetime
import os
import re

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = 'f:/science_data_warehouse_repo/output/neu/sbf/raw_data'
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'sbf.jsonl')

LOG_DIR = 'f:/science_data_warehouse_repo/output/neu/sbf/logs'
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f'sbf_{timestamp}.log')

class SbfSpiderSpider(scrapy.Spider):
    name = "sbf_spider"
    allowed_domains = ["nhtc.neu.edu.vn"]
    start_urls = ["https://nhtc.neu.edu.vn/chuyen-muc/gioi-thieu/cac-bo-mon/tai-chinh-cong/danh-sach-giang-vien-tai-chinh-cong/"]
    
    custom_settings = {
        "LOG_FILE": LOG_FILE,
        "LOG_LEVEL": "INFO",
        "FEEDS": {
            OUTPUT_FILE: {
                'format': 'jsonlines',
                "encoding": "utf8",
                "overwrite": False
            }
        },
        "CONCURRENT_REQUESTS": 500,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 32,
        "DOWNLOAD_DELAY": 1,
        "RANDOMIZED_DOWNLOAD_DELAY": True,
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 3, 
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429, 403],
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 0.5,
        "AUTOTHROTTLE_MAX_DELAY": 60,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 32,
        "FEED_EXPORT_FIELDS": [
            "url",
            "avt_url",
            "ho_ten",
            "dia_chi",
            "email",
            "huong_nghien_cuu_chinh",
            "chuyen_nganh_nghien_cuu",
            "sach",
            "bai_bao_trong_nuoc",
            "bai_bao_quoc_te",
            "bao_cao_trong_nuoc",
            "bao_cao_quoc_te",
            "de_tai_du_an",
            "giai_thuong",
            "huong_dan_ncs",
            "thong_tin_khac",
            'dai_hoc',
            'don_vi_truc_thuoc',
            "html_text",
            'thong_tin_khong_cong_bo',
            "is_extracted",
            "is_checked",
        ]
    }
    
    def clean_html_text(self, html_text): 
        if not html_text:
            return ""
        html_text = re.sub(r'<script\b[^>]*>([\s\S]*?)<\/script>', '', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'<style\b[^>]*>([\s\S]*?)<\/style>', '', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'<[^>]+>', '', html_text)
        html_text = re.sub(r'\n+', '\n', html_text)
        cleaned_text = '\n'.join([line.strip() for line in html_text.splitlines() if line.strip()])
        return cleaned_text

    def parse(self, response):
        scholars = response.css('.post-item')
        for scholar in scholars:
            scholar_url = scholar.css('a.plain::attr(href)').get()
            avt_url = scholar.css('noscript img::attr(src)').get()
            if not avt_url:
                avt_url = scholar.css('img.wp-post-image::attr(data-src)').get()
            if scholar_url:
                yield response.follow(
                    scholar_url, 
                    callback=self.parse_scholar,
                    meta={'avt_url': avt_url} 
                )
        next_page_urls = response.css('a.next.page-number::attr(href)').getall()
        for next_page_url in next_page_urls:
            if next_page_url:
                yield response.follow(next_page_url, callback=self.parse)
        
    def parse_scholar(self, response):
        item = {}
        item['url'] = response.url
        item['avt_url'] = response.meta.get('avt_url') or ""
        
        def get_table_value(label):
            td_nodes = response.xpath(f'//td[contains(., "{label}")]/following-sibling::td[1]//text()').getall()
            if td_nodes:
                text = " ".join([t.strip() for t in td_nodes if t.strip()])
                return re.sub(r'\s+', ' ', text).strip()
            return None

        ho_ten_table = get_table_value("Họ và tên")
        hoc_vi_table = get_table_value("Học vị cao nhất") or get_table_value("Học vị")
        
        if ho_ten_table:
            if hoc_vi_table:
                hv_lower = hoc_vi_table.lower()
                prefix = hoc_vi_table
                
                if "phó giáo sư" in hv_lower and ("tiến sĩ" in hv_lower or "tiến sỹ" in hv_lower):
                    prefix = "PGS.TS."
                elif "giáo sư" in hv_lower and ("tiến sĩ" in hv_lower or "tiến sỹ" in hv_lower):
                    prefix = "GS.TS."
                elif "tiến sĩ" in hv_lower or "tiến sỹ" in hv_lower:
                    prefix = "TS."
                elif "thạc sĩ" in hv_lower or "thạc sỹ" in hv_lower:
                    prefix = "ThS."
                elif "cử nhân" in hv_lower:
                    prefix = "CN."
                
                if len(prefix) <= 7 and not prefix.endswith('.'):
                    prefix += "."
                    
                item['ho_ten'] = f"{prefix} {ho_ten_table}".strip()
            else:
                item['ho_ten'] = ho_ten_table
        else:
            item['ho_ten'] = response.css('.entry-title::text').get(default="").strip()

        item['dia_chi'] = get_table_value("Địa chỉ liên lạc")
        item['email'] = get_table_value("Email")
        item['huong_nghien_cuu_chinh'] = get_table_value("Hướng nghiên cứu chính")
        item['chuyen_nganh_nghien_cuu'] = get_table_value("Chuyên ngành nghiên cứu")

        sections_map = {
            "4.2.1. Sách giáo trình": "sach",
            "4.2.2. Các bài báo đăng trên tạp chí khoa học trong nước": "bai_bao_trong_nuoc",
            "4.2.3. Các bài báo đăng trên tạp chí khoa học nước ngoài": "bai_bao_quoc_te",
            "4.2.4. Các báo cáo hội nghị, hội thảo trong nước": "bao_cao_trong_nuoc",
            "4.2.5. Các báo cáo hội nghị, hội thảo quốc tế": "bao_cao_quoc_te",
            "4.3. Các đề tài, dự án": "de_tai_du_an",
            "4.4. Giải thưởng": "giai_thuong",
            "4.5. Kinh nghiệm hướng dẫn": "huong_dan_ncs",
            "4.6. Những thông tin khác": "thong_tin_khac",
            "5. Giảng dạy": "END"
        }
        
        for key in sections_map.values():
            if key != "END":
                item[key] = []
                
        current_section = None
        
        for tr in response.xpath('//figure[contains(@class, "wp-block-table")]//tr'):
            row_text = " ".join(tr.xpath('.//text()').getall()).strip()
            
            found_section = False
            for sec_key, sec_val in sections_map.items():
                if sec_key in row_text:
                    current_section = sec_val
                    found_section = True
                    break
            
            if found_section:
                continue
                
            if current_section and current_section != "END":
                cols = tr.xpath('./td | ./th')
                col_texts = []
                for col in cols:
                    text = " ".join(col.xpath('.//text()').getall())
                    text = re.sub(r'\s+', ' ', text).strip()
                    if text:
                        col_texts.append(text)
                
                if col_texts:
                    merged_text = " - ".join(col_texts)
                    merged_lower = merged_text.lower()
                    
                    header_keywords = ["tên công trình", "tên sách", "tên đề tài", "tên dự án", "cấp đề tài", "tạp chí, nơi công bố"]
                    if any(kw in merged_lower for kw in header_keywords):
                        continue
                    
                    first_col = col_texts[0].lower()
                    if first_col in ["stt", "tt", "năm", "năm công bố", "năm xuất bản", "thời gian"]:
                        continue
                    
                    item[current_section].append(merged_text)
        
        for key in sections_map.values():
            if key != "END":
                if len(item[key]) == 0:
                    item[key] = None

        raw_html = response.css('.entry-content.single-page').get()
        item['html_text'] = self.clean_html_text(raw_html) if raw_html else ""
        item['dai_hoc'] = 'Đại học Kinh tế quốc dân'
        item['don_vi_truc_thuoc'] = 'Viện Ngân hàng Tài chính'
        item["thong_tin_khong_cong_bo"] = False
        item['is_extracted'] = True
        item['is_checked'] = False
        
        yield item
        
    def closed(self, reason):
        stats = self.crawler.stats 
        crawled = stats.get_value('response_received_count', 0)
        scraped = stats.get_value('item_scraped_count', 0)
        if crawled > 0:
            coverage = (scraped / crawled) * 100
            stats.set_value('coverage_percent', round(coverage, 2))