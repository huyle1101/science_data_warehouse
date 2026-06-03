import nodriver as uc
import asyncio
import json
import os
import time
import logging
from datetime import datetime

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
script_start_time = time.time()

OUTPUT_DIR = 'f:/science_data_warehouse_repo/output/neu/saa/raw_data'
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, f"saa_{timestamp}.jsonl")

LOG_DIR = 'f:/science_data_warehouse_repo/output/neu/saa/logs'
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"saa_{timestamp}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger()

LISTING_URL = "https://saa.neu.edu.vn/giang-vien/"


async def human_sleep(min_s=1.0, max_s=3.0):
    import random
    await asyncio.sleep(random.uniform(min_s, max_s))

# get all scholar profile links from listing page
async def scrape_listing_page(tab) -> list:
    page = await tab.get(LISTING_URL)

    await tab.evaluate("window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })")
    await human_sleep(1.0, 3.0)

    # Use getAttribute to get raw string values, not a.href which nodriver wraps as CDP objects
    raw = await page.evaluate('''
        Array.from(document.querySelectorAll('.gsc-image-content .image > a'))
            .map(a => a.getAttribute('href'))
    ''')

    base = "https://saa.neu.edu.vn"
    links = []
    for item in raw:
        href = item['value'].strip()
        full_url = href if href.startswith('http') else base + href
        links.append(full_url)
    
    if len(links)>0:
        links[0] = 'https://saa.neu.edu.vn/gsts-nguyen-huu-anh.html' # fix the first link which is broken on the website
        return links
    log.info("No scholar links found on the listing page or the selector crashses")


# click on expansion contents to reveal data
async def scrape_scientific_data(page, tab_id: str) -> str:
    """
    tab_id is the HTML id of the tabcontent div:
      'tab2' -> Bài báo tạp chí khoa học
      'tab3' -> Bài tham luận hội thảo
      'tab4' -> Sách, giáo trình
      'tab5' -> Đề tài, dự án
      'tab6' -> Hướng dẫn NCS
      'tab7' -> Khen thưởng khoa học
    """
    js_script = f"""
        (() => {{
            // Find the tablink that opens this tab and click it
            const tabLinks = document.querySelectorAll('div.tab a.tablinks');
            for (let link of tabLinks) {{
                if (link.getAttribute('onclick') && link.getAttribute('onclick').includes('{tab_id}')) {{
                    link.click();
                    break;
                }}
            }}
            // Read directly by ID — no need to scan display style
            const content = document.getElementById('{tab_id}');
            return content ? content.innerText.trim() : "Không có dữ liệu";
        }})()
    """
    return await page.evaluate(js_script)


async def get_table_information(page) -> str:
    # Đoạn script JS dùng querySelector để tìm thẻ table nằm trong div có class 'col-md-9'
    js_code = '''
        (() => {
            // Tìm bảng dựa trên cấu trúc HTML ở ảnh 2
            const table = document.querySelector('div.col-md-9 table');
            // Trả về toàn bộ text của bảng, nếu không có bảng thì trả về null
            return table ? table.innerText.trim() : null;
        })()
    '''
    
    # Thực thi mã JS trên page
    infor = await page.evaluate(js_code)
    
    # Trả về kết quả
    return infor if infor else "Không có dữ liệu trên web"


