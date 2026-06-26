import re
import json
import requests  # pip install requests
import fitz  # pip install pymupdf
import unicodedata


PDF_URL = "https://fbm.neu.edu.vn/wp-content/uploads/2022/07/Do-Thi-Dong.pdf"
OUTPUT_PATH = "patch_web.json"


# =========================
# 1. Utils
# =========================

def clean_line(s):
    if s is None:
        return ""

    s = s.replace("\u00ad", "")
    s = s.replace("￾", "")
    s = re.sub(r"[ \t]+", " ", s)

    return s.strip()


def clean_cell(s):
    if not s:
        return None

    s = s.replace("\u00ad", "")
    s = s.replace("￾", "")
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" \n\t;,.")
    return s or None


def normalize_page_text(text):
    lines = [clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def fetch_pdf_bytes(pdf_url, timeout=30):
    """
    Tải PDF từ URL và giữ trong memory, không lưu thành file local.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(pdf_url, headers=headers, timeout=timeout)
    response.raise_for_status()

    pdf_bytes = response.content

    # Một số server trả content-type không chuẩn, nên chỉ báo lỗi khi cả
    # header và phần đầu bytes đều không giống PDF.
    content_type = response.headers.get("Content-Type", "").lower()

    if not pdf_bytes.lstrip().startswith(b"%PDF") and "pdf" not in content_type:
        raise ValueError(
            "URL không trả về PDF hợp lệ. "
            f"Content-Type nhận được: {content_type or 'unknown'}"
        )

    return pdf_bytes


def read_pages_text(pdf_url):
    pages = []
    pdf_bytes = fetch_pdf_bytes(pdf_url)

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_idx, page in enumerate(doc, start=1):
            raw_text = page.get_text("text")
            pages.append({
                "page": page_idx,
                "text": raw_text,
                "text_clean": normalize_page_text(raw_text),
            })

    return pages


def search_one(pattern, text, flags=re.I | re.S):
    m = re.search(pattern, text, flags)
    return clean_cell(m.group(1)) if m else None


def section_between(text, start_pat, end_pat=None):
    start_m = re.search(start_pat, text, flags=re.I | re.S)

    if not start_m:
        return ""

    start = start_m.end()

    if end_pat is None:
        return text[start:]

    end_m = re.search(end_pat, text[start:], flags=re.I | re.S)
    end = start + end_m.start() if end_m else len(text)

    return text[start:end]


def strip_accents(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def vi_title(s):
    s = clean_cell(s)
    return s.title() if s else None


def hoc_ham_abbr(s):
    key = strip_accents(clean_cell(s) or "").lower()

    mapping = {
        "giao su": "GS.",
        "pho giao su": "PGS.",
    }

    return mapping.get(key, clean_cell(s))


def hoc_vi_abbr(s):
    key = strip_accents(clean_cell(s) or "").lower()

    mapping = {
        "tien si": "TS.",
        "thac si": "ThS.",
        "cu nhan": "CN.",
    }

    return mapping.get(key, clean_cell(s))


def remove_common_noise(text):
    # Xóa footnote ở cuối trang 2 để tránh bị lẫn vào bảng bài báo
    text = re.sub(
        r"\n1 Nêu những tổ chức khoa học.*?(?:kiêm nhiệm\)\.?)",
        "\n",
        text,
        flags=re.I | re.S,
    )
    return text


# =========================
# 2. Tách row dạng bảng theo STT
# =========================

def split_numbered_rows(section_text):
    """
    Tách các dòng bảng dựa vào STT 1, 2, 3...
    Có xử lý trường hợp:
    - STT đứng riêng một dòng: "1"
    - STT dính với text: "44 Vietnamese students..."
    - Tránh nhầm số năm, số tác giả, số trang thành STT
    """
    section_text = remove_common_noise(section_text)

    candidates = list(re.finditer(
        r"(?m)^\s*(\d{1,3})(?=[ \t]|$)(?:[ \t]+.*)?$",
        section_text
    ))

    accepted = []
    expected = 1

    for m in candidates:
        stt = int(m.group(1))

        if stt == expected:
            accepted.append((stt, m))
            expected += 1

    rows = []

    for i, (stt, m) in enumerate(accepted):
        start = m.start()
        end = accepted[i + 1][1].start() if i + 1 < len(accepted) else len(section_text)
        row_text = section_text[start:end].strip()
        rows.append((stt, row_text))

    return rows


def remove_row_number_from_lines(lines, stt):
    if not lines:
        return lines

    lines = lines.copy()
    lines[0] = re.sub(
        rf"^\s*{stt}(?=[ \t]|$)[ \t]*",
        "",
        lines[0]
    ).strip()

    if lines and not lines[0]:
        lines = lines[1:]

    return lines


# =========================
# 3. Parse bài báo / sách
# =========================

VENUE_PATTERNS = [
    r"Kinh tế\s+và\s+Phát triển",
    r"Tạp chí",
    r"TC\s+KTPT",
    r"Kỷ yếu",
    r"Hội thảo",
    r"The\s+\d+(?:st|nd|rd|th)?",
    r"Proceedings",
    r"Journal",
    r"Uncertain\s+Supply\s+Chain",
    r"International\s+(?:Conference|Journal)",
    r"Webology",
    r"Công nghiệp,\s*Số",
    r"NXB",
]


def split_title_place(text, venue_patterns=VENUE_PATTERNS):
    """
    Vì text PDF bị mất cột, ta tách 'tên công trình' và 'nơi công bố'
    bằng các marker thường gặp của nơi công bố: Tạp chí, Kỷ yếu, NXB...
    """
    text = clean_cell(text) or ""

    best = None

    for pat in venue_patterns:
        m = re.search(pat, text, flags=re.I)

        if m and m.start() > 3:
            if best is None or m.start() < best.start():
                best = m

    if not best:
        return clean_cell(text), None

    title = clean_cell(text[:best.start()])
    place = clean_cell(text[best.start():])

    return title, place


def split_page_tail(lines):
    """
    Một vài dòng bị vắt sang trang sau.
    Ví dụ:
    - phần đầu tail thuộc tên công trình
    - phần sau tail thuộc nơi công bố
    """
    place_start = None

    for i, line in enumerate(lines):
        if re.match(r"^(I{1,4}|V|X)\b", line):
            place_start = i
            break

        if re.match(r"^(số|Số|trang|Trang|tháng|Tháng|Vol\.|No\.|pp\.|ISBN)", line):
            place_start = i
            break

    if place_start is None:
        return " ".join(lines), ""

    title_tail = " ".join(lines[:place_start])
    place_tail = " ".join(lines[place_start:])

    return title_tail, place_tail


def parse_publication_like_rows(section_text, role_re):
    rows = []

    for stt, raw in split_numbered_rows(section_text):
        lines = [clean_line(x) for x in raw.splitlines()]
        lines = [x for x in lines if x]
        lines = remove_row_number_from_lines(lines, stt)

        role_idx = None

        for i in range(len(lines) - 1, -1, -1):
            if re.fullmatch(role_re, lines[i], flags=re.I):
                role_idx = i
                break

        if role_idx is not None:
            vai_tro = clean_cell(lines[role_idx])

            year_candidates = [
                i for i in range(role_idx)
                if re.fullmatch(r"(?:\d{1,2}/)?\d{4}", lines[i])
            ]

            year_idx = year_candidates[-1] if year_candidates else None
        else:
            vai_tro = None

            year_candidates = [
                i for i, line in enumerate(lines)
                if re.fullmatch(r"(?:\d{1,2}/)?\d{4}", line)
            ]

            year_idx = year_candidates[-1] if year_candidates else None

        tail_lines = []

        if role_idx is not None and role_idx + 1 < len(lines):
            tail_lines = lines[role_idx + 1:]

        if year_idx is not None:
            nam = clean_cell(lines[year_idx])
            main_before = " ".join(lines[:year_idx])
        else:
            nam = None
            main_before = " ".join(lines)

        ten, noi_cong_bo = split_title_place(main_before)

        if tail_lines:
            title_tail, place_tail = split_page_tail(tail_lines)

            if title_tail:
                ten = clean_cell(f"{ten or ''} {title_tail}")

            if place_tail:
                noi_cong_bo = clean_cell(f"{noi_cong_bo or ''} {place_tail}")

        rows.append({
            "stt": stt,
            "ten": ten,
            "noi_cong_bo": noi_cong_bo,
            "nam": nam,
            "vai_tro": vai_tro,
        })

    return rows


# =========================
# 4. Parse đề tài / dự án
# =========================

def parse_project_rows(section_text, vai_tro_de_tai):
    cap_re = (
        r"(Tương đương\s+cấp\s+bộ|"
        r"Tương đương\s+bộ|"
        r"Cấp\s+cơ\s+sở|"
        r"Nhà\s+nước|"
        r"Cơ\s+sở|"
        r"Bộ)"
    )

    rows = []

    for stt, raw in split_numbered_rows(section_text):
        lines = [clean_line(x) for x in raw.splitlines()]
        lines = [x for x in lines if x]
        lines = remove_row_number_from_lines(lines, stt)

        header_words = (
            "Tên đề tài",
            "Thời gian",
            "Tình trạng",
            "Cấp quản lý",
            "theo Hợp đồng",
            "thời điểm nghiệm",
            "cấp nhà nước",
        )

        lines = [
            x for x in lines
            if not any(hw.lower() in x.lower() for hw in header_words)
        ]

        time_idx = None

        for i, line in enumerate(lines):
            if re.match(r"^\d{4}\s*(?:[-–]\s*\d{4})?(?:,|\s|$)|^\d{4}-\d{4}", line):
                time_idx = i
                break

        if time_idx is None:
            rows.append({
                "stt": stt,
                "vai_tro": vai_tro_de_tai,
                "ten": clean_cell(" ".join(lines)),
                "thoi_gian": None,
                "tinh_trang": None,
                "cap_quan_ly": None,
            })
            continue

        ten = clean_cell(" ".join(lines[:time_idx]))
        rest = clean_cell(" ".join(lines[time_idx:])) or ""

        status_m = re.search(r"(Đã nghiệm thu|Đang thực hiện)", rest, flags=re.I)

        if status_m:
            thoi_gian = clean_cell(rest[:status_m.start()])
            tail = rest[status_m.start():]

            cap_matches = list(re.finditer(cap_re, tail, flags=re.I))

            if cap_matches:
                cap_m = cap_matches[-1]
                tinh_trang = clean_cell(tail[:cap_m.start()])
                cap_quan_ly = clean_cell(cap_m.group(0))
            else:
                tinh_trang = clean_cell(tail)
                cap_quan_ly = None
        else:
            thoi_gian = rest
            tinh_trang = None
            cap_quan_ly = None

        rows.append({
            "stt": stt,
            "vai_tro": vai_tro_de_tai,
            "ten": ten,
            "thoi_gian": thoi_gian,
            "tinh_trang": tinh_trang,
            "cap_quan_ly": cap_quan_ly,
        })

    return rows


# =========================
# 5. Parse bằng sáng chế / giải pháp hữu ích
# =========================

def parse_patent_rows(section_text):
    rows = []

    for stt, raw in split_numbered_rows(section_text):
        lines = [clean_line(x) for x in raw.splitlines()]
        lines = [x for x in lines if x]
        lines = remove_row_number_from_lines(lines, stt)

        date_idx = None

        for i, line in enumerate(lines):
            if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", line):
                date_idx = i
                break

        if date_idx is None:
            rows.append({
                "stt": stt,
                "ten": clean_cell(" ".join(lines)),
                "co_quan_cap": None,
                "ngay_cap": None,
                "so_tac_gia": None,
            })
            continue

        pre = " ".join(lines[:date_idx])

        agency_m = re.search(r"(Cục\s+Thông tin.+)$", pre, flags=re.I)

        if agency_m:
            ten = clean_cell(pre[:agency_m.start()])
            co_quan_cap = clean_cell(agency_m.group(1))
        else:
            ten, co_quan_cap = split_title_place(pre, [r"Cục", r"Bộ", r"Sở"])

        so_tac_gia = None

        for line in lines[date_idx + 1:]:
            if re.fullmatch(r"\d+", line):
                so_tac_gia = int(line)
                break

        rows.append({
            "stt": stt,
            "ten": ten,
            "co_quan_cap": co_quan_cap,
            "ngay_cap": clean_cell(lines[date_idx]),
            "so_tac_gia": so_tac_gia,
        })

    return rows


# =========================
# 6. Parse giải thưởng khoa học
# =========================

def parse_awards(section_text):
    text = clean_cell(section_text) or ""

    awards = re.split(
        r"(?<=\.)\s+(?=Khen thưởng)",
        text
    )

    return [clean_cell(x) for x in awards if clean_cell(x)]


# =========================
# 7. Main extractor
# =========================

def extract_profile(pdf_url):
    pages = read_pages_text(pdf_url)

    full_text = "\n".join(p["text_clean"] for p in pages)
    full_text = remove_common_noise(full_text)

    page1 = pages[0]["text_clean"]

    # --- Thông tin cơ bản ---
    raw_name = search_one(
        r"1\.\s*Họ và tên:\s*(.+?)\n2\.",
        page1
    )

    hoc_ham = search_one(
        r"4\.\s*Học hàm:\s*(.+?)(?:\s+Năm được phong học hàm:|\n)",
        page1
    )

    hoc_vi = search_one(
        r"Học vị:\s*(.+?)(?:\s+Năm đạt học vị:|\n)",
        page1
    )

    chuc_danh_nc = search_one(
        r"5\.\s*Chức danh nghiên cứu:\s*(.+?)\s+Chức vụ:",
        page1
    )

    chuc_vu = search_one(
        r"Chức vụ:\s*(.+?)\n6\.",
        page1
    )

    mobile = search_one(
        r"Mobile:\s*([0-9+\s().-]+)",
        page1
    )

    mobile = re.sub(r"\D", "", mobile) if mobile else None

    ho_ten = clean_cell(" ".join(x for x in [
        hoc_ham_abbr(hoc_ham),
        hoc_vi_abbr(hoc_vi),
        vi_title(raw_name),
    ] if x))

    # --- Tách các mục lớn ---
    sec13 = section_between(
        full_text,
        r"13\.\s*Các bài báo khoa học.*?đã công bố",
        r"14\.\s*Sách"
    )

    sec14 = section_between(
        full_text,
        r"14\.\s*Sách, giáo trình.*?đã công bố",
        r"15\.\s*Các đề tài"
    )

    sec15_full = section_between(
        full_text,
        r"15\.\s*Các đề tài.*?đã chủ\s*trì",
        r"16\.\s*Số công trình"
    )

    split_m = re.search(
        r"Tên đề tài, dự án, nhiệm vụ đã tham\s*gia",
        sec15_full,
        flags=re.I
    )

    if split_m:
        sec15_chu_tri = sec15_full[:split_m.start()]
        sec15_tham_gia = sec15_full[split_m.end():]
    else:
        sec15_chu_tri = sec15_full
        sec15_tham_gia = ""

    sec16 = section_between(
        full_text,
        r"16\.\s*Số công trình.*?Số tác giả",
        r"17\.\s*Giải thưởng"
    )

    sec17 = section_between(
        full_text,
        r"17\.\s*Giải thưởng.*?khoa học",
        r"18\.\s*Kinh nghiệm"
    )

    # --- Parse nested sections ---
    bai_bao = parse_publication_like_rows(
        sec13,
        role_re=r"(Tác giả chính|Đồng tác giả|Tác giả)"
    )

    sach_giao_trinh = parse_publication_like_rows(
        sec14,
        role_re=r"(Chủ biên|Đồng chủ biên|Tham gia|Đồng tác giả|Tác giả)"
    )

    de_tai_du_an = (
        parse_project_rows(sec15_chu_tri, "chu_tri")
        + parse_project_rows(sec15_tham_gia, "tham_gia")
    )

    bang_sang_che = parse_patent_rows(sec16)

    giai_thuong_kh = parse_awards(sec17)

    return {
        "ho_ten": ho_ten,
        "chuc_danh_nc": chuc_danh_nc,
        "chuc_vu": chuc_vu,
        "so_dien_thoai": mobile,
        "bai_bao": bai_bao,
        "sach_giao_trinh": sach_giao_trinh,
        "de_tai_du_an": de_tai_du_an,
        "bang_sang_che": bang_sang_che,
        "giai_thuong_kh": giai_thuong_kh,
    }


if __name__ == "__main__":
    data = extract_profile(PDF_URL)

    print(json.dumps(data, ensure_ascii=False, indent=2))

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to: {OUTPUT_PATH}")