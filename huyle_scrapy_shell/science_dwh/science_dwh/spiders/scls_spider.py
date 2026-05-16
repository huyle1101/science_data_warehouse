import scrapy
from scrapling.fetchers import Fetcher, AsyncFetcher, StealthyFetcher, DynamicFetcher
StealthyFetcher.adaptive = True

class SclsSpiderSpider(scrapy.Spider):
    name = "scls_spider"
    allowed_domains = ["scls.hust.edu.vn"]
    start_urls = ["https://scls.hust.edu.vn/"]


    def parse(self, response):
        scholars = response.css('table.table-striped h3.font-size-h3 a::attr(href)').getall()
        for scholar in scholars:
            yield response.follow(
                scholar,
                callback = self.parse_scholar,
                dont_filter=True
            )

    def parse_scholar(self, response):
        ho_ten = response.xpath('//b[contains(text(), "Họ tên")]/following-sibling::text()').get()
        # email = response.css('div.font-size-h3 a::attr(href)').get()
        # position = response.css('div.font-size-h3::text').getall()[1].strip()
        # education = response.css('div.font-size-h3::text').getall()[2].strip()
        # research_fields = response.css('div.font-size-h3::text').getall()[3].strip()
        # interested_research_fields = response.css('div.font-size-h3::text').getall()[4].strip()
        # publications = response.css('div.font-size-h3::text').getall()[5].strip()
        # awards = response.css('div.font-size-h3::text').getall()[6].strip()
        # subjects = response.css('div.font-size-h3::text').getall()[7].strip()
        # projects = response.css('div.font-size-h3::text').getall()[8].strip()

        # yield {
        #     "url":response.url,
        #     "name":name,
        #     "email":email,
        #     "position":position,
        #     "education":education,
        #     "research_fields":research_fields,
        #     "interested_research_fields":interested_research_fields,
        #     "publications":publications,
        #     "awards":awards,
        #     "subjects":subjects,
        #     "projects":projects
        # }