import scrapy


class DhCanthoSpider(scrapy.Spider):
    name = "dh_cantho"
    allowed_domains = ["qldiem.ctu.edu.vn"]
    start_urls = ["https://qldiem.ctu.edu.vn/htql/quanly/llkhcongkhai/index.php"]

    def parse(self, response):
        
        donvi= response.css('select[name="cmbDonVi"].cbo#cmbDonVi option::text').getall()
        donvi=donvi[1:]
        madonvi=response.css('select[name="cmbDonVi"].cbo#cmbDonVi option::attr(value)').extract()
        madonvi=madonvi[1:]
        tongsogv=[]
        for i,j in zip(donvi,madonvi):
            
            yield scrapy.FormRequest(
            
                url=response.url,
                formdata={
                    'curPage': '1',
                    'NhanVien': '',
                    'Tam': '0',
                    'cmbDonVi': j,
                    'cmbBoMon': '%%',
                    'txtMaNhanVien': '',
                    'txtTenNhanVien': '',
                    'cmbHocHam': '',
                    'cmbHocVi': '',
                    'cmbChucDanh': '',
                    '__ncforminfo': response.css(
                        'input[name="__ncforminfo"]::attr(value)'
                    ).get()
                }
                ,callback=self.parse2,meta={"donvi":i,"madonvi":j}
            )
            
    def parse2(self,response):
        donvi=response.meta['donvi']
        madonvi=response.meta['madonvi']
        sotrang=[i for i in range(1,int(response.css('td[colspan="2"][align="right"][class="level_1_1"] font::text').get().split('/')[-1])+1) ]
        for i in sotrang:
            yield scrapy.FormRequest(
                url=response.url,
                formdata={
                    'curPage': str(i),
                    'NhanVien': '',
                    'Tam': '0',
                    'cmbDonVi': madonvi,
                    'cmbBoMon': '%%',
                    'txtMaNhanVien': '',
                    'txtTenNhanVien': '',
                    'cmbHocHam': '',
                    'cmbHocVi': '',
                    'cmbChucDanh': '',
                    '__ncforminfo': response.css(
                        'form[name="frmTDNhanVien"] input[name="__ncforminfo"]::attr(value)'
                    ).get()
                }
                ,callback=self.parse3,meta={"donvi":donvi,"madonvi":madonvi,"trang":i})
    def parse3(self,response):
        donvi=response.meta['donvi']
        madonvi=response.meta['madonvi']
        trang=response.meta['trang']
        macanbo= [i.strip() for i in response.css(
    'td.level_1_1[align="center"]:nth-child(2)::text, '
    'td.level_1_2[align="center"]:nth-child(2)::text'
).getall()]
        for i in macanbo:
            yield scrapy.FormRequest(
                        url="https://qldiem.ctu.edu.vn/htql/canbo/llkh/codes/LyLichKhoaHoc_in.php",
                        formdata={
                        "manvPrint":str(i),
                        "__ncforminfo": response.css(
                        'form[name="frmPrint"] input[name="__ncforminfo"]::attr(value)'
                ).get()},callback=self.parse4,meta={"donvi":donvi,"madonvi":madonvi,"trang":trang})
        
#             ten = response.css(
#     'td[style*="width:420px"] b::text'
# ).get()
#             yield ten
    def parse4(self,response):
        donvi=response.meta['donvi']
        madonvi=response.meta['madonvi']
        trang=response.meta['trang']
        ten = response.css(
        'td[style*="width:420px"] b::text'
    ).get()

        yield {
            
        "ten": ten,
        "donvi":donvi,
        "trang":trang        
    }
        

#         for i,j in zip(donvi,madonvi):
            
#             a= scrapy.FormRequest(
            
#                 url=response.url,
#                 formdata={
#                     'curPage': '1',
#                     'NhanVien': '',
#                     'Tam': '0',
#                     'cmbDonVi': j,
#                     'cmbBoMon': '%%',
#                     'txtMaNhanVien': '',
#                     'txtTenNhanVien': '',
#                     'cmbHocHam': '',
#                     'cmbHocVi': '',
#                     'cmbChucDanh': '',
#                     '__ncforminfo': response.css(
#                         'form[name="frmTDNhanVien"] input[name="__ncforminfo"]::attr(value)'
#                     ).get()
#                 })
#             fetch(a)
#             sotrang=[i for i in range(1,int(response.css('td[colspan="2"][align="right"][class="level_1_1"] font::text').get().split('/')[-1])+1) ]
#             for i in sotrang:
#                 trang=scrapy.FormRequest(
#                 url=response.url,
#                 formdata={
#                     'curPage': str(i),
#                     'NhanVien': '',
#                     'Tam': '0',
#                     'cmbDonVi': j,
#                     'cmbBoMon': '%%',
#                     'txtMaNhanVien': '',
#                     'txtTenNhanVien': '',
#                     'cmbHocHam': '',
#                     'cmbHocVi': '',
#                     'cmbChucDanh': '',
#                     '__ncforminfo': response.css(
#                         'form[name="frmTDNhanVien"] input[name="__ncforminfo"]::attr(value)'
#                     ).get()
#                 })
#                 fetch(trang)
#                 macanbo= [i.strip() for i in response.css('td.level_1_1[align="center"]:nth-child(2)::text,''td.level_1_2[align="center"]:nth-child(2)::text').getall()]
#                 for k in macanbo:
#                     b=scrapy.FormRequest(
#                         url="https://qldiem.ctu.edu.vn/htql/canbo/llkh/codes/LyLichKhoaHoc_in.php",
#                         formdata={
#                         "manvPrint":str(k),
#                         "__ncforminfo": response.css(
#                         'form[name="frmPrint"] input[name="__ncforminfo"]::attr(value)'
#                 ).get()})
#                     fetch(b)
#                     ten = response.css(
#     'td[style*="width:420px"] b::text'
# ).get()

#                 print(ten.strip())
                    
                

# # fetch(form)
# #                             )
                
# #     def parse2(self,response):
# #         donvi=response.meta['donvi']
# #         madonvi=response.meta['madonvi']
        
# #         danhsach = [i.strip() for i in response.css('td.level_1_1[align="center"]:nth-child(2)::text,td.level_1_2[align="center"]:nth-child(2)::text').getall()]
