# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

from urllib import response

import scrapy


class ScienceDWHItem(scrapy.Item):
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

    # scls
    url = scrapy.Field()
    ho_ten = scrapy.Field()
    chuc_vu = scrapy.Field()
    don_vi = scrapy.Field()
    email = scrapy.Field()
    dien_thoai = scrapy.Field()
    nhom_chuyen_mon = scrapy.Field()
    dao_tao = scrapy.Field()
    cong_tac = scrapy.Field()
    giang_day = scrapy.Field()
    linh_vuc_nghien_cuu = scrapy.Field()
    dt_chu_nhiem = scrapy.Field()
    dt_tham_gia = scrapy.Field()
    dt_giai_thuong = scrapy.Field()
    dt_sang_che_shtt = scrapy.Field()
    ct_tap_chi_khoa_hoc = scrapy.Field()
    ct_chuong_sach = scrapy.Field()
    thanh_vien = scrapy.Field()
    to_chuc = scrapy.Field()
    dai_hoc = scrapy.Field()
    don_vi_truc_thuoc = scrapy.Field()