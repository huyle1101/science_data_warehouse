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
            f"f:/science_data_warehouse_repo/output/hust/sme/raw_data/sme.jsonl":{
                'format':'jsonlines',
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
            "dai_hoc",
            "don_vi_truc_thuoc",
            "html_text",
            "thong_tin_khong_cong_bo",
            "is_extracted",
            "is_checked"
        ]
    }


    # clean html text before feeding into Gemini API for information extraction to avoid excessive token usage
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
        scholars = response.xpath('//table[contains(@class, "table")]//tr/td[2]/h3/a/@href').getall()
        for scholar in scholars:
            yield response.follow(
                scholar,
                callback = self.parse_scholar,
                # dont_filter=True
            )

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
        item['dai_hoc'] = 'Đại học Bách khoa Hà Nội'
        item['don_vi_truc_thuoc'] = 'Trường Cơ khí'
        
        # get all text under "Lý lịch khoa học" section of sole text-break class
        list = response.xpath('//h2[span[contains(text(), "Lý lịch khoa học")]]/following-sibling::div[contains(@class, "text-break")]//text()').getall()
        html_text = ' '.join(list)
        item['html_text'] = self.clean_html_text(html_text)

        item["thong_tin_khong_cong_bo"] = False
        item["is_extracted"] = False
        item["is_checked"] = False

        yield item
    
    def closed(self, reason):
        # calculate coverage percentage and store in Dumping Scrapy stats
        stats = self.crawler.stats 

        crawled = stats.get_value('response_received_count', 0)
        scraped = stats.get_value('item_scraped_count', 0)

        if crawled > 0:
            coverage = (scraped / crawled) * 100
            stats.set_value('coverage_percent', round(coverage, 2))