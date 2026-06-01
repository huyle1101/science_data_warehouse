import scrapy
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
from science_dwh.items import sep_item
import os
import re

OUTPUT_DIR = 'f:/science_data_warehouse_repo/output/hust/sep/raw_data'
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'sep.jsonl')

LOG_DIR = 'f:/science_data_warehouse_repo/output/hust/sep/logs'
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f'sep_{timestamp}.log')

class SepSpiderSpider(scrapy.Spider):
    name = "sep_spider"
    allowed_domains = ["sep.hust.edu.vn"]
    start_urls = ["https://sep.hust.edu.vn/can-bo"]
    
    custom_settings = {
        "LOG_FILE": LOG_FILE,
        "LOG_LEVEL":"INFO",
        "FEEDS":{
            OUTPUT_FILE:{
                'format':'jsonlines',
                "encoding": "utf8",
                "overwrite": False
            }
    },
        "CONCURRENT_REQUESTS": 500, # maximum number of requests to all domains
        "CONCURRENT_REQUESTS_PER_DOMAIN" : 32, # increase this first to increase speed
        "DOWNLOAD_DELAY" : 1,
        "RANDOMIZED_DOWNLOAD_DELAY":True,
        
        "RETRY_ENABLED":True,
        "RETRY_TIMES": 3, 
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429, 403],

        
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 0.5, # initial download delay
        "AUTOTHROTTLE_MAX_DELAY": 60, # maximum download delay to be set in case of high latencies
        "AUTOTHROTTLE_TARGET_CONCURRENCY"  : 32, # average number of requests Scrapy should be sending in parallel to each remote server
        
        "FEED_EXPORT_FIELDS": [
            "url",
            "avt_url",
            "ho_ten",
            "web",
            "chuc_danh_kiem_nhiem",
            "chuc_vu",
            "html_text",
            "gioi_thieu",
            "qua_trinh_dao_tao",
            "email",
            "linh_vuc_nghien_cuu",
            "nghien_cuu_quan_tam",
            "cong_trinh_tieu_bieu",
            "sach",
            "giang_day",
            "giai_thuong",
            'de_tai_cho_thac_sy',
            'de_tai_cho_nghien_cuu_sinh',
            "dai_hoc",
            "don_vi_truc_thuoc",
            "thong_tin_khong_cong_bo",
            "is_extracted",
            "is_checked",
        ]
    }
    

    
    def clean_html_text(self,html_text): 
        if not html_text:
            return ""
        html_text = re.sub(r'<script\b[^>]*>([\s\S]*?)<\/script>', '', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'<style\b[^>]*>([\s\S]*?)<\/style>', '', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'', '', html_text)
        html_text = re.sub(r'<[^>]+>', '', html_text)
        html_text = re.sub(r'\n+', '\n', html_text)
        cleaned_text = '\n'.join([line.strip() for line in html_text.splitlines() if line.strip()])
        
        return cleaned_text

    def parse(self, response):
        scholars = response.css('#post-list .entry-title a::attr(href)').getall()
        for scholar in scholars:
            yield response.follow(
                scholar,
                callback=self.parse_scholar
            )
        next_page_url_list = response.css('a.page-number::attr(href)').getall()
        for next_page_url in next_page_url_list:
            if next_page_url:
                yield response.follow(next_page_url, callback=self.parse)
        

    def parse_scholar(self, response):
        item = sep_item()

        item['url'] = response.css('meta[property="og:url"]::attr(content)').get()
        item['avt_url'] = response.css('meta[property="og:image"]::attr(content)').get()
        item['ho_ten'] = response.xpath('normalize-space(//p[contains(@class, "lead")]//text())').get()

        chuc_vu_nodes = response.xpath('//p[@class="lead"]/following-sibling::p[1]//strong/text()').getall()
        chuc_vu_nodes = [x.strip() for x in chuc_vu_nodes if x.strip()]

        item['chuc_danh_kiem_nhiem'] = chuc_vu_nodes[0] if len(chuc_vu_nodes) > 0 else None

        item['chuc_vu'] = ", ".join(chuc_vu_nodes[1:]) if len(chuc_vu_nodes) > 1 else None

        dao_tao_nodes = response.xpath('//p[@class="lead"]/following-sibling::p[2]/text()').getall()
        item['qua_trinh_dao_tao'] = [x.strip() for x in dao_tao_nodes if x.strip()]

        item['email'] = response.xpath('//p[contains(text(), "Email:")]/text()').re_first(r'Email:\s*(.*)')
        item['web'] = response.xpath('//p[contains(text(), "Email:")]/text()').re_first(r'Web:\s*(.*)')
        
        gioi_thieu_texts = response.xpath('//div[.//span[contains(text(), "Giới thiệu")]]/following-sibling::p[1]//text()').getall()
        item['gioi_thieu'] = " ".join([x.strip() for x in gioi_thieu_texts if x.strip()])
        
        def get_list_after_heading(heading_keyword):
            lis = response.xpath(f'//div[.//span[contains(text(), "{heading_keyword}")]]/following-sibling::ul[1]/li')
            return ["".join(li.xpath('.//text()').getall()).strip() for li in lis]

        item['nghien_cuu_quan_tam'] = get_list_after_heading("nghiên cứu quan tâm")
        item['linh_vuc_nghien_cuu'] = get_list_after_heading("Lĩnh vực nghiên cứu")
        item['cong_trinh_tieu_bieu'] = get_list_after_heading("công trình khoa học tiêu biểu")
        item['sach'] = get_list_after_heading("Sách đã xuất bản")
        item['de_tai_cho_thac_sy'] = get_list_after_heading("giành cho thạc sỹ")
        item['de_tai_cho_nghien_cuu_sinh'] = get_list_after_heading("giành cho nghiên cứu sinh")
        item['giang_day'] = get_list_after_heading("Giảng dạy")
        item['giai_thuong'] = get_list_after_heading("Giải thưởng")
        
        item['dai_hoc'] = 'Đại học Bách khoa Hà Nội'
        item['don_vi_truc_thuoc'] = 'Khoa Vật lý Kỹ thuật'
        
        
        raw_html = response.xpath('//div[contains(@class, "entry-content single-page")]//text()').getall()
        html_text = ' '.join(raw_html)
        item['html_text'] = self.clean_html_text(html_text)
        
        item['thong_tin_khong_cong_bo'] = False
        item['is_extracted'] = True
        item['is_checked'] = False
        
        yield item
        
    def closed(self, reason):
        # calculate coverage percentage and store in Dumping Scrapy stats
        stats = self.crawler.stats 

        crawled = stats.get_value('response_received_count', 0)
        scraped = stats.get_value('item_scraped_count', 0)

        if crawled > 0:
            coverage = (scraped / crawled) * 100
            stats.set_value('coverage_percent', round(coverage, 2))
            
            
            
            