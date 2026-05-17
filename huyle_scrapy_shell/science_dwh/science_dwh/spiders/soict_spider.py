import scrapy
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
from science_dwh.items import ScholarItem

class SoictSpiderSpider(scrapy.Spider):
    name = "soict_spider"
    allowed_domains = ["soict.hust.edu.vn"]
    start_urls = ["https://soict.hust.edu.vn/can-bo"]

    custom_settings = {
        
        "LOG_FILE":f"f:/science_data_warehouse_repo/output/hust/soict/logs/soict_{timestamp}.log",
        "LOG_LEVEL":"DEBUG",
        "FEEDS":{
            f"f:/science_data_warehouse_repo/output/hust/soict/data/soict_{timestamp}.csv":{
                'format':'csv',
                "encoding": "utf8"
            }
    },
        "CONCURRENT_REQUESTS" : 16,
        "CONCURRENT_REQUESTS_PER_DOMAIN" : 8,
        "DOWNLOAD_DELAY" : 1,
        "RANDOMIZED_DOWNLOAD_DELAY":True,
        "RETRY_ENABLED":True,
        "RETRY_TIMES": 5, 
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429, 403],
        "FEED_EXPORT_FIELDS": [ # columns to export in csv
            "url",
            "ho_ten",
            "email",
            "chuc_vu",
            "hoc_ham_hoc_vi",
            "qua_trinh_dao_tao",
            "linh_vuc_nghien_cuu",
            "linh_vuc_nghien_cuu_quan_tam",
            "cong_trinh_khoa_hoc_tieu_bieu",
            "giai_thuong_khen_thuong",
            "mon_hoc_giang_day",
            "du_an_hien_tai"
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
        # return links to scholar information
        scholars = response.css('h2.entry-title a::attr(href)').getall()
        for scholar in scholars:
            # go into each link
            yield response.follow(
                scholar,
                callback = self.parse_scholar,
                dont_filter=True
            )
        next_page_url = response.xpath('//ul[contains(@class, "page-numbers")]//a[contains(@class, "next")]/@href').get()
        # if not blank, go to next_page_url
        if next_page_url:
            yield response.follow(next_page_url, callback=self.parse)
    
    def parse_scholar(self, response):
        url = response.url

        name = response.css('span.breadcrumb_last::text').get()
        email = response.css('a[href^="mailto:"]::text').getall()

        # chức vụ - học hàm
        info_list = response.css('div.col-inner p:not(.lead) strong::text').getall()

        position = info_list[0] if len(info_list) > 0 else None
        academic_title = info_list[1] if len(info_list) > 1 else None

        # con đường học vấn
        raw_edu = response.css('div.col-inner p:nth-of-type(3)::text').getall()
        edu = raw_edu[:3]

        # lĩnh vực nghiên cứu
        research_fields = response.xpath('//h3[contains(., "Lĩnh vực nghiên cứu")]/parent::div/following-sibling::ul[1]/li/text()').getall()

        # nghiên cứu quan tâm
        interested_rs_fields = response.xpath('//h3[contains(., "Các nghiên cứu quan tâm")]/parent::div/following-sibling::ul[1]/li/text()').getall()

        # các công trình khoa học
        publications = [
            "".join(li.xpath('.//text()').getall()).strip() 
            for li in response.xpath('//h3[contains(., "Các công trình khoa học tiêu biểu")]/parent::div/following-sibling::ul[1]/li')
        ]

        # giải thưởng
        award = [
            "".join(li.xpath('.//text()').getall()).strip() 
            for li in response.xpath('//h3[contains(., "Giải thưởng, khen thưởng")]/parent::div/following-sibling::ul[1]/li')
        ]

        # các môn giảng dạy
        subjects = [
            "".join(li.xpath('.//text()').getall()).strip() 
            for li in response.xpath('//h3[contains(., "Giảng dạy")]/parent::div/following-sibling::ul[1]/li')
        ]

        # dự án hiện tại
        projects =[
            "".join(li.xpath('.//text()').getall()).strip() 
            for li in response.xpath('//h3[contains(., "Dự án hiện tại")]/parent::div/following-sibling::ul[1]/li')
        ]

        scholar_item = ScholarItem()
        scholar_item['url'] = url
        scholar_item['name'] = name
        scholar_item['email'] = email
        scholar_item['position'] = position
        scholar_item['academic_title'] = academic_title
        scholar_item['education'] = [e.strip() for e in edu if e.strip()]
        scholar_item['research_fields'] = [f.strip() for f in research_fields if f.strip()]
        scholar_item['interested_research_fields'] = [f.strip() for f in interested_rs_fields if f.strip()]
        scholar_item['publications'] = publications
        scholar_item['awards'] = award
        scholar_item['subjects'] = subjects
        scholar_item['projects'] = projects
        yield scholar_item