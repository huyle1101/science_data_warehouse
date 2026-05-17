import scrapy
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
from science_dwh.items import ScholarItem

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
            'ho_ten',
            'chuc_vu',
            'thuoc_don_vi',
            'dia_chi_email',
            'nhom_chuyen_mon',
            'dia_chi_lam_viec',
            'cac_mon_giang_day',
            'cac_nghien_cuu_quan_tam',
            'cac_cong_trinh_khoa_hoc_tieu_bieu',
            'qua_trinh_dao_tao',
            "dai_hoc",
            "don_vi_truc_thuoc"
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

    def parse_scholar(self, response):
        url = response.url
        ho_ten = response.xpath('//div[@class="flex-des"]/p[b[contains(text(), "Họ tên:")]]/text()').get('').strip()
        chuc_vu = response.xpath('//div[@class="flex-des"]/p[b[contains(text(), "Chức vụ:")]]/text()').get('').strip()
        thuoc_don_vi = response.xpath('//div[@class="flex-des"]/p[b[contains(text(), "Thuộc đơn vị:")]]/a/text()').get('').strip()
        dia_chi_email = response.xpath('//div[@class="flex-des"]/p/a[contains(@href, "mailto")]/text()').get('').strip()
        nhom_chuyen_mon = response.xpath('//div[@class="flex-des"]/p[b[contains(text(), "Nhóm chuyên môn:")]]/text()').get('').strip()
        dia_chi_lam_viec = response.xpath('//h2[strong[contains(text(), "Địa chỉ làm việc:")]]/text()').get('').strip().replace('\xa0', ' ')
        cac_mon_giang_day = response.xpath('//p[span[strong[contains(text(), "Các môn giảng dạy")]]]/following-sibling::ul[1]/li/p/span/text()').getall()
        cac_nghien_cuu_quan_tam = response.xpath('//p[span[strong[contains(text(), "Các nghiên cứu quan tâm")]]]/following-sibling::ul[1]/li/p/span/text()').getall()
        
        cac_cong_trinh_khoa_hoc_tieu_bieu = [
            "".join(li.xpath('.//text()').getall()).strip() 
            for li in response.xpath('//p[span[strong[contains(text(), "Các công trình khoa học tiêu biểu")]]]/following-sibling::ul[1]/li')
        ]

        qua_trinh_dao_tao = response.xpath('//p[span[strong[contains(text(), "Đào tạo")]]]/following-sibling::ul[1]/li/p/span/text()').getall()
        dai_hoc = 'Đại học Bách Khoa Hà Nội'
        don_vi_truc_thuoc = "Trường Cơ khí"

        yield {
            "url": url,
            'ho_ten': ho_ten,
            'chuc_vu': chuc_vu,
            'thuoc_don_vi': thuoc_don_vi,
            'dia_chi_email': dia_chi_email,
            'nhom_chuyen_mon': nhom_chuyen_mon,
            'dia_chi_lam_viec': dia_chi_lam_viec,
            'cac_mon_giang_day': cac_mon_giang_day,
            'cac_nghien_cuu_quan_tam': cac_nghien_cuu_quan_tam,
            'cac_cong_trinh_khoa_hoc_tieu_bieu': cac_cong_trinh_khoa_hoc_tieu_bieu,
            'qua_trinh_dao_tao': qua_trinh_dao_tao,
            "dai_hoc":dai_hoc,
            "don_vi_truc_thuoc":don_vi_truc_thuoc
        }