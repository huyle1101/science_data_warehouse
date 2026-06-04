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

OUTPUT_DIR = 'f:/science_data_warehouse_repo/output/neu/tke/raw_data'
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, f"tke_{timestamp}.jsonl")

LOG_DIR = 'f:/science_data_warehouse_repo/output/neu/tke/logs'
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"tke_{timestamp}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger()

LISTING_URL = "https://khoathongke.neu.edu.vn/vi/can-bo-giang-vien-1745/giang-vien-can-bo"

async def human_sleep(min_s=1.0, max_s=3.0):
    await asyncio.sleep(random.uniform(min_s, max_s))


# get all scholar profile links from listing page
async def scrape_listing_page(tab) -> list:
    js_code = """
        Array.from(document.querySelectorAll('div.faculty-name a'))
            .map(a => a.getAttribute('href'))
            .filter(href => href !== null);
    """

    href = await tab.evaluate(js_code)
    l = list(set([item['value'] for item in href if 'value' in item]))
    log.info(f"Get {len(l)} links from listing page.")

    return l

# extract text content from the main table in the scholar profile page
async def extract_information(tab) -> dict:
    js_code = """
        (() => {
            function toSnakeCase(str) {
                return str.normalize("NFD")
                          .replace(/[\\u0300-\\u036f]/g, "")
                          .replace(/đ/g, "d").replace(/Đ/g, "D")
                          .toLowerCase()
                          .replace(/[^a-z0-9\\s-]/g, '')
                          .trim()
                          .replace(/\\s+/g, '_');
            }
            
            const result = {};
            document.querySelectorAll('h2').forEach(h2 => {
                const text = h2.textContent.trim();
                if (text) {
                    const key = toSnakeCase(text);
                    let items = [];
                    let el = h2.nextElementSibling;
                    while (el && el.tagName !== 'H2') {
                        const liItems = el.querySelectorAll('li');
                        if (liItems.length > 0) {
                            liItems.forEach(li => {
                                const t = li.textContent.trim();
                                if (t) items.push(t);
                            });
                        } else {
                            el.textContent.split('\\n')
                              .map(s => s.trim())
                              .filter(s => s.length > 0)
                              .forEach(s => items.push(s));
                        }
                        el = el.nextElementSibling;
                    }
                    result[key] = items;
                }
            });
            
            return JSON.stringify(result);
        })()
    """
    raw = await tab.evaluate(js_code)
    data_dict = json.loads(raw)
    get_avt_url_js = """
        (() => {
            const imgElement = document.querySelector('div.intro-section img');
            if (!imgElement) return null;
            return imgElement.getAttribute('src');
        })()
    """

    avt_url = await tab.evaluate(get_avt_url_js)
    data_dict['avt_url'] = ("https://khoathongke.neu.edu.vn" + avt_url.replace(" ", "%20")) if avt_url else None

    get_ho_ten_js = """
        (() => {
            const nameEl = document.querySelector('div.tuade');
            return nameEl ? nameEl.textContent.trim() : null;
        })()
    """

    data_dict['ho_ten'] = await tab.evaluate(get_ho_ten_js)


    return data_dict
'''
    get_avt_url_js = """
        (() => {
            const imgElement = document.querySelector('div.intro-section img');
            if (!imgElement) return null;
            return imgElement.getAttribute('src');
        })()
    """

    avt_url = await safe_evaluate(tab, get_avt_url_js)
    data_dict['avt_url'] = ("https://khoathongke.neu.edu.vn" + avt_url) if avt_url else None

    get_ho_ten_js = """
        (() => {
            const nameEl = document.querySelector('div.tuade');
            return nameEl ? nameEl.textContent.trim() : null;
        })()
    """

    data_dict['ho_ten'] = await safe_evaluate(tab, get_ho_ten_js)
'''


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
            record['don_vi_truc_thuoc'] = 'Khoa Thống kê - Trường Công nghệ'
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