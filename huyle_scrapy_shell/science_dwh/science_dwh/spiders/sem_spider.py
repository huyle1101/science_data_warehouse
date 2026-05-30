import scrapy
from science_dwh.items import sem_item
import os
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")


class SemSpiderSpider(scrapy.Spider):
    name = "sem_spider"
    allowed_domains = ["sem.hust.edu.vn"]
    start_urls = ["https://sem.hust.edu.vn/danh-sach-giang-vien"]

    LOG_DIR = f"f:/science_data_warehouse_repo/output/hust/sem/logs"
    OUTPUT_DIR = "f:/science_data_warehouse_repo/output/hust/sem/raw_data"
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)


    custom_settings = {
        "LOG_FILE": os.path.join(LOG_DIR, f"sem_{timestamp}.log"),
        "LOG_LEVEL":"INFO",
        "FEEDS":{
            os.path.join(OUTPUT_DIR, "sem.jsonl"):{
                'format':'jsonlines',
                "encoding": "utf8",
                "overwrite": False # append mode
            }
        },
        "CONCURRENT_REQUESTS" : 128,
        "CONCURRENT_REQUESTS_PER_DOMAIN" : 32,
        "DOWNLOAD_DELAY" : 1,
        "RANDOMIZED_DOWNLOAD_DELAY":True,
        
        "RETRY_ENABLED":True,
        "RETRY_TIMES": 5, 
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429, 403],

        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 0.5, # initial download delay
        "AUTOTHROTTLE_MAX_DELAY": 30, # maximum download delay to be set in case of high latencies
        "AUTOTHROTTLE_TARGET_CONCURRENCY"  : 10, # average number of requests Scrapy should be sending in parallel to each remote server

        "FEED_EXPORT_FIELDS": [
            "url",
            "avt_url",
            'ho_ten',
            'chuc_vu',
            "dai_hoc",
            "don_vi_truc_thuoc",
            "html_text",
            "thong_tin_khong_cong_bo",
            "is_extracted",
            "is_checked"
        ]
    }
    def parse(self, response):
        scholars = response.xpath('//h2[@class="pp-post-title"]/a/@href').getall()
        for scholar in scholars:
            yield response.follow(
                scholar,
                callback = self.parse_scholar,
                # dont_filter=True
            )
        
        next_page_url = response.css('a.next::attr(href)').get()
        if next_page_url:
            yield response.follow(next_page_url, callback=self.parse)

    def parse_scholar(self, response):
        item = sem_item()
        item['url'] = response.url
        item['avt_url'] = response.xpath('//div[contains(@class, "elementor-widget-image")]//div[@class="elementor-widget-container"]/img/@src').get()
        item['ho_ten'] = response.css('.elementor-page-title h1::text').get()
         
        chuc_vu_text = response.xpath('//div[contains(@class, "elementor-widget-theme-post-excerpt")]/div[@class="elementor-widget-container"]/text()').get()
        item['chuc_vu'] = chuc_vu_text.strip() if chuc_vu_text else None
        
        
        raw_list = response.css('div[data-widget_type="theme-post-content.default"] .elementor-widget-container *::text').getall()
        item['html_text'] = [el.strip() for el in raw_list]
        
        item['thong_tin_khong_cong_bo'] = False
        item['is_extracted'] = False
        item['is_checked'] = False
        
        item['dai_hoc'] = 'Đại học Bách khoa Hà Nội'
        item['don_vi_truc_thuoc'] = 'Trường Kinh tế'
        
        yield item
    
    def closed(self, reason):
        # calculate coverage percentage and store in Dumping Scrapy stats
        stats = self.crawler.stats 

        crawled = stats.get_value('response_received_count', 0)
        scraped = stats.get_value('item_scraped_count', 0)

        if crawled > 0:
            coverage = (scraped / crawled) * 100
            stats.set_value('coverage_percent', round(coverage, 2))
        