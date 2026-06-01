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
        logging.StreamHandler(),
    ],
)
log = logging.getLogger()

LISTING_URL = "https://saa.neu.edu.vn/giang-vien/"


async def human_sleep(min_s=1.0, max_s=3.0):
    import random
    await asyncio.sleep(random.uniform(min_s, max_s))


async def get_faculty_links(tab):
    """Collect all faculty detail URLs from listing page."""
    await tab.get(LISTING_URL)

    # scroll to trigger lazy-load
    await tab.evaluate("window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })")

    raw = await tab.evaluate("""
        (() => {
            // grab all anchor tags inside faculty item containers
            const links = document.querySelectorAll('.single-service-item .text-holder h3 a[href]');
            return JSON.stringify(Array.from(links).map(a => ({ href: a.href, text: a.innerText.trim() })));
        })()
    """)

    try:
        items = json.loads(raw) if raw else []
    except Exception:
        items = []

    items = [i for i in items if isinstance(i.get("href"), str) and i["href"].startswith("http")]
    log.info(f"Found {len(items)} faculty links on listing page")
    return items


async def click_expand_sections(tab):
    """Click all collapsible section headers to reveal hidden content (Image 2 fields)."""
    try:
        # find section toggle buttons / accordion headers
        await tab.evaluate("""
            (() => {
                const triggers = document.querySelectorAll(
                    '.accordion-toggle, .panel-title a, [data-toggle="collapse"], ' +
                    '.entry-content h3, .entry-content h4, .wpb_toggle, ' +
                    '.toggle-title, .fusion-toggle-heading, .fusion-panel-title'
                );
                triggers.forEach(el => {
                    try { el.click(); } catch(e) {}
                });
            })()
        """)
        await human_sleep(0.8, 1.5)
    except Exception as e:
        log.warning(f"click_expand_sections error: {e}")


async def extract_text_js(tab, selector):
    """Return innerText of first matching element via JS, or None."""
    try:
        result = await tab.evaluate(f"""
            (() => {{
                const el = document.querySelector('{selector}');
                return el ? el.innerText.replace(/\\s+/g, ' ').trim() : null;
            }})()
        """)
        return result if isinstance(result, str) and result else None
    except Exception:
        return None


