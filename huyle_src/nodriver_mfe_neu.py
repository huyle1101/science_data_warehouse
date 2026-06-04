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

OUTPUT_DIR = 'f:/science_data_warehouse_repo/output/neu/mfe/raw_data'
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, f"mfe_{timestamp}.jsonl")

LOG_DIR = 'f:/science_data_warehouse_repo/output/neu/mfe/logs'
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"mfe_{timestamp}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger()

LISTING_URL = "https://mfe.neu.edu.vn/thanh-vien/giang-vien-can-bo/"

async def human_sleep(min_s=1.0, max_s=3.0):
    await asyncio.sleep(random.uniform(min_s, max_s))


# get all scholar profile links from listing page
async def scrape_listing_page(tab) -> list:
    js_code = """
        Array.from(document.querySelectorAll('p a'))
            .map(a => a.getAttribute('href'))
            .filter(href => href !== null && href.startsWith('http://mfe.edu.vn/'));
    """

    href = await tab.evaluate(js_code)
    l = list(set([item['value'] for item in href if 'value' in item]))
    log.info(f"Get {len(l)} links from listing page.")

    return l

# extract text content from the main table in the scholar profile page
async def extract_information(tab) -> dict:
    data_dict = {}

    get_avt_url_js = """
        (() => {
            const imgElement = document.querySelector('div.col-inner img');
            if (!imgElement) return null;
            return imgElement.getAttribute('src');
        })()
    """

    get_personal_info_js = """
        (() => {
            const el = document.querySelectorAll('div.medium-12')[0];
            return el ? el.innerText.trim() : null;
        })()
    """

    get_html_text_js = """
        (() => {
            const el = document.querySelectorAll('div.medium-12')[1];
            return el ? el.innerText.trim() : null;
        })()
    """

    avt_url = await tab.evaluate(get_avt_url_js)
    data_dict['avt_url'] = avt_url if avt_url else None

    personal_info_text = await tab.evaluate(get_personal_info_js)
    data_dict['personal_info_text'] = personal_info_text if personal_info_text else None

    html_text = await tab.evaluate(get_html_text_js)
    data_dict['html_text'] = html_text if html_text else None

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

    
    scholars = []
    scholars.extend(await scrape_listing_page(tab)) # first page
    log.info(f"Found {len(scholars)} scholar links on page 1.")

    log.info(f"Found total {len(scholars)} scholar links to process.")

    for url in scholars:
        try:
            await tab.get(url)
            await human_sleep(1.5, 3.0)


            record = await extract_information(tab)
            record['url'] = url
            record['dai_hoc'] = 'Đại học Kinh tế quốc dân'
            record['don_vi_truc_thuoc'] = 'Khoa Toán kinh tế - Trường Công nghệ'
            record['is_extracted'] = True
            record['thong_tin_khong_cong_bo'] = False
            record['is_checked'] = False

            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
            log.info(f"Saved: {record.get('url')} to {OUTPUT_FILE}")
        except Exception as e:
            log.warning(f"Error processing {url}: {e}")
    
    log.info("Finished, total running time: {:.2f} seconds".format(time.time() - script_start_time))
    # await browser.stop()

uc.loop().run_until_complete(main())