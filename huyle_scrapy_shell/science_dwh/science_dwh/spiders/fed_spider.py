import scrapy
from science_dwh.items import fed_item
import re
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
import os

class FedSpiderSpider(scrapy.Spider):
    name = "fed_spider"
    allowed_domains = ["fed.hust.edu.vn"]
    start_urls = ["https://fed.hust.edu.vn/vi/about/can-bo-va-giang-vien.html"]
    
    LOG_DIR = f"f:/science_data_warehouse_repo/output/hust/fed/logs"
    OUTPUT_DIR = "f:/science_data_warehouse_repo/output/hust/fed/raw_data"
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)


    custom_settings = {
        "LOG_FILE": os.path.join(LOG_DIR, f"fed_{timestamp}.log"),
        "LOG_LEVEL":"INFO",
        "FEEDS":{
            os.path.join(OUTPUT_DIR, "fed.jsonl"):{
                'format':'jsonlines',
                "encoding": "utf8",
                "overwrite": False # append mode
            }
        },
        "CONCURRENT_REQUESTS" : 32,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 16,
        "DOWNLOAD_DELAY" : 1,
        "RANDOMIZED_DOWNLOAD_DELAY":True, 

        "RETRY_ENABLED":True,
        "RETRY_TIMES": 3, 
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429, 403],

        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 1, # initial download delay
        "AUTOTHROTTLE_MAX_DELAY": 60, # maximum download delay to be set in case of high latencies
        "AUTOTHROTTLE_TARGET_CONCURRENCY"  : 16, # average number of requests Scrapy should be sending in parallel to each remote server

        'FEED_EXPORT_FIELDS' : [
            "url",
            "avt_url",
            "ho_ten",
            "chuc_danh",
            "don_vi",
            "phong_lam_viec",
            "email",
            "dien_thoai",
            "qua_trinh_dao_tao",
            "qua_trinh_cong_tac",
            "linh_vuc_nghien_cuu",
            "linh_vuc_phu_trach_quan_tam",
            "cac_mon_giang_day",
            "de_tai_du_an",
            "cong_trinh_khoa_hoc",
            "sach_va_giao_trinh",
            "dai_hoc",
            "don_vi_truc_thuoc",
            "thong_tin_khong_cong_bo",
            "is_extracted",
            "is_checked"
        ]
    }

    def parse(self, response):
        scholars = response.xpath('//tr/td/a[contains(text(), "Chi tiết")]/@href').getall()
        for scholar in scholars:
            req= response.follow(scholar, callback=self.parse_scholar)
            req.meta['deltafetch_key'] = scholar
            yield req

    def parse_scholar(self, response):
        item = fed_item()
        item['url'] = response.url
        
        
        avt_url_1 = response.xpath('//div[@id="news-bodyhtml"]//img/@src').get()
        avt_url_2 = response.urljoin(response.xpath('//div[@id="news-bodyhtml"]//img/@src').get(''))
        if re.match(r"^https", avt_url_1):
            item['avt_url'] = avt_url_1
        else:
            item['avt_url'] = avt_url_2
        
        item['ho_ten'] = response.css('h1::text').get(default='').strip()
        item['chuc_danh'] = response.xpath('//p[strong[re:test(text(), "Chức danh", "i")]]/text()').get(default='').strip()
        item['don_vi'] = response.xpath('//p[strong[re:test(text(), "Đơn vị công tác", "i")]]/text()').get(default='').strip()
        item['phong_lam_viec'] = response.xpath('//p[strong[re:test(text(), "Phòng làm việc", "i")]]/text()').get(default='').strip()
        item['email'] = response.xpath('//p[strong[re:test(text(), "Email", "i")]]/text()').get(default='').strip()
        item['dien_thoai'] = response.xpath('//p[strong[re:test(text(), "Điện thoại", "i")]]/text()').get(default='').strip()

        item['qua_trinh_dao_tao'] = [li.xpath('normalize-space(.)').get() for li in response.xpath('//h2[re:test(text(), "Quá trình đào tạo", "i")]/following-sibling::ul[1]/li')]
        item['qua_trinh_cong_tac'] = [li.xpath('normalize-space(.)').get() for li in response.xpath('//h2[re:test(text(), "Quá trình công tác", "i")]/following-sibling::ul[1]/li')]
        item['linh_vuc_nghien_cuu'] = [li.xpath('normalize-space(.)').get() for li in response.xpath('//h2[re:test(text(), "nghiên cứu", "i")]/following-sibling::ul[1]/li')]
        item['linh_vuc_phu_trach_quan_tam'] = [li.xpath('normalize-space(.)').get() for li in response.xpath('//h2[re:test(text(), "Lĩnh vực (phụ trách|quan tâm)", "i")]/following-sibling::*[self::ul or self::ol][1]/li')]

        item['cac_mon_giang_day']=[li.xpath('normalize-space(.)').get() for li in response.xpath('//h2[re:test(text(), "giảng dạy", "i")]/following-sibling::ul[1]/li')]
        
        item['de_tai_du_an'] = [li.xpath('normalize-space(.)').get() for li in response.xpath('//h2[re:test(text(), "Đề tài, dự án nghiên cứu", "i")]/following-sibling::ol[preceding-sibling::h2[1][re:test(text(), "Đề tài, dự án", "i")]]/li')]

        item['cong_trinh_khoa_hoc'] = [li.xpath('normalize-space(.)').get() for li in response.xpath('//h2[re:test(text(), "Công trình khoa học", "i")]/following-sibling::ol[1]/li')]
        item['sach_va_giao_trinh'] = [li.xpath('normalize-space(.)').get() for li in response.xpath('//h2[re:test(text(), "Sách chuyên khảo", "i")]/following-sibling::ol[1]/li')]
        item['dai_hoc']='Đại học Bách Khoa Hà Nội'
        item['don_vi_truc_thuoc']='Khoa Khoa học công nghệ và Giáo dục'   
        
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
