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
        url = response.url

        # normalize space to ignore case and extra whitespace, then split by first colon to get value
        ho_ten = response.xpath('normalize-space(//*[contains(text(), "Họ tên")]/parent::*)').get(default='').split(':', 1)[-1].strip()

        chuc_vu = response.xpath('normalize-space(//*[contains(text(), "Chức vụ")]/parent::*)').get(default='').split(':', 1)[-1].strip()

        chuc_danh_kiem_nhiem = response.xpath('normalize-space(//*[contains(text(), "Chức danh kiêm nhiệm")]/parent::*)').get(default='').split(':', 1)[-1].strip()

        don_vi = response.xpath('normalize-space(//*[contains(text(), "Thuộc đơn vị")]/parent::*)').get(default='').split(':', 1)[-1].strip()

        email = response.xpath('normalize-space(//*[contains(text(), "Địa chỉ email")]/parent::*)').get(default='').split(':', 1)[-1].strip()

        n_diachi = response.xpath('//*[contains(text(), "Địa chỉ làm việc") and not(*[contains(text(), "Địa chỉ làm việc")])]')
        dia_chi_lam_viec = n_diachi.xpath('following-sibling::text()[normalize-space()]').get(default='').strip() or n_diachi.xpath('normalize-space(.)').get(default='').split(':', 1)[-1].strip()
        dia_chi_lam_viec = dia_chi_lam_viec.lstrip(':').strip()

        nhom_chuyen_mon = response.xpath('normalize-space(//*[contains(text(), "Nhóm chuyên môn")]/parent::*)').get(default='').split(':', 1)[-1].strip()

        def extract_block_data(response, keywords):
            """Extract block data sequentially, handling unstructured HTML and messy input keywords."""
            if isinstance(keywords, str):
                keywords = [keywords] # ensure list format
                
            # tokenize and clean input keywords (handle slashes and messy spaces)
            clean_keywords = []
            for k in keywords:
                if not k.strip():
                    continue
                # split by slash if present to handle variations like "Sách/Books"
                sub_keywords = k.split('/') if '/' in k else [k]
                for sub_k in sub_keywords:
                    # clean all internal and external spaces, then lowercase
                    cleaned = " ".join(sub_k.split()).lower()
                    if cleaned:
                        clean_keywords.append(cleaned)

            if not clean_keywords:
                return []

            # find target heading
            potential_headings = response.xpath('//h2 | //h3 | //h4 | //h5 | //b | //strong | //p/b | //p/strong')
            
            target_heading = None
            for node in potential_headings:
                text = node.xpath('normalize-space(.)').get(default='').lower()
                
                # match keyword and title length
                if any(k in text for k in clean_keywords) and len(text) < 100:
                    # step up to parent <p>
                    if node.root.tag in ['b', 'strong'] and node.xpath('parent::p'):
                        target_heading = node.xpath('parent::p')[0]
                    else:
                        target_heading = node
                    break

            if not target_heading:
                return []

            # extract until next heading
            data_list = []
            
            # iterate siblings
            for sibling in target_heading.xpath('following-sibling::*'):
                sibling_text = sibling.xpath('normalize-space(.)').get(default='')
                
                # stop condition
                is_heading_tag = sibling.root.tag in ['h2', 'h3', 'h4', 'h5']
                is_bold_text = sibling.xpath('./b | ./strong') and len(sibling_text) < 100
                
                if sibling_text and (is_heading_tag or is_bold_text):
                    break 
                    
                # extraction logic
                if sibling.root.tag == 'table' or sibling.xpath('.//table'):
                    # handle tables
                    for row in sibling.xpath('.//tr'):
                        row_data = [" ".join(col.split()) for col in row.xpath('.//th//text() | .//td//text()').getall() if col.strip()]
                        if row_data:
                            data_list.append(" - ".join(row_data))
                            
                elif sibling.root.tag in ['ul', 'ol']:
                    # handle lists
                    data_list.extend([" ".join(x.split()) for x in sibling.xpath('.//li//text()').getall() if x.strip()])
                    
                else:
                    # handle free text
                    texts = sibling.xpath('.//text()').getall()
                    for t in texts:
                        clean_t = " ".join(t.split())
                        if clean_t:
                            data_list.append(clean_t) 

            # return unique items
            return list(dict.fromkeys(data_list))
        
        mon_giang_day = extract_block_data(response, ["Giảng dạy/Teaching", "Các môn giảng dạy"])
        linh_vuc_nghien_cuu = extract_block_data(response, ["Lĩnh vực nghiên cứu/Research Arears", "Các nghiên cứu quan tâm", "Lĩnh vực nghiên cứu"])
        cong_trinh_tieu_bieu = extract_block_data(response, ["Công trình tiêu biểu", "Công trình tiêu biểu/Selected publications", "Các công trình khoa học tiêu biểu"])
        qua_trinh_dao_tao = extract_block_data(response, ["Đào tạo/Educations","Quá trình đào tạo"])
        du_an_hien_tai = extract_block_data(response, ["Dự án hiện tại", "Dự án hiện tại /Projects"])
        hv_cao_hoc = extract_block_data(response, ["HV cao học/ Master students"])
        ncs_phd = extract_block_data(response, ["NCS/ PhD students"])
        sach = extract_block_data(response, ["Sách/Books", "Sách"])
        giai_thuong = extract_block_data(response, ["Giải thưởng/Awards & Honour", "Giải thưởng"])
        hop_tac_chuyen_giao = extract_block_data(response, ["Hợp tác chuyển giao công nghệ (Lab, Đại học, Doanh nghiệp)/ Coperation and Tech. Transfer (Labs., Uni., Companies)"])  
        thong_tin_khac = extract_block_data(response, ["Other information"])
        dai_hoc = 'Đại học Bách Khoa Hà Nội'
        don_vi_truc_thuoc = "Trường Cơ khí"

        yield {
            "url": url,
            'ho_ten': ho_ten,
            'chuc_vu': chuc_vu,
            'chuc_danh_kiem_nhiem': chuc_danh_kiem_nhiem,
            'don_vi': don_vi,
            'email': email,
            'nhom_chuyen_mon': nhom_chuyen_mon,
            'dia_chi_lam_viec': dia_chi_lam_viec,
            'cac_mon_giang_day': mon_giang_day,
            'linh_vuc_nghien_cuu': linh_vuc_nghien_cuu,
            'qua_trinh_dao_tao': qua_trinh_dao_tao,
            'cong_trinh_tieu_bieu': cong_trinh_tieu_bieu,
            'du_an_hien_tai': du_an_hien_tai,
            'hv_cao_hoc': hv_cao_hoc,
            'ncs_phd': ncs_phd,
            'sach': sach,
            'giai_thuong': giai_thuong,
            'hop_tac_chuyen_giao': hop_tac_chuyen_giao,
            'thong_tin_khac': thong_tin_khac,
            "dai_hoc":dai_hoc,
            "don_vi_truc_thuoc":don_vi_truc_thuoc
        }