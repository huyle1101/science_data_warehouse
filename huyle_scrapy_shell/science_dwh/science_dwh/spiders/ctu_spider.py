import scrapy
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
import re
from science_dwh.items import ctu_item
import json

class CtuSpiderSpider(scrapy.Spider):
    name = "ctu_spider"
    allowed_domains = ["www.ctu.edu.vn", "qldiem.ctu.edu.vn"]
    start_urls = ["https://www.ctu.edu.vn/webctu_staff/staff.php"]

    custom_settings = {
        "LOG_FILE":f"f:/science_data_warehouse_repo/output/ctu/logs/ctu_{timestamp}.log",
        "LOG_LEVEL":"INFO",
        "FEEDS":{
            f"f:/science_data_warehouse_repo/output/ctu/raw_data/ctu.jsonl":{
                'format':'jsonlines',
                "encoding": "utf8",
                "overwrite": False # append mode
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
        
        # increase AUTOTHROTTLE_TARGET_CONCURRENCY along with CONCURRENT_REQUESTS_PER_DOMAIN, or AUTOTHROTTLE_TARGET_CONCURRENCY
        # will limit number of requests

        # "DELTAFETCH_ITEM_BASED":False,
        
        "FEED_EXPORT_FIELDS": [
            'url',
            'ho_ten',
            'gioi_tinh',
            'email',
            'chuc_vu',
            'trinh_do_chuyen_mon',
            'hoc_ham',
            'don_vi',
            'de_tai_nckh_da_thuc_hien',
            'sach_va_giao_trinh_xuat_ban',
            'cong_trinh_nckh_da_cong_bo',
            "thong_tin_khong_cong_bo",
            "is_extracted",
            "is_checked"
        ]
    }

    def filter_valid_profile_links(self, links: list):
        pattern = re.compile(r'^https://qldiem\.ctu\.edu\.vn/htql/canbo/llkh/codes/LyLichKhoaHoc_in\.php\?macb=\d+')
        return [link for link in links if pattern.match(link)]

    def get_personal_information(self, response, information):
        data= response.xpath(f'//td[contains(text(), "{information}")]/text()').get().strip()
        return data.strip() if data else ""

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
        links = response.css('div.art-article a::attr(href)').getall()
        scholars = self.filter_valid_profile_links(links)
        for scholar in scholars:
            # req = response.follow(
            #     scholar,
            #     callback = self.parse_scholar,
            #     # dont_filter=True
            # )
            yield response.follow(
                scholar,
                callback = self.parse_scholar,
                # dont_filter=True
            )
            # save scholar link in deltafetch to avoid mismatching url caused by redirection
            # req.meta['deltafetch_key'] = scholar
            # yield req
        next_page_relative = response.xpath('//font[@class="page-select"]/following-sibling::a[1]/@href').get()
        if next_page_relative is not None:
            next_page_url = response.urljoin(next_page_relative)
            yield response.follow(next_page_url, callback=self.parse)
        
        # for i in range(1,23):
        #     next_page_url = f"https://www.ctu.edu.vn/webctu_staff/staff.php?page={i}"
        #     if next_page_url:
        #         yield response.follow(next_page_url, callback=self.parse)

    def parse_scholar(self, response):

        item = ctu_item()
        item['url'] = response.url
        item['ho_ten'] = response.xpath('//td[contains(text(), "Họ và tên")]/b/text()').get().strip()
        item['gioi_tinh'] = self.get_personal_information(response, "Giới tính").split()[-1]
        item['email'] = self.get_personal_information(response, "Email").split()[-1]
        item['chuc_vu'] = self.get_personal_information(response, "Ngạch viên chức")
        item['trinh_do_chuyen_mon'] = self.get_personal_information(response, "Trình độ chuyên môn")
        item['hoc_ham'] = self.get_personal_information(response, "Học hàm")
        item['don_vi'] = self.get_personal_information(response, "Đơn vị công tác")

        item['de_tai_nckh_da_thuc_hien'] = []
        table = response.xpath('//div[contains(text(), "Các đề tài nghiên cứu khoa học đã thực hiện")]/following-sibling::table[1]')
        for row in table.xpath('.//tr[position()>1]'):
            cols = []
            for td in row.xpath('.//td'):
                raw_text = " ".join(td.xpath('.//text()').getall())
                clean_text = " ".join(raw_text.split())
                cols.append(clean_text)
            if len(cols) >= 4:
                ten_de_tai = cols[1]
                nam_hoan_thanh = cols[2]
                cap_quan_ly = cols[3]
                vai_tro = cols[4] if len(cols) >= 5 else ""
                
                fields = [ten_de_tai, nam_hoan_thanh, cap_quan_ly, vai_tro]
                valid_fields = [f for f in fields if f]
                joined_row_value = " - ".join(valid_fields)
                
                item['de_tai_nckh_da_thuc_hien'].append(joined_row_value)

        
        item['sach_va_giao_trinh_xuat_ban'] = []
        table = response.xpath('//div[contains(text(), "Sách và giáo trình xuất bản")]/following-sibling::table[1]')
        for row in table.xpath('.//tr[contains(@class, "clsSachGiaoTrinh")]'):
            cols = []
            for td in row.xpath('.//td'):
                raw_text = " ".join(td.xpath('.//text()').getall())
                clean_text = " ".join(raw_text.split())
                cols.append(clean_text)
            if len(cols) >= 4:
                ten_sach = cols[1]
                nha_xuat_ban = cols[2]
                nam_xuat_ban = cols[3]
                
                fields = [ten_sach, nha_xuat_ban, nam_xuat_ban]
                
                valid_fields = [f for f in fields if f]
                
                joined_row_value = " - ".join(valid_fields)
                
                item['sach_va_giao_trinh_xuat_ban'].append(joined_row_value)


        item['cong_trinh_nckh_da_cong_bo'] = []
        table = response.xpath('//div[contains(text(), "Các công trình nghiên cứu khoa học đã công bố")]/following-sibling::table[1]')

        for row in table.xpath('.//tr'):
            raw_text = "".join(row.xpath('.//text()').getall())
            clean_text = " ".join(raw_text.replace('\xa0', ' ').split())

            if clean_text:
                item['cong_trinh_nckh_da_cong_bo'].append(clean_text)
        
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