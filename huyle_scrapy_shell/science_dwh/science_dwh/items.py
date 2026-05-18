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
    # hust
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

class sme_item(scrapy.Item):
    url = scrapy.Field()
    ho_ten = scrapy.Field()
    chuc_vu = scrapy.Field()
    chuc_danh_kiem_nhiem = scrapy.Field()
    don_vi = scrapy.Field()
    email = scrapy.Field()
    nhom_chuyen_mon = scrapy.Field()
    dia_chi_lam_viec = scrapy.Field()
    cac_mon_giang_day = scrapy.Field()
    linh_vuc_nghien_cuu = scrapy.Field()
    qua_trinh_dao_tao = scrapy.Field()
    cong_trinh_tieu_bieu = scrapy.Field()
    du_an_hien_tai = scrapy.Field()
    hv_cao_hoc = scrapy.Field()
    ncs_phd = scrapy.Field()
    sach = scrapy.Field()
    giai_thuong = scrapy.Field()
    hop_tac_chuyen_giao = scrapy.Field()
    thong_tin_khac = scrapy.Field()
    dai_hoc = scrapy.Field()
    don_vi_truc_thuoc = scrapy.Field()

class soict_item(scrapy.Item):
    url = scrapy.Field()
    ho_ten = scrapy.Field()
    gioi_thieu = scrapy.Field()
    vi_tri = scrapy.Field()
    chuc_vu = scrapy.Field()
    hoc_ham_hoc_vi = scrapy.Field()
    qua_trinh_dao_tao = scrapy.Field()
    email = scrapy.Field()
    linh_vuc_nghien_cuu = scrapy.Field()
    nghien_cuu_quan_tam = scrapy.Field()
    du_an_hien_tai = scrapy.Field()
    cong_trinh_tieu_bieu = scrapy.Field()
    giai_thuong_khen_thuong = scrapy.Field()
    cac_mon_giang_day = scrapy.Field()