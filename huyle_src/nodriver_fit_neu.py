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

OUTPUT_DIR = 'f:/science_data_warehouse_repo/output/neu/fit/raw_data'
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, f"fit_{timestamp}.jsonl")

LOG_DIR = 'f:/science_data_warehouse_repo/output/neu/fit/logs'
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"fit_{timestamp}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger()

LISTING_URL = "https://fit.neu.edu.vn/lecturer"

async def human_sleep(min_s=1.0, max_s=3.0):
    await asyncio.sleep(random.uniform(min_s, max_s))


# get all scholar profile links from listing page
async def scrape_listing_page(tab) -> list:
    js_code = """
        Array.from(document.querySelectorAll('.card.bg-light a'))
             .map(a => a.getAttribute('href'))
             .filter(href => href !== null);
    """
    
    href_list = await tab.evaluate(js_code)
    
    log.info(f"Extracted {len(href_list)} profile links.")
    
    l = [item['value'] for item in href_list if 'value' in item]
    
    return l

# extract text content from the main table in the scholar profile page
async def extract_information(tab) -> dict:
    js_code = """
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
        
        document.querySelectorAll('h3').forEach(h3 => {
            const text = h3.textContent.trim();
            if (text) { 
                const key = toSnakeCase(text);
                result[key] = text;
            }
        });
        
        result;
    """
    
    data_dict = await tab.evaluate(js_code)
    
    get_lien_he_js = """
        let el = Array.from(document.querySelectorAll('h4')).find(h => h.textContent.includes('LIÊN HỆ'));
        let res = [];
        while ((el = el?.nextElementSibling) && el.tagName === 'P') {
            res.push(el.textContent.trim());
        }
        res;
    """
    
    data_dict['lien_he'] = await tab.evaluate(get_lien_he_js)
    
    get_avt_url_js = """
        const imgElement = document.querySelector('img.img-lecture');
        imgElement ? imgElement.src : null;
    """
    
    data_dict['avt_url'] = await tab.evaluate(get_avt_url_js)
    
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

    await tab.evaluate("document.querySelector('.lang-btn')?.click()")
    
    await asyncio.sleep(2) 
    
    js_click_vi = """
        let viItem = Array.from(document.querySelectorAll('.lang-item')).find(item => item.textContent.includes('Tiếng Việt'));
        if (viItem) {
            viItem.click();
            return true;
        }
        return false;
    """
    
    switched = await tab.evaluate(js_click_vi)
    
    if switched:
        log.info("Switched to Vietnamese language successfully.")
        await human_sleep(3.0, 4.0) 
    else:
        log.warning("Not able to switch language, proceeding with default.")
    
    scholars = []
    scholars.append(await scrape_listing_page(tab)) # first page
    log.info(f"Found {len(scholars)} scholar links on page 1.")
    
    page=1
    while 1:
        js_click_next = """
                    let activeLi = document.querySelector('.pagination .page-item.active');
                    if (!activeLi) return false;
                    
                    let nextLi = activeLi.nextElementSibling;
                    
                    if (!nextLi || nextLi.classList.contains('disabled')) {
                        return false; 
                    }
                    
                    let nextBtn = nextLi.querySelector('.page-link');
                    if (nextBtn) {
                        nextBtn.click();
                        return true;
                    }
                    
                    return false;
                """
        
        has_next_page = await tab.evaluate(js_click_next)
        
        if has_next_page:
            page += 1
            log.info(f"On page {[page]}")
            
            await human_sleep(2.0, 4.0)  # wait for page to load
            tmp = await scrape_listing_page(tab)
            log.info(f"Found {len(tmp)} on page {page}")
            scholars.append(tmp)
        else:
            log.info("No more pages to click, finished pagination.")
            break
    
    log.info(f"Found total {len(scholars)} scholar links to process.")

    base_url = "https://fit.neu.edu.vn/lecturer"
    for url in scholars:
        try:
            valid_url = base_url + url[10:]
            await tab.get(valid_url)
            await human_sleep(1.5, 3.0)


            record = await extract_information(tab)
            record['valid_url'] = valid_url
            record['avt_url'] = None
            record['dai_hoc'] = 'Đại học Kinh tế quốc dân'
            record['don_vi_truc_thuoc'] = 'Khoa Công nghệ thông tin'
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
    await browser.close()

uc.loop().run_until_complete(main())