async def scrape_detail_page(tab, url):
    """
    Scrape all required fields from a faculty detail page.
    Falls back to a DOM-walk approach for the structured info table.
    """
    await tab.get(url)
    await human_sleep(2, 3.5)

    # scroll down to load all content
    await tab.evaluate("window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })")
    await human_sleep(1.2, 2.0)
    await tab.evaluate("window.scrollTo({ top: 0, behavior: 'smooth' })")
    await human_sleep(0.5, 1.0)

    # expand all accordion / collapsible sections before scraping
    await click_expand_sections(tab)

    # --- avatar URL ---
    avt_url = await tab.evaluate("""
        (() => {
            // profile avatar in img-holder or featured-image area
            const img = document.querySelector(
                '.img-holder img, .single-service-item img, ' +
                '.single-content img, .post-thumbnail img, ' +
                '.profile-image img, .avt img, .avatar img'
            );
            return img ? (img.src || img.getAttribute('data-src') || null) : null;
        })()
    """)

    ho_ten = await tab.evaluate("""
        (() => {
            const h = document.querySelector('h1.entry-title, h2.entry-title, .page-title h1, h1, h2');
            return h ? h.innerText.replace(/\\s+/g, ' ').trim() : null;
        })()
    """)

    info_map_raw = await tab.evaluate("""
        (() => {
            const result = {};
            // approach 1: rows with <td> label + value pairs
            document.querySelectorAll('table tr').forEach(row => {
                const cells = row.querySelectorAll('td, th');
                if (cells.length >= 2) {
                    const key = cells[0].innerText.replace(/\\s+/g, ' ').trim().replace(/:$/, '');
                    const val = cells[1].innerText.replace(/\\s+/g, ' ').trim();
                    if (key) result[key] = val;
                }
            });
            // approach 2: dt/dd definition lists
            const dts = document.querySelectorAll('dt');
            dts.forEach(dt => {
                const dd = dt.nextElementSibling;
                if (dd && dd.tagName === 'DD') {
                    const key = dt.innerText.replace(/\\s+/g, ' ').trim().replace(/:$/, '');
                    result[key] = dd.innerText.replace(/\\s+/g, ' ').trim();
                }
            });
            // approach 3: pairs of <p><strong>Label:</strong> Value</p>
            document.querySelectorAll('p').forEach(p => {
                const strong = p.querySelector('strong, b');
                if (strong) {
                    const key = strong.innerText.replace(/\\s+/g, ' ').trim().replace(/:$/, '');
                    // remove strong text from full paragraph text to get value
                    const full = p.innerText.replace(/\\s+/g, ' ').trim();
                    const val = full.replace(strong.innerText, '').replace(/^[:\\s]+/, '').trim();
                    if (key && val) result[key] = val;
                }
            });
            return JSON.stringify(result);
        })()
    """)

    try:
        info_map = json.loads(info_map_raw) if info_map_raw else {}
    except Exception:
        info_map = {}

    def find_field(keys_vi):
        """Look up a value in info_map by trying multiple Vietnamese key variants."""
        for k in keys_vi:
            for map_key, val in info_map.items():
                if k.lower() in map_key.lower():
                    return val or None
        return None

    don_vi_cong_tac = find_field(["Đơn vị", "Đơn vị công tác", "Khoa", "Bộ môn"])
    chuc_vu = find_field(["Chức vụ", "Ngạch giảng viên", "Chức danh"])
    nganh = find_field(["Ngành", "Chuyên ngành"])
    linh_vuc = find_field(["Lĩnh vực nghiên cứu", "Lĩnh vực giảng dạy", "Lĩnh vực"])
    dien_thoai = find_field(["Điện thoại", "Phone", "Tel", "SĐT"])
    email = find_field(["Email", "E-mail"])

    sections_raw = await tab.evaluate("""
        (() => {
            const result = {};
            // fusion theme accordion panels
            document.querySelectorAll('.fusion-panel').forEach(panel => {
                const title_el = panel.querySelector('.fusion-panel-title, .panel-title, .accordion-toggle');
                const body_el  = panel.querySelector('.panel-body, .fusion-toggle-content, .accordion-content');
                if (title_el && body_el) {
                    const key = title_el.innerText.replace(/\\s+/g, ' ').trim();
                    const val = body_el.innerText.replace(/\\s+/g, ' ').trim();
                    if (key) result[key] = val;
                }
            });
            // generic Bootstrap / WPBakery toggle
            document.querySelectorAll('.wpb_toggle_title, .toggle-title').forEach(el => {
                const body = el.nextElementSibling;
                if (body) {
                    const key = el.innerText.replace(/\\s+/g, ' ').trim();
                    result[key] = body.innerText.replace(/\\s+/g, ' ').trim();
                }
            });
            return JSON.stringify(result);
        })()
    """)

    try:
        sections = json.loads(sections_raw) if sections_raw else {}
    except Exception:
        sections = {}

    def find_section(keys_vi):
        """Look up a section value by partial Vietnamese key match."""
        for k in keys_vi:
            for sec_key, val in sections.items():
                if k.lower() in sec_key.lower():
                    return val or None
        return None

    qua_trinh_dao_tao     = find_section(["Quá trình đào tạo"])
    qua_trinh_cong_tac    = find_section(["Quá trình công tác"])
    bai_bao_tap_chi       = find_section(["Bài báo đăng trên tạp chí"])
    bai_tham_luan         = find_section(["Bài tham luận"])
    sach_giao_trinh       = find_section(["Sách, giáo trình"])
    de_tai_du_an          = find_section(["Đề tài", "dự án", "nhiệm vụ khoa học"])
    huong_dan_ncs         = find_section(["Kinh nghiệm hướng dẫn NCS"])
    khen_thuong           = find_section(["Hình thức khen thưởng"])

    if not don_vi_cong_tac:
        don_vi_cong_tac = find_section(["Đơn vị"])
    if not chuc_vu:
        chuc_vu = find_section(["Chức vụ", "Ngạch giảng viên"])
    if not nganh:
        nganh = find_section(["Ngành", "Chuyên ngành"])
    if not linh_vuc:
        linh_vuc = find_section(["Lĩnh vực"])
    if not dien_thoai:
        dien_thoai = find_section(["Điện thoại"])
    if not email:
        email = find_section(["Email"])

    record = {
        "url":                     url,
        "avt_url":                 avt_url if isinstance(avt_url, str) else None,
        "ho_ten":                  ho_ten,
        "don_vi_cong_tac":         don_vi_cong_tac,
        "chuc_vu_ngach_giang_vien": chuc_vu,
        "nganh_chuyen_nganh":      nganh,
        "linh_vuc_nghien_cuu_giang_day": linh_vuc,
        "dien_thoai":              dien_thoai,
        "email":                   email,
        "qua_trinh_dao_tao":       qua_trinh_dao_tao,
        "qua_trinh_cong_tac":      qua_trinh_cong_tac,
        "bai_bao_tap_chi_kh":      bai_bao_tap_chi,
        "bai_tham_luan_hoi_thao":  bai_tham_luan,
        "sach_giao_trinh_an_pham": sach_giao_trinh,
        "de_tai_du_an_nhiem_vu":   de_tai_du_an,
        "huong_dan_ncs":           huong_dan_ncs,
        "khen_thuong_khoa_hoc":    khen_thuong,
    }

    log.info(f"Scraped: {ho_ten} | {url}")
    return record


