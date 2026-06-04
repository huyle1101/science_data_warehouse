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
    href = await tab.evaluate(js_code)
    l = list(set([item['value'] for item in href if 'value' in item]))
    log.info(f"Get {len(l)} links from listing page.")
    
    return l

# extract text content from the main table in the scholar profile page
'''
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
                // Lấy toàn bộ text của sibling sau h3 cho đến h3 tiếp theo
                let content = [];
                let el = h3.nextElementSibling;
                while (el && el.tagName !== 'H3') {
                    content.push(el.textContent.trim());
                    el = el.nextElementSibling;
                }
                result[key] = content.join('\\n');
            }
        });
        
        JSON.stringify(result);
    """
    raw = await tab.evaluate(js_code)
    data_dict = json.loads(raw)

    get_lien_he_js = """
        let el = Array.from(document.querySelectorAll('h4')).find(h => h.textContent.includes('LIÊN HỆ'));
        let res = [];
        while ((el = el?.nextElementSibling) && el.tagName === 'P') {
            res.push(el.textContent.trim());
        }
        JSON.stringify(res);
    """
    data_dict['lien_he'] = json.loads(await tab.evaluate(get_lien_he_js))

    get_avt_url_js = """
        const imgElement = document.querySelector('img.img-lecture');
        imgElement ? imgElement.src : null;
    """
    data_dict['avt_url'] = await tab.evaluate(get_avt_url_js)

    return data_dict
'''


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
            document.querySelectorAll('h3').forEach(h3 => {
                const text = h3.textContent.trim();
                if (text) {
                    const key = toSnakeCase(text);
                    let items = [];
                    let el = h3.nextElementSibling;
                    while (el && el.tagName !== 'H3') {
                        // Lấy tất cả text nodes / inline items bên trong element
                        const liItems = el.querySelectorAll('li');
                        if (liItems.length > 0) {
                            // Nếu có <li> thì mỗi li là 1 item
                            liItems.forEach(li => {
                                const t = li.textContent.trim();
                                if (t) items.push(t);
                            });
                        } else {
                            // Không có li: tách theo newline hoặc lấy cả block
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

    get_lien_he_js = """
        (() => {
            let el = Array.from(document.querySelectorAll('h4')).find(h => h.textContent.includes('LIÊN HỆ'));
            let res = [];
            while ((el = el?.nextElementSibling) && el.tagName === 'P') {
                const t = el.textContent.trim();
                if (t) res.push(t);
            }
            return JSON.stringify(res);
        })()
    """
    data_dict['lien_he'] = json.loads(await tab.evaluate(get_lien_he_js))

    get_avt_url_js = """
        (() => {
            const imgElement = document.querySelector('img.img-lecture');
            return imgElement ? imgElement.src : null;
        })()
    """
    data_dict['avt_url'] = await tab.evaluate(get_avt_url_js)
    
    
    get_ho_ten_js = """
        (() => {
            const nameEl = document.querySelector('.info-lecturer_name-content h1 span.custom-h3');
            return nameEl ? nameEl.textContent.trim() : null;
        })()
    """
    data_dict['ho_ten'] = await tab.evaluate(get_ho_ten_js)
    
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

    lang_btn = await tab.find(".lang-btn")
    await lang_btn.click()
    await human_sleep(2.0, 4.0)  # wait for language button to respond
    
    lang_items = await tab.find_all(".lang-item")
    clicked = False
    for item in lang_items:
        text = await item.get_html()
        if "Tiếng Việt" in text:
            await item.click()
            await human_sleep(2.0, 4.0)  # wait for language switch
            log.info("Switched to Vietnamese language.")
            clicked = True
            break
 
    if not clicked:
        log.warning("Cannot find Vietnamese language option, continuing with default language.")
    
    scholars = []
    scholars.extend(await scrape_listing_page(tab)) # first page
    log.info(f"Found {len(scholars)} scholar links on page 1.")
    
    page = 1
    while True:
        next_page = page + 1

        # check if page-item disabled (means last page)
        is_last = await tab.evaluate("""
            const nextBtn = document.querySelector('.pagination button[aria-label="Next"]');
            if (!nextBtn) return true;
            return nextBtn.closest('.page-item').classList.contains('disabled');
        """)

        log.info(f"DEBUG is_last type: {type(is_last)}, value: {is_last!r}, bool: {bool(is_last)}")

        if is_last == True:
            log.info(f"Finished at page {page}.")
            break

        # find button with text of next_page
        all_btns = await tab.find_all("button.page-link")
        btn_to_click = None
        for btn in all_btns:
            txt = await btn.get_html()
            if f">{next_page}<" in txt:
                btn_to_click = btn
                break

        if not btn_to_click:
            log.info(f"No button {next_page}, finished.")
            break

        await btn_to_click.click()
        await human_sleep(3.0, 5.0)

        current = await tab.evaluate("""
            const active = document.querySelector('.pagination .page-item.active');
            active ? parseInt(active.innerText.trim()) : -1;
        """)
        
        log.info(f"DEBUG current type: {type(current)}, value: {current!r}")
        log.info(f"DEBUG next_page: {next_page}, current == next_page: {current == next_page}")

        page += 1
        await human_sleep(1.0, 2.0)
        tmp = await scrape_listing_page(tab)
        await human_sleep(3.0, 5.0)
        scholars.extend(tmp)
        
    log.info(f"Found total {len(scholars)} scholar links to process.")

    base_url = "https://fit.neu.edu.vn/lecturer"
    for url in scholars:
        try:
            valid_url = base_url + url[9:]
            await tab.get(valid_url)
            await human_sleep(1.5, 3.0)


            record = await extract_information(tab)
            record['valid_url'] = valid_url
            record['dai_hoc'] = 'Đại học Kinh tế quốc dân'
            record['don_vi_truc_thuoc'] = 'Khoa Công nghệ thông tin'
            record['is_extracted'] = True
            record['thong_tin_khong_cong_bo'] = False
            record['is_checked'] = False

            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
            log.info(f"Saved: {record.get('valid_url')} to {OUTPUT_FILE}")
        except Exception as e:
            log.warning(f"Error processing {url}: {e}")
    
    log.info("Finished, total running time: {:.2f} seconds".format(time.time() - script_start_time))
    # await browser.stop()

uc.loop().run_until_complete(main())