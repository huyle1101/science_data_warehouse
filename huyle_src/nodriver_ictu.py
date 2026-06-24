import nodriver as uc
import asyncio
import json
import os
import time
import logging
import random
from datetime import datetime

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
script_start_time = time.time()

OUTPUT_DIR = 'f:/science_data_warehouse_repo/output/tnu/ictu/raw_data'
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, f"ictu_{timestamp}.jsonl")

LOG_DIR = 'f:/science_data_warehouse_repo/output/tnu/ictu/logs'
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"ictu_{timestamp}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger()

LISTING_URL = "https://repository.ictu.edu.vn/giang-vien/"

async def human_sleep(min_s=1.0, max_s=3.0):
    await asyncio.sleep(random.uniform(min_s, max_s))


# get all scholar profile links from listing page
async def scrape_listing_page(tab) -> list:
    cards = await tab.evaluate("""
        Array.from(document.querySelectorAll('a.gv-detail-link')).map(a => a.href)
    """)
    
    l = list(set([item['value'] for item in cards]))
    return l

# extract text content from the main table in the scholar profile page
async def extract_information(tab) -> dict:
    data_dict = {}
    name_el = await tab.select('h1.gv-profile-name')
    data_dict['ho_ten'] = name_el.text if name_el else None

    spec_el = await tab.select('p.gv-profile-spec')
    data_dict['nhom_chuyen_mon'] = spec_el.text if spec_el else None

    email_el = await tab.select('a[href^="mailto:"]')
    data_dict['email'] = email_el.text if email_el else None

    phone_el = await tab.select('a[href^="tel:"]')
    data_dict['so_dien_thoai'] = phone_el.text if phone_el else None

    orcid_el = await tab.select('a[href*="orcid.org"]')
    data_dict['orcid_link'] = orcid_el.attrs.get('href') if orcid_el else None

    scholar_el = await tab.select('a[href*="scholar.google.com"]')
    data_dict['scholar_link'] = scholar_el.attrs.get('href') if scholar_el else None
    
    avatar_el = await tab.select('img.gv-profile-avatar-img')
    data_dict['avatar_link'] = avatar_el.attrs.get('src') if avatar_el else None

    pub_els = await tab.select_all('.gv-pub-title a:first-of-type')

    data_dict['bai_bao'] = [
        {
            'title': el.text.strip() if el.text else None,
            'link': el.attrs.get('href')
        }
        for el in pub_els
    ] if pub_els else []

    # switch to other tab 
    all_tab_buttons = await tab.select_all('nav.dl-tabs button.dl-tab')
    if len(all_tab_buttons)>1:
        target_buttons = all_tab_buttons[1:] if all_tab_buttons else []
        
        
        for index, button in enumerate(target_buttons):
            await button.click()
            await human_sleep(3, 4)
            
            els = await tab.select_all('.gv-pub-title a:first-of-type')
            
            extracted_data = [
                {
                    'title': el.text.strip() if el.text else None,
                    'link': el.attrs.get('href')
                }
                for el in els
            ] if els else []
            
            if index == 0:
                data_dict['do_an'] = extracted_data
            elif index == 1:
                data_dict['luan_van_ths'] = extracted_data
            elif index == 2:
                data_dict['luan_an_ts'] = extracted_data
            elif index == 3:
                data_dict['hoc_lieu_so'] = extracted_data

    # log.info(data_dict)
    await tab.close()
    
    return data_dict

async def main():
    browser = await uc.start(
        headless=False,
        browser_args=[
            "--disable-blink-features=AutomationControlled",
        ],
        lang="vi-VN",
    )

    tab = browser.main_tab
    await tab.get(LISTING_URL)
    await human_sleep(2.0, 4.0)  # wait for page to load

    current_page=1
    while 1:
        scholars = []
        scholars.extend(await scrape_listing_page(tab)) # first page

        log.info(f"Found total {len(scholars)} scholar links to process.")

        for url in scholars:
            try:
                new_tab = await tab.get(url, new_tab=True)
                await human_sleep(1.5, 3.0)
                record = await extract_information(new_tab)
                record['url'] = url
                record['dai_hoc'] = 'Đại học Thái Nguyên'
                record['don_vi_truc_thuoc'] = 'Trường Công nghệ thông tin VÀ Truyền thông'
                record['is_extracted'] = True
                record['thong_tin_khong_cong_bo'] = False
                record['is_checked'] = False

                with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f.flush()
                log.info(f"Saved: {record.get('url')} to {OUTPUT_FILE}")
            except Exception as e:
                log.warning(f"Error processing {url}: {e}")
        next_btn = await tab.select('button[title="Trang tiếp"]')

        if next_btn:
            btn_classes = next_btn.attrs.get('class', '')
            is_disabled = 'disabled' in next_btn.attrs or 'disabled' in btn_classes or 'dl-pg-disabled' in btn_classes

            if not is_disabled:
                await next_btn.click()
                current_page+=1
                log.info(f"To next page, current_page={current_page}")
                await human_sleep(3,4)
                
            else:
                log.info("No more pages")
                break
        else:
            log.error('Next page button not found')
    
    log.info("Finished, total running time: {:.2f} seconds".format(time.time() - script_start_time))
    # await browser.stop()

uc.loop().run_until_complete(main())