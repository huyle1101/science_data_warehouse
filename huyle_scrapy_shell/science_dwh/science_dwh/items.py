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
    pass
    # # hust
    # # soict
    # url = scrapy.Field()
    # name = scrapy.Field()
    # email = scrapy.Field()
    # position = scrapy.Field()
    # academic_title = scrapy.Field()
    # education = scrapy.Field()
    # research_fields = scrapy.Field()
    # interested_research_fields = scrapy.Field()
    # publications = scrapy.Field()
    # awards = scrapy.Field()
    # subjects = scrapy.Field()
    # projects = scrapy.Field()

class sme_item(scrapy.Item):
    url = scrapy.Field()
    avt_url = scrapy.Field()
    ho_ten = scrapy.Field()
    chuc_vu = scrapy.Field()
    chuc_danh_kiem_nhiem = scrapy.Field()
    don_vi = scrapy.Field()
    email = scrapy.Field()
    nhom_chuyen_mon = scrapy.Field()
    dai_hoc = scrapy.Field()
    don_vi_truc_thuoc = scrapy.Field()
    html_text = scrapy.Field()
    thong_tin_khong_cong_bo = scrapy.Field()
    is_extracted = scrapy.Field()
    is_checked = scrapy.Field()

class soict_item(scrapy.Item):
    url = scrapy.Field()
    avt_url = scrapy.Field()
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
    html_text = scrapy.Field()
    thong_tin_khong_cong_bo = scrapy.Field()
    is_extracted= scrapy.Field()
    is_checked= scrapy.Field()
    dai_hoc = scrapy.Field()
    don_vi_truc_thuoc = scrapy.Field()

class scls_item(scrapy.Item):
    url = scrapy.Field()
    avt_url = scrapy.Field()
    ho_ten = scrapy.Field()
    chuc_vu = scrapy.Field()
    chuc_danh_kiem_nhiem = scrapy.Field()
    don_vi = scrapy.Field()
    email = scrapy.Field()
    nhom_chuyen_mon = scrapy.Field()
    dai_hoc = scrapy.Field()
    don_vi_truc_thuoc = scrapy.Field()
    html_text = scrapy.Field()
    thong_tin_khong_cong_bo = scrapy.Field()
    is_extracted = scrapy.Field()
    is_checked = scrapy.Field()

class seee_item(scrapy.Item):
    url = scrapy.Field()
    avt_url = scrapy.Field()
    ho_ten = scrapy.Field()
    chuc_vu = scrapy.Field()
    chuc_danh_kiem_nhiem = scrapy.Field()
    don_vi = scrapy.Field()
    nhom_nghien_cuu = scrapy.Field()
    html_text = scrapy.Field()
    gioi_thieu = scrapy.Field()
    cong_trinh_tieu_bieu = scrapy.Field()
    cac_mon_giang_day = scrapy.Field()
    linh_vuc_nghien_cuu = scrapy.Field()
    nhom_chuyen_mon = scrapy.Field()
    lab_nghien_cuu = scrapy.Field()
    dai_hoc = scrapy.Field()
    don_vi_truc_thuoc = scrapy.Field()

class ctu_item(scrapy.Item):
    url = scrapy.Field()
    # html_text = scrapy.Field()
    ho_ten = scrapy.Field()
    gioi_tinh = scrapy.Field()
    email = scrapy.Field()
    chuc_vu = scrapy.Field()
    trinh_do_chuyen_mon = scrapy.Field()
    hoc_ham = scrapy.Field()
    don_vi = scrapy.Field()
    de_tai_nckh_da_thuc_hien = scrapy.Field()
    sach_va_giao_trinh_xuat_ban = scrapy.Field()
    cong_trinh_nckh_da_cong_bo = scrapy.Field()