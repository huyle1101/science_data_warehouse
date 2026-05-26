from urllib import response
import re
import scrapy
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
from science_dwh.items import soict_item
import json

class SoictSpiderSpider(scrapy.Spider):
    name = "soict_spider"
    allowed_domains = ["soict.hust.edu.vn"]
    start_urls = ["https://soict.hust.edu.vn/can-bo"]

    custom_settings = {
        
        "LOG_FILE":f"f:/science_data_warehouse_repo/output/hust/soict/logs/soict_{timestamp}.log",
        "LOG_LEVEL":"INFO",
        "FEEDS":{
            f"f:/science_data_warehouse_repo/output/hust/soict/raw_data/soict_v3.csv":{
                'format':'csv',
                "encoding": "utf8",
                "overwrite": False
            }
    },
        "CONCURRENT_REQUESTS" : 32,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 16,
        "DOWNLOAD_DELAY" : 1,
        "RANDOMIZED_DOWNLOAD_DELAY":True, 

        "RETRY_ENABLED":True,
        "RETRY_TIMES": 10, 
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429, 403],

        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 5, # initial download delay
        "AUTOTHROTTLE_MAX_DELAY": 60, # maximum download delay to be set in case of high latencies
        "AUTOTHROTTLE_TARGET_CONCURRENCY"  : 10, # average number of requests Scrapy should be sending in parallel to each remote server
        
        "FEED_EXPORT_FIELDS": [ # columns to export in csv
            "url",
            "avt_url",
            "ho_ten",
            "html_text",
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
            "cac_mon_giang_day",
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
    
    def parse_scholar(self, response):
        item = soict_item()
        item['url'] = response.url
        item['avt_url'] = response.css('img.attachment-original::attr(data-lazy-src)').get()

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

        

        item['email'] = response.css('a[href^="mailto:"]::text').get()

        '''
        item['linh_vuc_nghien_cuu'] = response.xpath('//span[contains(text(), "Lĩnh vực nghiên cứu")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall()
        item['nghien_cuu_quan_tam'] = json.dumps(response.xpath('//span[contains(text(), "Các nghiên cứu quan tâm")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall(), ensure_ascii=False)

        section = response.xpath('(//span[contains(@class, "section-title-main") and contains(., "Các công trình")]/ancestor::div[contains(@class, "section-title-container")]/following-sibling::*[1])[1]', ensure_ascii=False)
        item['cong_trinh_tieu_bieu'] = json.dumps(section.xpath('.//li//text()').getall(), ensure_ascii=False)
        item['giai_thuong_khen_thuong'] = json.dumps(response.xpath('//span[contains(text(), "Giải thưởng, khen thưởng")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall(), ensure_ascii=False)
        item['cac_mon_giang_day'] = json.dumps(response.xpath('//span[contains(text(), "Giảng dạy")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall(), ensure_ascii=False)

        du_an_1 = response.xpath('//span[contains(text(), "Dự án hiện tại")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall()
        du_an_2 = response.xpath('//span[contains(text(), "Các dự án đang thực hiện")]/ancestor::div[1]/following-sibling::ol[1]/li//text()').getall()
        item['du_an_hien_tai'] = json.dumps(du_an_1, ensure_ascii=False) if du_an_1 else json.dumps(du_an_2, ensure_ascii=False)
        '''
        item['linh_vuc_nghien_cuu'] = " | ".join(response.xpath('//span[contains(text(), "Lĩnh vực nghiên cứu")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall())

        item['nghien_cuu_quan_tam'] = " | ".join(response.xpath('//span[contains(text(), "Các nghiên cứu quan tâm")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall())

        section = response.xpath('(//span[contains(@class, "section-title-main") and contains(., "Các công trình")]/ancestor::div[contains(@class, "section-title-container")]/following-sibling::*[1])[1]')
        item['cong_trinh_tieu_bieu'] = " | ".join(section.xpath('.//li//text()').getall())

        item['giai_thuong_khen_thuong'] = " | ".join(response.xpath('//span[contains(text(), "Giải thưởng, khen thưởng")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall())

        item['cac_mon_giang_day'] = " | ".join(response.xpath('//span[contains(text(), "Giảng dạy")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall())

        du_an_1 = response.xpath('//span[contains(text(), "Dự án hiện tại")]/ancestor::div[1]/following-sibling::ul[1]/li//text()').getall()
        du_an_2 = response.xpath('//span[contains(text(), "Các dự án đang thực hiện")]/ancestor::div[1]/following-sibling::ol[1]/li//text()').getall()
        item['du_an_hien_tai'] = " | ".join(du_an_1) if du_an_1 else " | ".join(du_an_2)

        list = response.css('div.entry-content ::text').getall()
        html_text = ' '.join(list)
        item['html_text'] = self.clean_html_text(html_text)


        yield item
    
    def closed(self, reason):
        # calculate coverage percentage and store in Dumping Scrapy stats
        stats = self.crawler.stats 

        crawled = stats.get_value('response_received_count', 0)
        scraped = stats.get_value('item_scraped_count', 0)

        if crawled > 0:
            coverage = (scraped / crawled) * 100
            stats.set_value('coverage_percent', round(coverage, 2))