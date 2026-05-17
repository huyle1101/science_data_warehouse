import scrapy
# from scrapling.fetchers import Fetcher, AsyncFetcher, StealthyFetcher, DynamicFetcher
# StealthyFetcher.adaptive = True
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
from science_dwh.items import ScholarItem

class SclsSpiderSpider(scrapy.Spider):
    name = "scls_spider"
    allowed_domains = ["scls.hust.edu.vn"]
    start_urls = ["https://scls.hust.edu.vn/vi/organs/"]

    custom_settings = {
        "LOG_FILE":f"f:/science_data_warehouse_repo/output/hust/scls/logs/scls_{timestamp}.log",
        "LOG_LEVEL":"INFO",
        "FEEDS":{
            f"f:/science_data_warehouse_repo/output/hust/scls/data/scls.csv":{
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
            "ho_ten",
            "chuc_vu",
            "don_vi",
            "email",
            "dien_thoai",
            "nhom_chuyen_mon",
            "dao_tao",
            "cong_tac",
            "giang_day",
            "linh_vuc_nghien_cuu",
            "dt_chu_nhiem",
            "dt_tham_gia",
            "dt_giai_thuong",
            "dt_sang_che_shtt",
            "ct_tap_chi_khoa_hoc",
            "ct_chuong_sach",
            "thanh_vien",
            "to_chuc",
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
        scholars = response.css('table.table-striped h3.font-size-h3 a::attr(href)').getall()
        for scholar in scholars:
            yield response.follow(
                scholar,
                callback = self.parse_scholar,
                dont_filter=True
            )

    def parse_scholar(self, response):
        url = response.url
        ho_ten = response.xpath('//b[contains(text(), "Họ tên")]/following-sibling::text()').get()
        chuc_vu = response.xpath('//b[contains(text(), "Chức vụ")]/following-sibling::text()').get(default='').strip()
        don_vi = response.xpath('//b[contains(text(), "Thuộc đơn vị")]/following-sibling::a/text()').get(default='').strip()
        email = response.xpath('//b[contains(text(), "Địa chỉ email")]/following-sibling::a/text()').get(default='').strip()
        dien_thoai = response.xpath('//b[contains(text(), "Điện thoại")]/following-sibling::text()').get(default='').strip()
        nhom_chuyen_mon = response.xpath('//b[contains(text(), "Nhóm chuyên môn")]/following-sibling::text()').get(default='').strip()

        dao_tao = [li.xpath('string(.)').get().strip() for li in response.xpath('//h2[contains(string(.), "ĐÀO TẠO")]/following-sibling::ul[1]/li')]
        cong_tac = [li.xpath('string(.)').get().strip() for li in response.xpath('//h2[contains(string(.), "QUÁ TRÌNH CÔNG TÁC")]/following-sibling::ul[1]/li')]

        giang_day = [li.xpath('string(.)').get().strip() for li in response.xpath('//h2[contains(string(.), "GIẢNG DẠY")]/following-sibling::ul[1]/li')]
        linh_vuc_nghien_cuu = [li.xpath('string(.)').get().strip() for li in response.xpath('//h2[contains(string(.), "LĨNH VỰC NGHIÊN CỨU")]/following-sibling::ul[1]/li')]

        dt_chu_nhiem = [li.xpath('string(.)').get().strip() for li in response.xpath('//h3[contains(string(.), "Chủ nhiệm")]/following-sibling::ul[1]/li')]
        dt_tham_gia = [li.xpath('string(.)').get().strip() for li in response.xpath('//h3[contains(string(.), "Tham gia")]/following-sibling::ul[1]/li')]
        dt_giai_thuong = [li.xpath('string(.)').get().strip() for li in response.xpath('//h3[contains(string(.), "Giải thưởng")]/following-sibling::ul[1]/li')]
        dt_sang_che_shtt = [li.xpath('string(.)').get().strip() for li in response.xpath('//h3[contains(string(.), "Sáng chế và Giải pháp hữu ích")]/following-sibling::ul[1]/li')]

        ct_tap_chi_khoa_hoc = [li.xpath('string(.)').get().strip() for li in response.xpath('//h3[contains(string(.), "Tạp chí khoa học")]/following-sibling::*[self::ul or self::ol][1]/li')]
        ct_chuong_sach = [li.xpath('string(.)').get().strip() for li in response.xpath('//h3[contains(string(.), "Chương sách")]/following-sibling::*[self::ul or self::ol][1]/li')]

        thanh_vien = [li.xpath('string(.)').get().strip() for li in response.xpath('//h3[contains(string(.), "Thành viên")]/following-sibling::ul[1]/li')]
        to_chuc = [li.xpath('string(.)').get().strip() for li in response.xpath('//h3[contains(string(.), "Tổ chức")]/following-sibling::ul[1]/li')]

        dai_hoc = 'Đại học Bách Khoa Hà Nội'
        don_vi_truc_thuoc = "Trường Hóa và Khoa học sự sống"

        yield {
            "url": url,
            "ho_ten": ho_ten,
            "chuc_vu": chuc_vu,
            "don_vi": don_vi,
            "email": email,
            "dien_thoai": dien_thoai,
            "nhom_chuyen_mon":nhom_chuyen_mon,
            "dao_tao":dao_tao,
            "cong_tac":cong_tac,
            "giang_day":giang_day,
            "linh_vuc_nghien_cuu":linh_vuc_nghien_cuu,
            "dt_chu_nhiem":dt_chu_nhiem,
            "dt_tham_gia":dt_tham_gia,
            "dt_giai_thuong":dt_giai_thuong,
            "dt_sang_che_shtt":dt_sang_che_shtt,
            "ct_tap_chi_khoa_hoc":ct_tap_chi_khoa_hoc,
            "ct_chuong_sach":ct_chuong_sach,
            "thanh_vien":thanh_vien,
            "to_chuc":to_chuc,
            "dai_hoc":dai_hoc,
            "don_vi_truc_thuoc":don_vi_truc_thuoc
        }