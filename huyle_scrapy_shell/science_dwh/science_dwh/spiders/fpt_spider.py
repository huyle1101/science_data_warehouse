import scrapy
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
from science_dwh.items import fpt_item
import os
import re

OUTPUT_DIR = 'f:/science_data_warehouse_repo/output/hust/fpt/raw_data'
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'fpt.jsonl')

LOG_DIR = 'f:/science_data_warehouse_repo/output/hust/fpt/logs'
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f'fpt_{timestamp}.log')


class FptSpiderSpider(scrapy.Spider):
    name = "fpt_spider"
    allowed_domains = ["fpt.hust.edu.vn"]
    start_urls = ["https://fpt.hust.edu.vn/vi/about/can-bo-giang-vien-224481.html"]
    
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
            "ho_ten",
            "avt_url",
            "nhom_chuyen_mon",
            "html_text",
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
        bodyhtml = response.css('#page-bodyhtml')

        links = bodyhtml.xpath(
            './/a[contains(@href, "/bo-mon/") and '
            'not(contains(@href, "nhom-chuyen-mon")) and '
            'not(contains(@href, "bo-phan-chuyen-mon"))]'
        )

        seen = set()
        for link in links:
            raw_url = link.attrib.get('href', '')

            # Fix lỗi href bị duplicate: lấy URL đầu tiên nếu có 2 URL dính nhau
            url = re.split(r'(?<=\.html)', raw_url)[0].strip()

            if not url or url in seen:
                continue
            seen.add(url)

            nhom = link.xpath(
                'ancestor::table[1]/preceding-sibling::*'
                '[self::h2 or self::div[.//strong]][1]//text()'
            ).getall()
            nhom_chuyen_mon = ' '.join(t.strip() for t in nhom if t.strip())

            yield response.follow(
                url,
                callback=self.parse_scholar,
                cb_kwargs={'nhom_chuyen_mon': nhom_chuyen_mon}
            )

    def parse_scholar(self, response, nhom_chuyen_mon):
        item = fpt_item()

        item['url'] = response.css('meta[property="og:url"]::attr(content)').get()

        item['ho_ten'] = response.css('h1.title[itemprop="headline"]::text').get('').strip()

        avt_src = response.css('#news-bodyhtml img::attr(src)').get('')
        item['avt_url'] = response.urljoin(avt_src) if avt_src else \
                          response.css('meta[property="og:image"]::attr(content)').get('')

        item['nhom_chuyen_mon'] = nhom_chuyen_mon

        raw_html_text = response.css('#news-bodyhtml').get('')
        item['html_text'] = self.clean_html_text(raw_html_text)

        item['dai_hoc'] = 'Đại học Bách khoa Hà Nội'
        item['don_vi_truc_thuoc'] = 'Khoa Lý luận chính trị'
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