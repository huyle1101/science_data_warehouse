import scrapy
import scrapling


class SclsSpiderSpider(scrapy.Spider):
    name = "scls_spider"
    allowed_domains = ["scls.hust.edu.vn"]
    start_urls = ["https://scls.hust.edu.vn/"]


    def parse(self, response):
        pass