async def scrape_detail_page(tab, url):

    try:
        await tab.get(url)
        await human_sleep(2, 3.5)

        # scroll down to load all content
        await tab.evaluate("window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })")
        await human_sleep(1.2, 2.0)
        await tab.evaluate("window.scrollTo({ top: 0, behavior: 'smooth' })")
        await human_sleep(0.5, 1.0)

        # expand all accordion / collapsible sections before scraping
        # await click_expand_sections(tab)
        
        # personal_infor = []
        # for i in ['họ tên', 'đơn vị công tác', 'chức vụ', 'chuyên ngành','lĩnh vực nghiên cứu', 'điện thoại', 'email']:
        #     personal_infor.append(await get_personal_information(tab, i))

        # 
        avt_url = await tab.evaluate('''
            (() => {
                const img = document.querySelector('.col-md-3 img');
                return img ? img.src : "Không tìm thấy ảnh";
            })()
        ''')
        
        tab_ids = ['tab2', 'tab3', 'tab4', 'tab5', 'tab6', 'tab7']
        scientific_data = []
        for tab_id in tab_ids:
            scientific_data.append(await scrape_scientific_data(tab, tab_id))

        bai_bao_tap_chi  = scientific_data[0]  # tab2
        bai_tham_luan    = scientific_data[1]  # tab3
        sach_giao_trinh  = scientific_data[2]  # tab4
        de_tai_du_an     = scientific_data[3]  # tab5
        huong_dan_ncs    = scientific_data[4]  # tab6
        khen_thuong      = scientific_data[5]  # tab7

        # ['họ tên', 'đơn vị công tác', 'chức vụ', 'chuyên ngành','lĩnh vực nghiên cứu', 'điện thoại', 'email']
        record = {
            "url":                     url,
            "avt_url":                 avt_url if isinstance(avt_url, str) else None,
            'thong_tin_ca_nhan':       await get_table_information(tab),
            "bai_bao_tap_chi_kh":      bai_bao_tap_chi,
            "tham_luan_hoi_thao":  bai_tham_luan,
            "sach_giao_trinh_an_pham": sach_giao_trinh,
            "de_tai_du_an_nhiem_vu":   de_tai_du_an,
            "huong_dan_ncs":           huong_dan_ncs,
            "khen_thuong_khoa_hoc":    khen_thuong,
            'dai_hoc': 'Đại học Kinh tế quốc dân',
            'don_vi_truc_thuoc': 'Viện Kế toán - Kiểm toán'
        }

        log.info(f"Scraped: {url}")
        return record

    except Exception as e:
        log.warning(f"Error scraping {url}: {e}")
        return None

# clean up the extracted data by unwrapping nodriver's CDP objects and dropping non-serializable fields
def sanitize(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and 'value' in value:
        return value['value']
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return None  # drop anything non-serializable

async def main():
    browser = await uc.start(
        headless=False,
        browser_args=[
            "--disable-blink-features=AutomationControlled",
        ],
        lang="vi-VN",
    )

    tab = browser.main_tab

    scholar_links = await scrape_listing_page(tab)
    log.info(f"Found {len(scholar_links)} scholar links to process.")
    
    for link in scholar_links:
        record = await scrape_detail_page(tab, link)
        if record is None:
            log.warning(f"Skipping {link} due to scrape error")
            continue

        record = {k: sanitize(v) for k, v in record.items()}

        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
        log.info(f"Saved: {record.get('url')} to {OUTPUT_FILE}")
        await human_sleep(1.5, 3.0)

    # for idx, item in enumerate(faculty_items):
    #     url  = item["href"]
    #     name = item["text"]
    #     log.info(f"[{idx+1}/{len(faculty_items)}] Processing: {name} | {url}")

    #     try:
    #         await tab.get(url)
    #         await human_sleep(1.5, 3.0)

    #         current_url = await tab.evaluate("window.location.href")
    #         page_title  = await tab.evaluate("document.title")

    #         record = await scrape_detail_page(tab, url)

    #         with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
    #             f.write(json.dumps(record, ensure_ascii=False) + "\n")
    #             f.flush()

    #         log.info(f"Saved: {record.get('ho_ten')} -> {OUTPUT_FILE}")

    #     except Exception as e:
    #         log.warning(f"Error processing {name} | {url}: {e}")

    #     await human_sleep(1.5, 3.0)

    log.info(f"Done. Total time: {time.time() - script_start_time:.1f}s")
    browser.stop()


uc.loop().run_until_complete(main())