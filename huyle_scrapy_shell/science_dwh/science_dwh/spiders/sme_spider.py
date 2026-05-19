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
            'ho_ten',
            'chuc_vu',
            'chuc_danh_kiem_nhiem',
            'don_vi',
            'email',
            'nhom_chuyen_mon',
            'dia_chi_lam_viec',
            'cac_mon_giang_day',
            'linh_vuc_nghien_cuu',
            'qua_trinh_dao_tao',
            'cong_trinh_tieu_bieu',
            'du_an_hien_tai',
            'hv_cao_hoc',
            'ncs_phd',
            'sach',
            'giai_thuong',
            'hop_tac_chuyen_giao',
            'thong_tin_khac',
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
        item = sme_item() # don't use sme_item = sme_item() which creates an instance at the class level and causes data overwriting across items, instead create a new instance for each item in the parse method.
        url = response.url

        # normalize space to ignore case and extra whitespace, then split by first colon to get value
        item['ho_ten'] = response.xpath('normalize-space(//*[contains(text(), "Họ tên")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['chuc_vu'] = response.xpath('normalize-space(//*[contains(text(), "Chức vụ")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['vi_tri'] = response.xpath('normalize-space(//*[contains(text(), "Chức danh kiêm nhiệm")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['don_vi'] = response.xpath('normalize-space(//*[contains(text(), "Thuộc đơn vị")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['email'] = response.xpath('normalize-space(//*[contains(text(), "Địa chỉ email")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['dai_hoc'] = 'Đại học Bách Khoa Hà Nội'
        item['don_vi_truc_thuoc'] = 'Trường Cơ khí'
        
        
        
        
        dia_chi_lam_viec = response.xpath('//strong[contains(text(), "Địa chỉ làm việc")]/following-sibling::text()').get()
        nhom_chuyen_mon = response.xpath('//b[contains(text(), "Nhóm chuyên môn")]/following-sibling::text()').get()
        mon_giang_day = response.xpath('//b[contains(text(), "Các môn giảng dạy")]/following-sibling::text()').get() # following-sbling ->  get text of tags after and outside of <b> tag, not inside <b> tag

        # find the first <ul> element that follows the <p> element containing "Các nghiên cứu quan tâm", then get all <li> elements inside that <ul>
        for tag in ['p','strong']:
            xpath_lvnc = f'//{tag}[contains(., "Các nghiên cứu quan tâm") or contains(., "Lĩnh vực nghiên cứu/Research Arears") or contains(., "Hướng nghiên cứu")]/following-sibling::ul[1]/li'
            li_elements_lvnc = response.xpath(xpath_lvnc)
            linh_vuc_nghien_cuu = [" ".join(li.xpath('.//text()').getall()).strip() for li in li_elements_lvnc]
            if linh_vuc_nghien_cuu: # if found the research areas, no need to check other tags to prevent data overwriting, if not found, continue to check other tags
                break

        li_elements_qtdt = response.xpath('//p[contains(., "Đào tạo")]/following-sibling::ul[1]/li')
        qua_trinh_dao_tao = [" ".join(li.xpath('.//text()').getall()).strip() for li in li_elements_qtdt]

        
        li_elements_ctkh = response.xpath('//p[contains(., "Các công trình khoa học tiêu biểu")]/following-sibling::ul[1]/li')
        cong_trinh_tieu_bieu = [" ".join(li.xpath('.//text()').getall()).strip() for li in li_elements_ctkh]



        item['dia_chi_lam_viec'] = dia_chi_lam_viec
        item['nhom_chuyen_mon'] = nhom_chuyen_mon
        item['cac_mon_giang_day'] = mon_giang_day
        item['linh_vuc_nghien_cuu'] = linh_vuc_nghien_cuu
        item['qua_trinh_dao_tao'] = qua_trinh_dao_tao
        item['cong_trinh_tieu_bieu'] = cong_trinh_tieu_bieu
        item['du_an_hien_tai'] = du_an_hien_tai
        item['hv_cao_hoc'] = hv_cao_hoc
        item['ncs_phd'] = ncs_phd
        item['sach'] = sach
        item['giai_thuong'] = giai_thuong
        item['hop_tac_chuyen_giao'] = hop_tac_chuyen_giao
        item['thong_tin_khac'] = thong_tin_khac
        item['dai_hoc'] = dai_hoc
        item['don_vi_truc_thuoc'] = don_vi_truc_thuoc

        yield item