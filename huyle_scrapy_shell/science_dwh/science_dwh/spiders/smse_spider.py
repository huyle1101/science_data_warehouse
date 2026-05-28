import scrapy
import os
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
from science_dwh.items import sme_item
import re

class SmseSpiderSpider(scrapy.Spider):
    name = "smse_spider"
    allowed_domains = ["smse.hust.edu.vn"]
    start_urls = ["https://smse.hust.edu.vn/"]

    LOG_DIR = f"f:/science_data_warehouse_repo/output/hust/smse/logs"
    OUTPUT_DIR = "f:/science_data_warehouse_repo/output/hust/smse/raw_data"
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)


    custom_settings = {
        "LOG_FILE": os.path.join(LOG_DIR, f"/smse_{timestamp}.log"),
        "LOG_LEVEL":"INFO",
        "FEEDS":{
            os.path.join(OUTPUT_DIR, "/sme.jsonl"):{
                'format':'jsonlines',
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
            "avt_url",
            'ho_ten',
            'chuc_vu',
            'chuc_danh_kiem_nhiem',
            'don_vi',
            'email',
            'nhom_chuyen_mon',
            "dai_hoc",
            "don_vi_truc_thuoc",
            "html_text",
            "thong_tin_khong_cong_bo",
            "is_extracted",
            "is_checked"
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

    def clean_html_text(html_text): 
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
        pass

    def parse_scholar(self, response):
        

        item['ho_ten'] = response.xpath('normalize-space(//*[contains(text(), "Họ tên")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['chuc_vu'] = response.xpath('normalize-space(//*[contains(text(), "Chức vụ")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['chuc_danh_kiem_nhiem'] = response.xpath('normalize-space(//*[contains(text(), "Chức danh kiêm nhiệm")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['don_vi'] = response.xpath('normalize-space(//*[contains(text(), "Thuộc đơn vị")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['email'] = response.xpath('normalize-space(//*[contains(text(), "Địa chỉ email")]/parent::*)').get(default='').split(':', 1)[-1].strip()
        item['nhom_chuyen_mon'] = response.xpath('//b[contains(text(), "Nhóm chuyên môn")]/following-sibling::text()').get()
        item['dai_hoc'] = 'Đại học Bách khoa Hà Nội'
        item['don_vi_truc_thuoc'] = 'Trường Vật liệu'

        # gt_1 = ' '.join(response.xpath('//h2[contains(., "Giới thiệu")]/following-sibling::div[1]//text()').getall()).strip()
        # gt_2 = ' '.join(response.xpath('//h2[contains(., "Giới thiệu")]/following-sibling::text()').getall()).strip()
        # if gt_1 != '':
        #     item['gioi_thieu'] = gt_1
        # else:
        #     item['gioi_thieu'] = gt_2

        # gd_list = response.xpath('//h2[contains(., "Các môn giảng dạy")]/following-sibling::*[preceding-sibling::h2[1][contains(., "Các môn giảng dạy")]]//text()').getall()
        # item['cac_mon_giang_day'] = [text.strip() for text in gd_list if text.strip()]

        # nc_list = response.xpath('//h2[contains(., "Lĩnh vực nghiên cứu")]/following-sibling::ul[1]//text()').getall()
        # item['linh_vuc_nghien_cuu'] = [text.strip() for text in nc_list if text.strip()]

        # dt_keywords = ["Một đề tài NCKH điển hình", "Một vài đề tài NCKH điển hình", "Dự án tiêu biểu", "Các công trình nghiên cứu"]
        # regex_pattern = "|".join(dt_keywords)
        # dt_list = response.xpath(f'//h3[re:test(., "{regex_pattern}", "i")]/following-sibling::ul[1]//text()').getall()
        # item['de_tai_nckh'] = [text.strip() for text in dt_list if text.strip()]

        # wos_list = response.xpath('//h3[contains(., "Tạp chí Web of Science")]/following-sibling::ol[1]//text()').getall()
        # item['tap_chi_web_of_science'] = [text.strip() for text in wos_list if text.strip()]

        # qt_list = response.xpath('//h3[contains(., "Tạp chí quốc tế")]/following-sibling::ol[1]//text()').getall()
        # item['tap_chi_quoc_te'] = [text.strip() for text in qt_list if text.strip()]
        
        # tn_list = response.xpath('//h3[contains(., "Tạp chí trong nước")]/following-sibling::ol[1]//text()').getall()
        # item['tap_chi_quoc_te'] = [text.strip() for text in tn_list if text.strip()]

        # sach_list = response.xpath('//h2[contains(., "Sách đã xuất bản")]/following-sibling::ul[1]//text()').getall()
        # item['sach_da_xuat_ban'] = [text.strip() for text in sach_list if text.strip()]

        # thanh_tich_list = response.xpath('//h3[contains(., "Thành tích, giải thưởng")]/following-sibling::ul[1]//text()').getall()
        # item['thanh_tich_giai_thuong'] = [text.strip() for text in thanh_tich_list if text.strip()]

        


        item['thong_tin_khong_cong_bo'] = False
        item['is_extracted'] = False
        item['is_checked'] = False

        yield item
