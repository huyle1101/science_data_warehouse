import scrapy
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
from science_dwh.items import sme_item
import re

class SmeSpiderSpider(scrapy.Spider):
    name = "sme_spider"
    allowed_domains = ["sme.hust.edu.vn"]
    start_urls = ["https://sme.hust.edu.vn/vi/organs/"]

    custom_settings = {
        "LOG_FILE":f"f:/science_data_warehouse_repo/output/hust/sme/logs/sme_{timestamp}.log",
        "LOG_LEVEL":"INFO",
        "FEEDS":{
            f"f:/science_data_warehouse_repo/output/hust/sme/data/sme.csv":{
                'format':'csv',
                "encoding": "utf8",
                "overwrite": False # append mode
            }
        },
        "CONCURRENT_REQUESTS" : 32,
        "CONCURRENT_REQUESTS_PER_DOMAIN" : 8,
        "DOWNLOAD_DELAY" : 1,
        "RANDOMIZED_DOWNLOAD_DELAY":True,
        
        "RETRY_ENABLED":True,
        "RETRY_TIMES": 5, 
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429, 403],

        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 5, # initial download delay
        "AUTOTHROTTLE_MAX_DELAY": 60, # maximum download delay to be set in case of high latencies
        "AUTOTHROTTLE_TARGET_CONCURRENCY"  : 1.0, # average number of requests Scrapy should be sending in parallel to each remote server

        "FEED_EXPORT_FIELDS": [
            "url",
            "avt_url",
            'ho_ten',
            'chuc_vu',
            'chuc_danh_kiem_nhiem',
            'don_vi',
            'email',
            'nhom_chuyen_mon',
            # 'dia_chi_lam_viec',
            # 'cac_mon_giang_day',
            # 'linh_vuc_nghien_cuu',
            # 'qua_trinh_dao_tao',
            # 'cong_trinh_tieu_bieu',
            # 'du_an_hien_tai',
            # 'hv_cao_hoc',
            # 'ncs_phd',
            # 'sach',
            # 'giai_thuong',
            # 'hop_tac_chuyen_giao',
            # 'thong_tin_khac',
            "dai_hoc",
            "don_vi_truc_thuoc",
            "html_text"
        ],
        "DOWNLOADER_MIDDLEWARES":{
            'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
            'scrapy_user_agents.middlewares.RandomUserAgentMiddleware': 400,
            'scrapy.downloadermiddlewares.retry.RetryMiddleware': None,
        },
        "DEFAULT_REQUEST_HEADERS": {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
        }
    }


    def parse(self, response):
        scholars = response.xpath('//table[contains(@class, "table")]//tr/td[2]/h3/a/@href').getall()
        for scholar in scholars:
            yield response.follow(
                scholar,
                callback = self.parse_scholar,
                # dont_filter=True
            )
    # clean html text before feeding into Gemini API for information extraction to avoid excessive token usage
    def clean_html_text(self,html_text): 
        if not html_text:
            return ""
            
        # 1. Xóa toàn bộ cặp thẻ <script>...</script> và nội dung Javascript bên trong
        html_text = re.sub(r'<script\b[^>]*>([\s\S]*?)<\/script>', '', html_text, flags=re.IGNORECASE)
        
        # 2. Xóa toàn bộ cặp thẻ <style>...</style> và nội dung CSS bên trong
        html_text = re.sub(r'<style\b[^>]*>([\s\S]*?)<\/style>', '', html_text, flags=re.IGNORECASE)
        
        # 3. Xóa các đoạn Comment HTML ()
        html_text = re.sub(r'', '', html_text)
        
        # 4. Xóa tất cả các thẻ HTML còn lại (các cặp ngoặc nhọn <...>)
        html_text = re.sub(r'<[^>]+>', '', html_text)
        
        # 5. Dọn dẹp khoảng trắng, dấu xuống dòng thừa (\n) để văn bản đẹp hơn
        html_text = re.sub(r'\n+', '\n', html_text)
        cleaned_text = '\n'.join([line.strip() for line in html_text.splitlines() if line.strip()])
        
        return cleaned_text

    def parse_scholar(self, response):
        item = sme_item() # don't use sme_item = sme_item() which creates an instance at the class level and causes data overwriting across items, instead create a new instance for each item in the parse method.
        item['url'] = response.url

        relative_url = response.css('.flex-avatar img::attr(data-src)').get()
        item['avt_url'] = response.urljoin(relative_url)
        
        # normalize space to ignore case and extra whitespace, then split by first colon to get value
        item['ho_ten'] = response.xpath('normalize-space(//*[contains(text(), "Họ tên")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['chuc_vu'] = response.xpath('normalize-space(//*[contains(text(), "Chức vụ")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        # chức danh kiêm nhiệm = trưởng NCM robot,....
        item['chuc_danh_kiem_nhiem'] = response.xpath('normalize-space(//*[contains(text(), "Chức danh kiêm nhiệm")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['don_vi'] = response.xpath('normalize-space(//*[contains(text(), "Thuộc đơn vị")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['email'] = response.xpath('normalize-space(//*[contains(text(), "Địa chỉ email")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['nhom_chuyen_mon'] = response.xpath('//b[contains(text(), "Nhóm chuyên môn")]/following-sibling::text()').get()
        item['dai_hoc'] = 'Đại học Bách Khoa Hà Nội'
        item['don_vi_truc_thuoc'] = 'Trường Cơ khí'
        
        html_text = response.text
        item['html_text'] = self.clean_html_text(html_text)

        yield item