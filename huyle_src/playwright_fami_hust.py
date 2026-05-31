from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import time
import logging
import os
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")


# Setup logging
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # get project root dir

OUTPUT_DIR = os.path.join(BASE_DIR, "output/hust/fami/raw_data")
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "fami.jsonl")

LOG_DIR = os.path.join(BASE_DIR, "output/hust/fami/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"fami_{timestamp}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


SLUGS_FILE = "html_text.txt"

with open(SLUGS_FILE, 'r', encoding='utf-8') as f:
    SLUGS = [line.strip() for line in f if line.strip()]

logger.info(f"Đọc được {len(SLUGS)} slugs")


def parse_lecturer(html, slug):
    soup = BeautifulSoup(html, 'html.parser')
    
    data = {
        'slug': slug,
        'url': f"https://fami.hust.edu.vn/giang-vien/?name={slug}",
        'thong_tin_khong_cong_bo': False,
        'is_extracted': True,
        'is_checked': False,
        'dai_hoc': 'Đại học Bách khoa Hà Nội',
        'don_vi_truc_thuoc': 'Khoa Toán-Tin',
    }

    img = soup.select_one('#lecturer-image img')
    data['avt_url'] = img['src'] if img else ''

    info = soup.select_one('#lecturer-info')
    if info:
        h1 = info.find('h1')
        data['name'] = h1.text.strip() if h1 else ''

        for p in info.find_all('p'):
            text = p.get_text(strip=True)
            if not text:
                continue
            if 'Email:' in text:
                data['email'] = text.replace('Email:', '').strip()
            elif 'Website:' in text:
                data['website'] = text.replace('Website:', '').strip()
            else:
                data['chuc_vu'] = p.get_text(strip=True)

    for section in soup.select('div.bg-bd-gv'):
        h2 = section.find('h2')
        if not h2:
            continue
        title = h2.text.strip().lower()
        lines = section.get_text(separator='\n').strip().split('\n')
        content = '\n'.join(l for l in lines[1:] if l.strip())

        if 'môn học' in title:
            data['mon_hoc'] = content
        elif 'nghiên cứu' in title:
            data['huong_nghien_cuu'] = content
        elif 'journal' in title:
            data['bai_bao_journal'] = content
        elif 'conference' in title:
            data['bao_cao_hoi_nghi'] = content
        elif 'đề tài' in title:
            data['de_tai'] = content

    return data
def scrape_all(slugs):
    logger.info(f"Bắt đầu scrape {len(slugs)} giảng viên")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f_out:
            for i, slug in enumerate(slugs):
                logger.info(f"[{i+1}/{len(slugs)}] Đang scrape: {slug}")
                try:
                    page = browser.new_page()
                    page.goto(f"https://fami.hust.edu.vn/giang-vien/?name={slug}")
                    page.wait_for_load_state("networkidle")
                    html = page.content()
                    page.close()
                    
                    data = parse_lecturer(html, slug)
                    f_out.write(json.dumps(data, ensure_ascii=False) + '\n')
                    f_out.flush()
                    
                    logger.info(f"OK: {data.get('name', '?')}")
                except Exception as e:
                    logger.error(f"Lỗi {slug}: {e}")
                    error_record = {'slug': slug, 'error': str(e)}
                    f_out.write(json.dumps(error_record, ensure_ascii=False) + '\n')
                    f_out.flush()
                
                time.sleep(0.5)
        
        browser.close()
    
    logger.info(f"Hoàn thành! Kết quả lưu tại: {OUTPUT_FILE}")

scrape_all(SLUGS)