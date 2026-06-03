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

OUTPUT_DIR = 'f:/science_data_warehouse_repo/output/neu/khpt/raw_data'
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, f"khpt_{timestamp}.jsonl")

LOG_DIR = 'f:/science_data_warehouse_repo/output/neu/khpt/logs'
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"khpt_{timestamp}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger()

LISTING_URL = "https://khoakhpt.neu.edu.vn/vi/khoi-giang-vien"

async def human_sleep(min_s=1.0, max_s=3.0):
    await asyncio.sleep(random.uniform(min_s, max_s))

def sanitize(value):
    """Unwrap nodriver CDP objects and drop anything non-serializable."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return None

# get all scholar profile links from listing page and avatar urls
async def scrape_listing_page(tab, data_dict: dict) -> dict:
    await human_sleep(1.0, 3.0) # wait for page to load
    
    img_elements = await tab.select_all('p.article-thumb a img')
    for img_tag in img_elements:
        avt_url = img_tag.attrs.get('src')
        parent_a_tag = img_tag.parent
        if parent_a_tag:
            profile_url = parent_a_tag.attrs.get('href')
            if profile_url and avt_url:
                data_dict[profile_url] = avt_url

    return data_dict

# extract text content from the main table in the scholar profile page, return as a single string
async def extract_table_text(tab) -> str:
    selector = 'div#print-chitiet'
    content_element = await tab.select(selector)
    if content_element:
        raw_text = await content_element.apply('e => e.innerText')
        
        if raw_text:
            cleaned_text = raw_text.strip()
            return cleaned_text

    log.warning(f"Content not found with selector: {selector}")
    return ""



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
    data_dict = {}

    data_dict = await scrape_listing_page(tab, data_dict)
    tmp={}
    
    all_links = await tab.select_all('a')
    page_2_button = None
    
    for a_tag in all_links:
        if a_tag.text and a_tag.text.strip() == '2':
            page_2_button = a_tag
            break
            
    if page_2_button:
        href_val = page_2_button.attrs.get('href', '')
        if 'javascript:' in href_val:
            js_command = href_val.replace('javascript:', '').strip()
            await tab.evaluate(js_command)
            await tab.sleep(3)
            log.info("On page 2") 
            data_dict.update(await scrape_listing_page(tab, tmp))
        else:
            await page_2_button.scroll_into_view()
            await page_2_button.apply('e => e.click()')
            await tab.sleep(3)
    
    log.info(f"Found {len(data_dict)} scholar links to process.")

    base_url = "https://khoakhpt.neu.edu.vn"
    for url in data_dict.keys():
        try:
            valid_url = base_url + url
            await tab.get(valid_url)
            await human_sleep(1.5, 3.0)


            table_text = await extract_table_text(tab)

            record = {
                "url": valid_url,
                "avt_url": base_url + data_dict[url],
                "table_text": table_text,
                "dai_hoc": "Đại học Kinh tế Quốc dân",
                "don_vi_truc_thuoc": "Khoa Kế hoạch và phát triển",
                "is_extracted": False,
                "thong_tin_khong_cong_bo": False,
                "is_checked": False,
            }

            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
            log.info(f"Saved: {record.get('url')} to {OUTPUT_FILE}")

        except Exception as e:
            log.warning(f"Error processing {url}: {e}")

uc.loop().run_until_complete(main())