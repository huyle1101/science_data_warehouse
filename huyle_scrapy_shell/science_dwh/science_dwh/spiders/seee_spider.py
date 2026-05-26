import scrapy
from datetime import datetime
timestamp=datetime.now().strftime("%Y%m%d_%H%M%S")
import re
from science_dwh.items import seee_item

class SeeeSpiderSpider(scrapy.Spider):
    name = "seee_spider"
    allowed_domains = ["seee.hust.edu.vn"]
    start_urls = ["https://seee.hust.edu.vn/vi/suborgans/"]

    custom_settings = {
        "LOG_FILE":f"f:/science_data_warehouse_repo/output/hust/seee/logs/seee_{timestamp}.log",
        "LOG_LEVEL":"INFO",
        "FEEDS":{
            f"f:/science_data_warehouse_repo/output/hust/seee/raw_data/seee.csv":{
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
        "RETRY_TIMES": 3, 
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429, 403],

        # auto adjust speed of sending request based on the server response speed
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 5, # initial download delay
        "AUTOTHROTTLE_MAX_DELAY": 60, # maximum download delay to be set in case of high latencies
        "AUTOTHROTTLE_TARGET_CONCURRENCY"  : 1.0, # average number of requests Scrapy should be sending in parallel to each remote server

        "DNSCACHE_ENABLED" :True, # cache IP to improve speed

        "FEED_EXPORT_FIELDS": [
            'url',
            'avt_url',
            'ho_ten',
            'chuc_vu',
            'chuc_danh_kiem_nhiem',
            'don_vi',
            'html_text',
            'gioi_thieu',
            'cong_trinh_tieu_bieu',
            'cac_mon_giang_day',
            'linh_vuc_nghien_cuu',
            'nhom_chuyen_mon',
            'lab_nghien_cuu',
            'dai_hoc',
            'don_vi_truc_thuoc'
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

    # get sections of information with repeated format
    def get_information(self, response, information):
        header_tr = response.xpath(f'//span[contains(text(), "{information}")]/ancestor::tr')
        result_list = []
        following_trs = header_tr.xpath('following-sibling::tr')
        for tr in following_trs:
            if tr.xpath('.//h1'): # stop if goes to another section
                break
            texts = tr.xpath('.//li//text()').getall()
            clean_text = ' '.join([t.strip() for t in texts if t.strip()])
            if clean_text:
                result_list.append(clean_text)
        return result_list


    def parse(self, response):
        scholars = response.xpath('//table[contains(@class, "table")]//tr/td[2]/h3/a/@href').getall()
        for scholar in scholars:
            req = response.follow(
                scholar,
                callback = self.parse_scholar,
                # dont_filter=True
            )
            # save scholar link in deltafetch to avoid mismatching url caused by redirection
            req.meta['deltafetch_key'] = scholar
            yield req
        
    def parse_scholar(self, response):
    #     self.logger.info(
    #     f"URL: {response.url} | "
    #     f"deltafetch_key: {response.request.meta.get('deltafetch_key', 'NOT SET')}"
    # )
        item = seee_item()
        item['url'] = response.url

        relative_url = response.css('.flex-avatar img::attr(data-src)').get()
        item['avt_url'] = response.urljoin(relative_url)

        item['ho_ten'] = response.xpath('normalize-space(//*[contains(text(), "Họ tên")]/parent::*)').get(default='').split(':', 1)[-1].strip()

        item['chuc_vu'] = response.xpath('normalize-space(//*[contains(text(), "Chức vụ")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['chuc_danh_kiem_nhiem'] = response.xpath('normalize-space(//*[contains(text(), "Chức danh kiêm nhiệm")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['don_vi'] = response.xpath('normalize-space(//*[contains(text(), "Thuộc đơn vị")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        
        list = response.xpath('//h2[span[contains(text(), "Lý lịch khoa học")]]/following-sibling::div[contains(@class, "text-break")]//text()').getall()
        html_text = ' '.join(list)
        item['html_text'] = self.clean_html_text(html_text)
        item['gioi_thieu'] = response.xpath('//span[contains(text(), "GIỚI THIỆU")]/ancestor::tr/following-sibling::tr[1]//p//text()').getall()
        
        item['cong_trinh_tieu_bieu'] = self.get_information(response, "CÁC CÔNG TRÌNH KHOA HỌC TIÊU BIỂU")
        item['cac_mon_giang_day'] = self.get_information(response, "GIẢNG DẠY")
        item['linh_vuc_nghien_cuu'] = self.get_information(response, "LĨNH VỰC NGHIÊN CỨU")
        item['nhom_chuyen_mon'] = self.get_information(response, "NHÓM CHUYÊN MÔN")
        item['lab_nghien_cuu'] = self.get_information(response, "LAB NGHIÊN CỨU")
        item['dai_hoc'] = 'Đại học Bách Khoa Hà Nội'
        item['don_vi_truc_thuoc'] = 'Trường Điện - Điện tử'

        yield item

    def closed(self, reason):
        # calculate coverage percentage and store in Dumping Scrapy stats
        stats = self.crawler.stats 

        crawled = stats.get_value('response_received_count', 0)
        scraped = stats.get_value('item_scraped_count', 0)

        if crawled > 0:
            coverage = (scraped / crawled) * 100
            stats.set_value('coverage_percent', round(coverage, 2))