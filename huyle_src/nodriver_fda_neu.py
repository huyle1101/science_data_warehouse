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

OUTPUT_DIR = 'f:/science_data_warehouse_repo/output/neu/fda/raw_data'
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, f"fda_{timestamp}.jsonl")

LOG_DIR = 'f:/science_data_warehouse_repo/output/neu/fda/logs'
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"fda_{timestamp}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger()

LISTING_URL = "https://fda.neu.edu.vn/doi-ngu-can-bo-giang-vien/"

async def human_sleep(min_s=1.0, max_s=3.0):
    await asyncio.sleep(random.uniform(min_s, max_s))


# get all scholar profile links from listing page
async def scrape_listing_page(tab) -> list:
    js_code = """
        Array.from(document.querySelectorAll('h3.wps-team--member-title a'))
            .map(a => a.getAttribute('href'))
            .filter(href => href !== null);
    """
    
    href = await tab.evaluate(js_code)
    l = list(set([item['value'] for item in href if 'value' in item]))
    log.info(f"Get {len(l)} links from listing page.")
    
    return l

# extract text content from the main table in the scholar profile page
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

        const TARGET_KEYWORDS = [
            'lĩnh vực nghiên cứu',
            'giải thưởng',
            'công trình khoa học tiêu biểu',
            'giảng dạy',
            'các đề tài dự án đã thực hiện',
        ];

        function matchesTarget(text) {
            const t = text.trim().toLowerCase();
            return TARGET_KEYWORDS.some(kw => t.includes(kw));
        }

        function isSectionHeader(el) {
            if (['H3', 'H4'].includes(el.tagName)) return true;
            if (el.tagName === 'P') {
                const meaningful = Array.from(el.childNodes).filter(n =>
                    !(n.nodeType === 3 && n.textContent.trim() === '')
                );
                return meaningful.length === 1 &&
                    meaningful[0].nodeType === 1 &&
                    ['STRONG', 'B'].includes(meaningful[0].tagName);
            }
            return false;
        }

        function isTargetSectionHeader(el) {
            return isSectionHeader(el) && matchesTarget(el.textContent);
        }

        const contentArea = document.querySelector('.entry-content, .wps-team--description, article, main')
                            || document.body;

        const allBlocks = Array.from(contentArea.querySelectorAll('p, ul, ol, h3, h4'));

        const headerBlocks = allBlocks.filter(el => isTargetSectionHeader(el));

        const result = {};

        headerBlocks.forEach(headerEl => {
            const key = toSnakeCase(headerEl.textContent.trim());
            const items = [];

            let el = headerEl.nextElementSibling;

            while (el) {
                if (isTargetSectionHeader(el)) break;
                if (['H3', 'H4'].includes(el.tagName)) break;

                const liItems = el.querySelectorAll('li');
                if (liItems.length > 0) {
                    liItems.forEach(li => {
                        const t = li.textContent.trim();
                        if (t) items.push(t);
                    });
                } else {
                    const t = el.textContent.trim();
                    if (t) items.push(t);
                }

                el = el.nextElementSibling;
            }

            result[key] = items;
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
            const imgElement = document.querySelector('div.team-member--thumbnail img');
            if (!imgElement) return null;
            const srcset = imgElement.getAttribute('srcset');
            if (srcset) {
                const entries = srcset.split(',')
                    .map(s => s.trim().split(/\\s+/))
                    .filter(parts => parts.length === 2)
                    .map(parts => ({ url: parts[0], w: parseInt(parts[1]) }))
                    .sort((a, b) => b.w - a.w);
                if (entries.length > 0) return entries[0].url;
            }
            return imgElement.src;
        })()
    """
    data_dict['avt_url'] = await tab.evaluate(get_avt_url_js)
    
    get_ho_ten_js = """
        (() => {
            const nameEl = document.querySelector('h1.wps-team--member-title');
            return nameEl ? nameEl.textContent.trim() : null;
        })()
    """
    data_dict['ho_ten'] = await tab.evaluate(get_ho_ten_js)

    get_email_js = """
        (() => {
            const emailEl = document.querySelector('a[href^="mailto:"]');
            return emailEl ? emailEl.textContent.trim() : null;
        })()
    """
    data_dict['email'] = await tab.evaluate(get_email_js)
    
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
            record['don_vi_truc_thuoc'] = 'Khoa Khoa học dữ liệu và Trí tuệ nhân tạo'
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