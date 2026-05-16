# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class DwhScholarItem(scrapy.Item):
    # define the fields for your item here like:
    # name = scrapy.Field()
    pass

class ScholarItem(scrapy.Item):
    # soict
    url = scrapy.Field()
    name = scrapy.Field()
    email = scrapy.Field()
    position = scrapy.Field()
    academic_title = scrapy.Field()
    education = scrapy.Field()
    research_fields = scrapy.Field()
    interested_research_fields = scrapy.Field()
    publications = scrapy.Field()
    awards = scrapy.Field()
    subjects = scrapy.Field()
    projects = scrapy.Field()