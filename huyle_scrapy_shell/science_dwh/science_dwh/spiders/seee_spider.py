import scrapy


class SeeeSpiderSpider(scrapy.Spider):
    name = "seee_spider"
    allowed_domains = ["seee.hust.edu.vn"]
    start_urls = ["https://seee.hust.edu.vn/vi/suborgans/vieworg/Khoa-Dien-3/"]

    def parse(self, response):
        scholas = response.css('div.height-col div.caption h3 a::attr(href)').getall()
        for scholar in scholars:
            yield response.follow(
                scholar,
                callback = self.parse_scholar,
                # dont_filter=True
            )
        
        next_page_url = response.css('ul.pagination li:last-child a::attr(href)').get()
        if next_page_url:
            yield response.follow(next_page_url, callback=self.parse)
    
    def parse_scholar(self, response):
        url = response.url
        ho_ten = response.xpath('normalize-space(//p[b[contains(text(), "Họ tên")]]/text())').get()
        chuc_vu = response.xpath('normalize-space(//p[b[contains(text(), "Chức vụ")]]/text())').get()
        thuoc_don_vi = response.xpath('normalize-space(//p[b[contains(text(), "Thuộc đơn vị")]]/a/text())').get()
        email = response.xpath('normalize-space(//p[b[contains(text(), "Địa chỉ email")]]/a/text())').get()
        cac_cong_trinh_khoa_hoc_tieu_bieu = [
            text.strip() for text in response.xpath(
                '//tr[preceding-sibling::tr[td/h1/span][1]/td/h1/span[contains(text(), "CÁC CÔNG TRÌNH KHOA HỌC TIÊU BIỂU")]]//li//text()'
            ).getall() if text.strip()
        ]

        giang_day = [
            text.strip() for text in response.xpath(
                '//tr[preceding-sibling::tr[td/h1/span][1]/td/h1/span[contains(text(), "GIẢNG DẠY")]]//li//text()'
            ).getall() if text.strip()
        ]

        linh_vuc_nghien_cuu = [
            text.strip() for text in response.xpath(
                '//tr[preceding-sibling::tr[td/h1/span][1]/td/h1/span[contains(text(), "LĨNH VỰC NGHIÊN CỨU")]]//li//text()'
            ).getall() if text.strip()
        ]

        nhom_chuyen_mon = [
            text.strip() for text in response.xpath(
                '//tr[preceding-sibling::tr[td/h1/span][1]/td/h1/span[contains(text(), "NHÓM CHUYÊN MÔN")]]//li//text()'
            ).getall() if text.strip()
        ]

        lab_nghien_cuu = [
            text.strip() for text in response.xpath(
                '//tr[preceding-sibling::tr[td/h1/span][1]/td/h1/span[contains(text(), "LAB NGHIÊN CỨU")]]//li//text()'
            ).getall() if text.strip()
        ]