async def handle_broken_link(tab, listing_item):
    """
    Some faculty links redirect to a broken page (e.g. Nguyễn Hữu Ánh).
    In that case we fall back to Image-1 approach: find the correct href
    from the DOM of the listing item's expanded section or navigate directly
    to the corrected path extracted from the inspector view.
    """
    corrected = await tab.evaluate("""
        (() => {
            // look for canonical link or any matching anchor in page
            const canonical = document.querySelector('link[rel="canonical"]');
            if (canonical) return canonical.href;
            // try first content anchor that differs from current URL
            const anchors = Array.from(document.querySelectorAll('a[href]'));
            for (const a of anchors) {
                const h = a.href;
                if (h && h.includes('saa.neu.edu.vn') && !h.includes('/giang-vien/') && h !== window.location.href) {
                    return h;
                }
            }
            return null;
        })()
    """)
    return corrected if isinstance(corrected, str) and corrected.startswith("http") else None


async def main():
    browser = await uc.start(
        headless=False,
        browser_args=[
            "--disable-blink-features=AutomationControlled",
        ],
        lang="vi-VN",
    )

    tab = browser.main_tab

    faculty_items = await get_faculty_links(tab)

    for idx, item in enumerate(faculty_items):
        url  = item["href"]
        name = item["text"]
        log.info(f"[{idx+1}/{len(faculty_items)}] Processing: {name} | {url}")

        try:
            await tab.get(url)
            await human_sleep(1.5, 3.0)

            current_url = await tab.evaluate("window.location.href")
            page_title  = await tab.evaluate("document.title")

            is_broken = await tab.evaluate("""
                (() => {
                    // page is broken if it has no profile-specific selectors
                    const hasProfile = document.querySelector(
                        '.img-holder img, .single-service-item, .entry-title, h1'
                    );
                    const has404 = document.title.toLowerCase().includes('404') ||
                                   document.body.innerText.includes('không tìm thấy') ||
                                   document.body.innerText.toLowerCase().includes('page not found');
                    return !hasProfile || has404;
                })()
            """)

            if is_broken:
                log.warning(f"Broken page detected for {name}, trying fallback link...")
                await tab.get(LISTING_URL)
                await human_sleep(1.5, 2.5)
                await tab.evaluate("window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })")
                await human_sleep(1.0, 1.5)

                escaped_name = name.replace("'", "\\'")
                fallback_url = await tab.evaluate(f"""
                    (() => {{
                        const anchors = Array.from(document.querySelectorAll('a[href]'));
                        for (const a of anchors) {{
                            if (a.innerText.trim().includes('{escaped_name}')) {{
                                return a.href;
                            }}
                        }}
                        // fallback: search by partial name (without title prefix like GS.TS.)
                        const nameParts = '{escaped_name}'.split(' ');
                        const lastName = nameParts[nameParts.length - 1];
                        for (const a of anchors) {{
                            if (a.href.includes(lastName.toLowerCase().replace(/[àáạảãâầấậẩẫăằắặẳẵ]/g, 'a')
                                .replace(/[èéẹẻẽêềếệểễ]/g, 'e')
                                .replace(/[ìíịỉĩ]/g, 'i')
                                .replace(/[òóọỏõôồốộổỗơờớợởỡ]/g, 'o')
                                .replace(/[ùúụủũưừứựửữ]/g, 'u')
                                .replace(/[ỳýỵỷỹ]/g, 'y')
                                .replace(/[đ]/g, 'd'))) {{
                                return a.href;
                            }}
                        }}
                        return null;
                    }})()
                """)

                if fallback_url and isinstance(fallback_url, str) and fallback_url.startswith("http") and fallback_url != url:
                    log.info(f"Fallback URL found: {fallback_url}")
                    url = fallback_url
                else:
                    log.warning(f"No fallback URL found for {name}, skipping.")
                    continue

            record = await scrape_detail_page(tab, url)

            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()

            log.info(f"Saved: {record.get('ho_ten')} -> {OUTPUT_FILE}")

        except Exception as e:
            log.warning(f"Error processing {name} | {url}: {e}")

        await human_sleep(1.5, 3.0)

    log.info(f"Done. Total time: {time.time() - script_start_time:.1f}s")
    browser.stop()


uc.loop().run_until_complete(main())