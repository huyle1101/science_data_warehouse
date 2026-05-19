import scrapy
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
from science_dwh.items import soict_item

class SoictSpiderSpider(scrapy.Spider):
    name = "soict_spider"
    allowed_domains = ["soict.hust.edu.vn"]
    start_urls = ["https://soict.hust.edu.vn/can-bo"]

    custom_settings = {
        
        "LOG_FILE":f"f:/science_data_warehouse_repo/output/hust/soict/logs/soict_{timestamp}.log",
        "LOG_LEVEL":"INFO",
        "FEEDS":{
            f"f:/science_data_warehouse_repo/output/hust/soict/data/soict.csv":{
                'format':'csv',
                "encoding": "utf8",
                "overwrite": False
            }
    },
        "CONCURRENT_REQUESTS" : 32,
        "CONCURRENT_REQUESTS_PER_DOMAIN" : 8,
        "DOWNLOAD_DELAY" : 1,
        "RANDOMIZED_DOWNLOAD_DELAY":True,

        "RETRY_ENABLED":True,
        "RETRY_TIMES": 10, 
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429, 403],

        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 5, # initial download delay
        "AUTOTHROTTLE_MAX_DELAY": 60, # maximum download delay to be set in case of high latencies
        "AUTOTHROTTLE_TARGET_CONCURRENCY"  : 1.0, # average number of requests Scrapy should be sending in parallel to each remote server
        
        "FEED_EXPORT_FIELDS": [ # columns to export in csv
            "url",
            "ho_ten",
            "gioi_thieu",
            "vi_tri",
            "chuc_vu",
            "hoc_ham_hoc_vi",
            "qua_trinh_dao_tao",
            "email",
            "linh_vuc_nghien_cuu",
            "nghien_cuu_quan_tam",
            "du_an_hien_tai",
            "cong_trinh_tieu_bieu",
            "giai_thuong_khen_thuong",
            "cac_mon_giang_day"
        ]
    }

    def parse(self, response):
        # return links to scholar information
        scholars = response.css('h2.entry-title a::attr(href)').getall()
        for scholar in scholars:
            # go into each link
            yield response.follow(
                scholar,
                callback = self.parse_scholar,
                # dont_filter=True
            )
        next_page_url = response.xpath('//ul[contains(@class, "page-numbers")]//a[contains(@class, "next")]/@href').get()
        # if not blank, go to next_page_url
        if next_page_url:
            yield response.follow(next_page_url, callback=self.parse)
    
    def parse_scholar(self, response):
        item = soict_item()
        item['url'] = response.url

        item['ho_ten'] = response.css('span.breadcrumb_last::text').get()
        item['gioi_thieu'] = response.xpath('//span[contains(text(), "Giới thiệu")]/ancestor::div[1]/following-sibling::p[1]//text()').getall()

        info_list = response.css('div.col-inner p:not(.lead) strong::text').getall()
        # chức vụ = hiệu trưởng,....
        item['chuc_vu'] = info_list[0] if len(info_list) > 0 else None
        # vị trí = trưởng nhóm nghiên cứu tối ưu hóa,.....
        item['vi_tri'] = info_list[1] if len(info_list) > 1 else None
        # học hàm học vị = tiến s khoa học máy tính,....
        item['hoc_ham_hoc_vi'] = info_list[2] if len(info_list) > 2 else None

        raw_edu = response.css('div.col-inner p:not(.lead) strong::text').getall()[3:]
        item['qua_trinh_dao_tao'] = raw_edu[:3] if len(raw_edu) > 3 else raw_edu

        item['email'] = response.css('a[href^="mailto:"]::text').getall()

        item['linh_vuc_nghien_cuu'] = response.xpath('//span[contains(text(), "Lĩnh vực nghiên cứu")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall()
        item['nghien_cuu_quan_tam'] = response.xpath('//span[contains(text(), "Các nghiên cứu quan tâm")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall()
        item['cong_trinh_tieu_bieu'] = response.xpath('//span[contains(text(), "Các công trình khoa học tiêu biểu")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall()
        item['giai_thuong_khen_thuong'] = response.xpath('//span[contains(text(), "Giải thưởng, khen thưởng")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall()
        item['cac_mon_giang_day'] = response.xpath('//span[contains(text(), "Giảng dạy")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall()

        du_an_1 = response.xpath('//span[contains(text(), "Dự án hiện tại")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall()
        du_an_2 = response.xpath('//span[contains(text(), "Các dự án đang thực hiện")]/ancestor::div[1]/following-sibling::ol[1]/li//text()').getall()
        item['du_an_hien_tai'] = du_an_1 if du_an_1 else du_an_2
        yield item