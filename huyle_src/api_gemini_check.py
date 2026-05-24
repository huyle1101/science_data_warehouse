import os, re, time, json
import pandas as pd
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# API KEY ROTATION
API_KEY_LIST = [
    os.getenv("API_KEY_01"),
    os.getenv("API_KEY_02"),
    os.getenv("API_KEY_03"),
    os.getenv("API_KEY_04"),
    os.getenv("API_KEY_05"),
    os.getenv("API_KEY_06"),
]
API_KEY_LIST = [k for k in API_KEY_LIST if k]

if not API_KEY_LIST:
    raise ValueError("No API keys found! Check your .env file.")

print(f"🔑 Found {len(API_KEY_LIST)} API key(s).")

_key_index = 0

def _make_client(key_idx: int) -> genai.Client:
    return genai.Client(api_key=API_KEY_LIST[key_idx])

def _rotate_key() -> bool:
    """Rotate to next key. Returns False if a full cycle was completed."""
    global _key_index
    next_idx = (_key_index + 1) % len(API_KEY_LIST)
    if next_idx == 0 and len(API_KEY_LIST) > 1:
        _key_index = next_idx
        return False
    _key_index = next_idx
    return True

def current_key_label() -> str:
    return f"key[{_key_index + 1}/{len(API_KEY_LIST)}]"

# MODEL ROTATION

MODEL_LIST = [
    os.getenv("MODEL_01"),
    os.getenv("MODEL_02"),
    os.getenv("MODEL_03"),
    os.getenv("MODEL_04"),
    # os.getenv("MODEL_05"),
]
print(f"Model list ({len(MODEL_LIST)}): {MODEL_LIST}")

_model_index = 0

def _rotate_model() -> bool:
    """Rotate to next model. Returns False if a full cycle was completed."""
    global _model_index
    next_idx = (_model_index + 1) % len(MODEL_LIST)
    if next_idx == 0:
        _model_index = next_idx
        return False
    _model_index = next_idx
    return True

def current_model_label() -> str:
    return f"{MODEL_LIST[_model_index]} [{_model_index + 1}/{len(MODEL_LIST)}]"


# CONFIG
INPUT_CSV   = r"output/hust/sme/raw_data/sme.csv"
OUTPUT_CSV  = r"output/hust/sme/processed_data/sme_extracted.csv"

BATCH_SIZE  = 15      # Reduce if MAX_CHARS is large, to avoid exceeding context window
                     # Increase to 10 for paid tier with large context models

DELAY_BETWEEN_BATCHES = 10       # seconds between batch calls
ALL_KEYS_EXHAUSTED_WAIT = 60


MAX_RETRIES  = 4
# # Increase MAX_CHARS to 30_000 to avoid truncating data at end of page
# # (Books, Awards, Tech Transfer usually appear at the bottom of profiles)
# MAX_CHARS    = 30_000



# # PREPROCESSING 
# # Markers indicating start of personal info section (skip nav menu above)
# PROFILE_START_MARKERS = ["Lý lịch khoa học", "Thông tin nhân sự", "Thông tin cơ bản"]

# # Markers indicating footer boilerplate section (skip to save tokens)
# # Appears after the actual profile content ends
# PROFILE_END_MARKERS = [
#     "\nThông tin chung về trường Cơ khí",
#     "\nThông tin chung về trường Cơ Khí",
#     "\nSơ đồ trang sme.hust.edu.vn",
#     "\nBản đồ chỉ dẫn\n",
# ]

# def clean_profile_text(text: str) -> str:
#     """
#     Strip nav/menu boilerplate from top and footer boilerplate from bottom,
#     keeping only the actual profile content.
#     Increase MAX_CHARS to 30_000 to avoid cutting Books, Awards, Tech Transfer.
#     """
#     if not isinstance(text, str):
#         return ""

#     # 1. Strip header boilerplate — find the earliest appearing marker
#     earliest = len(text)
#     for marker in PROFILE_START_MARKERS:
#         pos = text.find(marker)
#         if pos != -1 and pos < earliest:
#             earliest = pos
#     if earliest < len(text):
#         text = text[earliest:]

#     # 2. Strip footer boilerplate — find marker appearing after at least 500 chars
#     #    (ensures we do not accidentally cut real profile content)
#     for fm in PROFILE_END_MARKERS:
#         pos = text.find(fm)
#         if pos != -1 and pos > 500:
#             text = text[:pos]
#             break

#     # 3. Clean HTML entities and extra whitespace
#     text = text.replace("&nbsp;", " ").replace("&amp;", "&")
#     text = re.sub(r"[ \t]+", " ", text)
#     text = re.sub(r"\n{3,}", "\n\n", text)

#     return text.strip()[:MAX_CHARS]


# BATCH PROMPT 
OUTPUT_FIELDS = [
    "dia_chi_lam_viec", "cac_mon_giang_day", "linh_vuc_nghien_cuu",
    "qua_trinh_dao_tao", "cong_trinh_tieu_bieu", "du_an_hien_tai",
    "hv_cao_hoc", "ncs_phd", "sach", "giai_thuong",
    "hop_tac_chuyen_giao", "thong_tin_khac",
]

STRING_FIELDS = {"dia_chi_lam_viec"}

FIELD_DESCRIPTIONS = """
Dưới đây là mô tả từng field cần trích xuất, kèm theo tên section/heading tương ứng
trên trang web (dùng để xác định vị trí dữ liệu trong văn bản):

- dia_chi_lam_viec (string):
    Section: "Địa chỉ làm việc" hoặc "Địa chỉ làm việc:"
    Nội dung: địa chỉ đầy đủ và tên cơ quan/đơn vị công tác, sao chép nguyên văn.
    Ví dụ: "Phòng 207, nhà C3, Trường Đại học Bách Khoa Hà Nội"

- cac_mon_giang_day (list of strings):
    Section: "Giảng dạy/Teaching" hoặc "Các môn giảng dạy" hoặc "Môn học"
    Mỗi phần tử là TÊN ĐẦY ĐỦ một môn học. Liệt kê TẤT CẢ môn, không bỏ sót.
    Ví dụ: ["Lập trình hướng đối tượng", "Cơ sở dữ liệu", "Trí tuệ nhân tạo"]

- linh_vuc_nghien_cuu (list of strings):
    Section: "Lĩnh vực nghiên cứu/Research Areas" hoặc "Lĩnh vực nghiên cứu"
    Mỗi phần tử là một hướng/lĩnh vực nghiên cứu, sao chép nguyên văn.
    Lưu ý: KHÔNG lấy tiêu đề "Lĩnh vực nghiên cứu" từ menu điều hướng của website.
    Chỉ lấy nội dung thực sự liệt kê các hướng nghiên cứu của người đó (thường dạng gạch đầu dòng hoặc danh sách).
    Ví dụ: ["Xử lý ngôn ngữ tự nhiên", "Học máy", "Khai phá dữ liệu"]

- qua_trinh_dao_tao (list of strings):
    Section: "Đào tạo/Educations" hoặc "Quá trình đào tạo"
    Mỗi phần tử là MỘT bằng cấp/giai đoạn, bao gồm năm, bằng cấp, chuyên ngành, trường.
    Ví dụ: ["1999-2004, Kỹ sư Nhiệt Lạnh, Đại học Bách Khoa Hà Nội",
             "2011-2015, Tiến sĩ Nhiệt Lạnh, Đại học Bách Khoa Hà Nội"]

- cong_trinh_tieu_bieu (list of strings):
    Section: "Công trình tiêu biểu/Selected publications" hoặc "Bài báo khoa học tiêu biểu"
    Liệt kê TẤT CẢ công trình/bài báo — nếu có 20 bài thì ghi đủ 20 phần tử.
    Dùng phần tử tiêu đề (e.g., "--- Bài báo quốc tế ---") để phân nhóm nếu hồ sơ có phân loại.
    Mỗi phần tử là một công trình đầy đủ: tác giả, tên bài, tạp chí/hội nghị, số/tập, năm, trang, DOI (nếu có).
    Ví dụ: ["Nguyen V.A., Tran T.B. (2022). Title. Journal Name, 10(2), 100-110."]

- du_an_hien_tai (list of strings):
    Section: "Dự án hiện tại /Project" hoặc "Đề tài nghiên cứu" hoặc "Dự án"
    Mỗi phần tử là MỘT đề tài/dự án đầy đủ, bao gồm: tên đề tài, mã số (nếu có),
    cơ quan tài trợ, thời gian thực hiện, vai trò (Chủ nhiệm/Thành viên).
    Ví dụ: ["Nghiên cứu X, mã số 102.01-2020.15, Bộ KH&CN, 2020-2022, Chủ nhiệm"]

- hv_cao_hoc (list of strings):
    Section: "HV cao học/ Master students" hoặc "Học viên cao học"
    Mỗi phần tử là MỘT học viên, bao gồm tên, đề tài, năm bảo vệ nếu có.

- ncs_phd (list of strings):
    Section: "NCS/ PhD students" hoặc "Nghiên cứu sinh"
    Mỗi phần tử là MỘT nghiên cứu sinh, bao gồm tên, đề tài, năm bảo vệ nếu có.

- sach (list of strings):
    Section: "Sách" hoặc "Sách chuyên khảo và giáo trình tiêu biểu" hoặc "Giáo trình"
    Mỗi phần tử là MỘT cuốn sách/giáo trình, bao gồm: tên sách, tác giả/đồng tác giả,
    NXB, năm xuất bản, vai trò (Chủ biên/Đồng tác giả) nếu có.
    Ví dụ: ["Nguyên lý gia công vật liệu, Bành Tiến Long, Trần Thế Lục, NXB Khoa học và Kỹ thuật, 2001, Chủ biên"]

- giai_thuong (list of strings):
    Section: "Giải thưởng/Awards & Honour" hoặc "Giải thưởng" hoặc "Khen thưởng"
    QUAN TRỌNG: Đây là field hay bị bỏ sót. Tìm kỹ phần này — nội dung thường có dạng:
      "– Giải thưởng X năm Y" hoặc dòng liệt kê các thành tích, bằng khen.
    Mỗi phần tử là MỘT giải thưởng/bằng khen/thành tích, bao gồm tên, tổ chức trao, năm.
    Ví dụ: ["Giải thưởng VIFOTEC về sáng tạo KH&CN, Bộ KH&CN, 2018",
             "Hướng dẫn sinh viên đạt giải nhất NCKH cấp trường năm 2013-2014"]

- hop_tac_chuyen_giao (list of strings):
    Section: "Hợp tác chuyển giao công nghệ" hoặc "Coperation and Tech. Transfer"
    Mỗi phần tử là MỘT hợp tác/chuyển giao, bao gồm tên đối tác, nội dung, thời gian.

- thong_tin_khac (list of strings):
    Section: "Other information" hoặc các thông tin khác chưa thuộc field nào ở trên.
    Bao gồm: chức vụ kiêm nhiệm, thành viên hội đồng biên tập, thành viên hiệp hội nghề nghiệp...
"""

def build_batch_prompt(profiles: list[dict]) -> str:
    """Build a batched prompt from html_text profiles, requesting a JSON array response."""
    blocks = []
    for i, p in enumerate(profiles):
        blocks.append(f"=== PROFILE_{i} | ho_ten={p['ho_ten']} ===\n{p['text']}")

    return f"""Bạn là chuyên gia trích xuất thông tin học thuật từ trang web hồ sơ cán bộ.
Nhiệm vụ: SAO CHÉP và LIỆT KÊ thông tin nguyên văn, KHÔNG tóm tắt, KHÔNG bỏ sót.

Dưới đây là {len(profiles)} hồ sơ lý lịch khoa học, phân cách bằng "=== PROFILE_N ===".
Mỗi profile có nhãn "ho_ten=<tên>" — đây là người cần trích xuất.

Trả về ĐÚNG một JSON array gồm {len(profiles)} object theo thứ tự PROFILE_0, PROFILE_1, ...
Mỗi object có các field sau:
{FIELD_DESCRIPTIONS}
- chua_cong_bo (boolean):
    true nếu trang hồ sơ không có thông tin thực sự — ví dụ chỉ có "Đang cập nhật", rỗng,
    hoặc chỉ có boilerplate/menu mà không có lý lịch khoa học thực của người đó.
    false nếu trang có ít nhất một thông tin thực (địa chỉ, môn học, bài báo, v.v.)

QUY TẮC BẮT BUỘC:
1. CHỈ lấy thông tin của đúng người có tên "ho_ten" trong profile đó.
   Trang web có thể hiển thị thông tin người khác ở phần điều hướng (menu nav) — BỎ QUA.
2. SAO CHÉP NGUYÊN VĂN — không paraphrase, không rút gọn, không dùng "..." thay nội dung thực.
3. LIỆT KÊ ĐẦY ĐỦ — 20 bài báo → 20 phần tử; 10 môn học → 10 phần tử.
4. Các field kiểu list phải là JSON array of strings — mỗi string là một mục hoàn chỉnh.
5. Nếu không tìm thấy thông tin → giá trị null. KHÔNG bịa.
6. KHÔNG thêm bất kỳ text hay markdown nào bên ngoài JSON array.
7. Đặc biệt chú ý các field: linh_vuc_nghien_cuu, cong_trinh_tieu_bieu, du_an_hien_tai,
   sach, giai_thuong, cac_mon_giang_day — đây là các field hay bị bỏ sót nhất.
   Tìm kỹ các section header tương ứng được mô tả ở trên trước khi kết luận là null.

{''.join(chr(10) + b for b in blocks)}

Trả về JSON array:"""


def build_batch_prompt_from_columns(profiles: list[dict], all_columns: list[str]) -> str:
    """
    Prompt waiting trường hợp KHÔNG có html_text.
    Input is a full dump of all existing row columns — data may be misplaced.
    Model sẽ phát hiện nhầm lẫn và sắp xếp lại đúng vào OUTPUT_FIELDS.
    """
    # Columns that are not output fields and not ho_ten — used as data source
    source_cols = [c for c in all_columns if c not in OUTPUT_FIELDS and c != "ho_ten"]

    blocks = []
    for i, p in enumerate(profiles):
        row_dump_lines = []
        for col in source_cols:
            val = p["raw_columns"].get(col)
            if val and str(val).strip() and str(val).strip().lower() not in ("nan", "none", ""):
                row_dump_lines.append(f"  [{col}]: {str(val).strip()}")
        # Also dump existing OUTPUT_FIELDS (may contain misplaced data)
        for col in OUTPUT_FIELDS:
            val = p["raw_columns"].get(col)
            if val and str(val).strip() and str(val).strip().lower() not in ("nan", "none", ""):
                row_dump_lines.append(f"  [{col}]: {str(val).strip()}")

        row_dump = "\n".join(row_dump_lines) if row_dump_lines else "  (no data)"
        blocks.append(
            f"=== PROFILE_{i} | ho_ten={p['ho_ten']} ===\n"
            f"Existing data (may contain column mismatches):\n{row_dump}"
        )

    return f"""Bạn là chuyên gia kiểm tra và chỉnh lý dữ liệu học thuật.

Dưới đây là {len(profiles)} hồ sơ giảng viên. Dữ liệu của mỗi người được liệt kê theo từng cột,
nhưng CÓ THỂ bị nhầm lẫn: thông tin đúng của một field lại nằm trong cột khác,
hoặc một cột chứa nhiều loại thông tin trộn lẫn.

Nhiệm vụ của bạn gồm 2 bước:
1. PHÁT HIỆN nhầm lẫn: xác định thông tin nào đang nằm sai cột.
2. SẮP XẾP LẠI: đọc toàn bộ dữ liệu của từng người và phân loại đúng vào từng field.

Trả về ĐÚNG một JSON array gồm {len(profiles)} object theo thứ tự PROFILE_0, PROFILE_1, ...
Mỗi object có các field sau:
{FIELD_DESCRIPTIONS}
- chua_cong_bo (boolean):
    true nếu toàn bộ dữ liệu của hồ sơ này trống hoặc không có thông tin thực sự.
    false nếu có ít nhất một thông tin thực tìm được.

QUY TẮC BẮT BUỘC:
1. Đọc TẤT CẢ các cột của một người trước khi điền — thông tin cần tìm có thể nằm ở cột bất kỳ.
2. Nếu một giá trị rõ ràng thuộc về field A nhưng đang nằm trong cột B → đặt vào field A.
3. SAO CHÉP NGUYÊN VĂN — không paraphrase, không rút gọn.
4. LIỆT KÊ ĐẦY ĐỦ — mỗi mục là một phần tử riêng trong array.
5. Các field kiểu list phải là JSON array of strings.
6. Nếu thực sự không có thông tin → null. KHÔNG bịa.
7. KHÔNG thêm bất kỳ text hay markdown nào bên ngoài JSON array.
8. Với field thong_tin_khac: nếu phát hiện dữ liệu bị nhầm cột,
   ghi chú ngắn gọn vào đây, ví dụ: "[FIX] dia_chi_lam_viec lấy từ cột url".

{''.join(chr(10) + b for b in blocks)}

Trả về JSON array:"""


# VALIDATE CSV
def validate_csv(df: pd.DataFrame, has_html_text: bool) -> None:
    """
    Validate the CSV before running extraction.
    - has_html_text=True : check fill rate, spot-check rows, warn on 100% null fields
    - has_html_text=False: check column mismatches (HTML tags, abnormal lengths, suspicious values)
    """
    total = len(df)
    print("\n" + "═" * 60)
    print("📊 VALIDATE CSV")
    print("═" * 60)

    if has_html_text:
        # Case 1: html_text present
        print(f"✅ Found cột 'html_text'. Kiểm tra độ phủ các field đã extracted:\n")

        all_null_fields = []
        for f in OUTPUT_FIELDS:
            if f in df.columns:
                filled = df[f].notna().sum()
                pct    = filled / total * 100
                bar    = "█" * int(pct / 5)
                flag   = " ⚠️  NULL 100%" if filled == 0 else ""
                print(f"  {f:<28} {filled:>3}/{total}  ({pct:5.1f}%)  {bar}{flag}")
                if filled == 0:
                    all_null_fields.append(f)
            else:
                print(f"  {f:<28} (column not yet created)")

        if all_null_fields:
            print(f"\n⚠️  Fields with 100% NULL — prompt may not be extracting these correctly:")
            for f in all_null_fields:
                print(f"     • {f}")

        # Spot-check 3 random rows with non-empty html_text
        sample_idx = df[df["html_text"].notna() & (df["html_text"].str.strip() != "")].sample(
            min(3, total), random_state=42
        ).index.tolist()

        print(f"\n🔍 Spot-check {len(sample_idx)} random rows:\n")
        for idx in sample_idx:
            row = df.loc[idx]
            ho_ten = row.get("ho_ten", f"row_{idx}")
            html_preview = str(row.get("html_text", ""))[:300].replace("\n", " ")
            print(f"  ── {ho_ten} (idx={idx}) ──")
            print(f"  html_text (300 chars): {html_preview}...")
            for f in OUTPUT_FIELDS:
                val = row.get(f)
                if pd.notna(val) and str(val).strip():
                    preview = str(val)[:120].replace("\n", " ")
                    print(f"    {f}: {preview}")
            print()

    else:
        # Case 2: no html_text 
        print("⚠️  No 'html_text' column found. Checking for column mismatches:\n")

        issues_found = False

        # 2a. Check for HTML tags inside extracted columns
        html_tag_re = re.compile(r"<[a-zA-Z/][^>]{0,50}>")
        print("  [1] Checking for HTML tags in extracted columns:")
        for f in OUTPUT_FIELDS:
            if f not in df.columns:
                continue
            col_str = df[f].dropna().astype(str)
            has_html = col_str.str.contains(html_tag_re).sum()
            if has_html:
                print(f"    ⚠️  '{f}': {has_html} rows contain HTML tags — html_text may have been placed in wrong column")
                issues_found = True
        if not issues_found:
            print("    ✅ No HTML tags detected in extracted columns.")

        # 2b. Check for abnormally long values (>500 chars) in STRING_FIELDS
        print("\n  [2] Checking for abnormally long values (>500 chars) in string fields:")
        found_long = False
        for f in STRING_FIELDS:
            if f not in df.columns:
                continue
            long_rows = df[df[f].notna() & (df[f].astype(str).str.len() > 500)]
            if not long_rows.empty:
                print(f"    ⚠️  '{f}': {len(long_rows)} rows with values >500 chars")
                for idx, row in long_rows.head(2).iterrows():
                    print(f"       idx={idx}: {str(row[f])[:150]}...")
                found_long = True
                issues_found = True
        if not found_long:
            print("    ✅ No abnormally long values detected.")

        # 2c. Check if ho_ten contains email/URL/address
        print("\n  [3] Checking 'ho_ten' column for mixed data:")
        if "ho_ten" in df.columns:
            suspicious_re = re.compile(
                r"(@|http|www\.|\.com|\.vn|\d{5,}|phòng|tầng|số \d|P\.\d)", re.IGNORECASE
            )
            sus_rows = df[df["ho_ten"].notna() & df["ho_ten"].astype(str).str.contains(suspicious_re)]
            if not sus_rows.empty:
                print(f"    ⚠️  {len(sus_rows)} rows with suspicious ho_ten values:")
                for idx, row in sus_rows.head(5).iterrows():
                    print(f"       idx={idx}: {row['ho_ten']}")
                issues_found = True
            else:
                print("    ✅ ho_ten column looks clean.")

        # 2d. Summary table of sample values for all columns
        print("\n  [4] Sample values for all columns (first 5 rows):\n")
        sample_df = df.head(5)
        for col in df.columns:
            print(f"  ── {col} ──")
            for idx, val in sample_df[col].items():
                preview = str(val)[:100].replace("\n", " ") if pd.notna(val) else "(null)"
                print(f"    idx={idx}: {preview}")
            print()

        if not issues_found:
            print("✅ No obvious mismatches detected. Proceeding with re-extraction from existing columns.")
        else:
            print("⚠️  Issues detected. Script will use Gemini to re-extract and reorganize data.")

    print("═" * 60 + "\n")


# API CALL WITH RETRY + KEY ROTATION
config = types.GenerateContentConfig(
    temperature=0.05,
    response_mime_type="application/json",
    thinking_config=types.ThinkingConfig(thinking_budget=0),
)

def call_batch(profiles: list[dict], prompt_builder=None) -> list[dict]:
    global _key_index

    empty    = lambda: {f: None for f in OUTPUT_FIELDS}
    fallback = [empty() for _ in profiles]
    if prompt_builder is None:
        prompt_builder = build_batch_prompt
    prompt   = prompt_builder(profiles)

    attempt = 0
    keys_tried_this_round = 0

    while attempt < MAX_RETRIES:
        client = _make_client(_key_index)
        try:
            _current_model = MODEL_LIST[_model_index]
            response = client.models.generate_content(
                model=_current_model,
                contents=prompt,
                config=config,
            )
            raw = response.text.strip()

            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if not match:
                raise ValueError(f"No JSON array found in response: {raw[:200]}")

            parsed = json.loads(match.group())
            if not isinstance(parsed, list) or len(parsed) != len(profiles):
                raise ValueError(
                    f"JSON array returned {len(parsed)} items, expected {len(profiles)}"
                )

            results = []
            for item in parsed:
                clean = empty()
                # Nếu Gemini phán đoán trang không có thông tin thực → đánh dấu NO_DATA
                if item.get("chua_cong_bo") is True:
                    clean["thong_tin_khac"] = NO_DATA_LABEL
                    results.append(clean)
                    continue
                for f in OUTPUT_FIELDS:
                    val = item.get(f)
                    if val is None:
                        clean[f] = None
                    elif f in STRING_FIELDS:
                        clean[f] = str(val).strip() if val else None
                    elif isinstance(val, list):
                        items = [str(v).strip() for v in val if v and str(v).strip()]
                        clean[f] = json.dumps(items, ensure_ascii=False) if items else None
                    else:
                        clean[f] = json.dumps([str(val).strip()], ensure_ascii=False)
                results.append(clean)

            keys_tried_this_round = 0
            return results

        except Exception as e:
            err      = str(e)
            is_quota = "429" in err or "RESOURCE_EXHAUSTED" in err
            is_500 = "500" in err or "503" in err or "INTERNAL" in err or "UNAVAILABLE" in err

            if is_quota and len(API_KEY_LIST) > 1:
                keys_tried_this_round += 1
                rotated_full_circle = not _rotate_key()

                if rotated_full_circle or keys_tried_this_round >= len(API_KEY_LIST):
                    print(f"    ⚠️  All {len(API_KEY_LIST)} keys exhausted quota. Waiting {ALL_KEYS_EXHAUSTED_WAIT}s then retrying...")
                    time.sleep(ALL_KEYS_EXHAUSTED_WAIT)
                    keys_tried_this_round = 0
                    attempt += 1
                else:
                    print(f"    🔄 Quota {current_key_label()} — rotating to {current_key_label()}")

            elif is_quota and len(API_KEY_LIST) == 1:
                if attempt < MAX_RETRIES - 1:
                    wait = 15 * (2 ** attempt)
                    print(f"    ⚠️  Quota error (attempt {attempt+1}/{MAX_RETRIES}), "
                          f"waiting {wait}s...")
                    time.sleep(wait)
                attempt += 1

            elif is_500:
                rotated = _rotate_model()
                if rotated:
                    print(f"    Rotate 503 -> model: {current_model_label()}")
                else:
                    # Full model cycle exhausted, sleep then retry
                    wait = 15 * (2 ** attempt)
                    print(f"    503 full model cycle (attempt {attempt+1}/{MAX_RETRIES}), waiting {wait}s...")
                    time.sleep(wait)
                    attempt += 1

            else:
                print(f"    ❌ Batch failed ({current_key_label()}): {err[:150]}")
                for r in fallback:
                    r["thong_tin_khac"] = f"ERROR: {err[:100]}"
                return fallback

    print(f"    ❌ Max retries reached ({MAX_RETRIES}). Skipping this batch.")
    for r in fallback:
        r["thong_tin_khac"] = "ERROR: max retries exceeded"
    return fallback


# MAIN 
NO_DATA_LABEL = "Thông tin không được công bố"

def main():
    raw_df = pd.read_csv(OUTPUT_CSV) if os.path.exists(OUTPUT_CSV) else pd.read_csv(INPUT_CSV)

    # Xóa duplicate header rows, lưu vào df sạch — dùng xuyên suốt
    dup_mask = raw_df.apply(lambda r: r.astype(str).eq(raw_df.columns).all(), axis=1)
    if dup_mask.any():
        print(f"🧹 Removed {dup_mask.sum()} duplicate header rows.")
    df = raw_df[~dup_mask].reset_index(drop=True)

    total = len(df)
    print(f"📂 Loaded {total} rows from {OUTPUT_CSV if os.path.exists(OUTPUT_CSV) else INPUT_CSV}")
    print(f"📋 Available columns: {list(df.columns)}")

    # Detect mode: html_text present or not
    has_html_text = "html_text" in df.columns and df["html_text"].notna().any()
    if has_html_text:
        print("🟢 Mode: EXTRACT from html_text")
    else:
        print("🟡 Mode: RE-EXTRACT + FIX column mismatch (no html_text)")

    # Validate CSV before processing
    validate_csv(df, has_html_text)

    # Initialize output fields if not present
    for f in OUTPUT_FIELDS:
        if f not in df.columns:
            df[f] = None

    # Pre-mark các dòng html_text rỗng / chỉ có boilerplate là NO_DATA (chỉ khi chưa đánh dấu)
    if has_html_text:
        NO_DATA_PATTERNS = ["đang cập nhật", "updating", "coming soon", "to be updated"]

        def _is_no_data(text) -> bool:
            if pd.isna(text):
                return True
            s = str(text).strip()
            if not s:
                return True
            s_lower = s.lower()
            # Nếu text ngắn (< 100 ký tự) VÀ chứa keyword boilerplate → không có thông tin thực
            if len(s) < 100 and any(p in s_lower for p in NO_DATA_PATTERNS):
                return True
            return False

        not_yet_marked = ~df["thong_tin_khac"].str.startswith(NO_DATA_LABEL, na=False)
        to_mark = df["html_text"].apply(_is_no_data) & not_yet_marked
        if to_mark.any():
            print(f"ℹ️  Pre-marked {to_mark.sum()} rows as '{NO_DATA_LABEL}' (html_text rỗng/boilerplate).")
            df.loc[to_mark, "thong_tin_khac"] = NO_DATA_LABEL

    non_error_fields = [f for f in OUTPUT_FIELDS if f != "thong_tin_khac"]
    has_any_data  = df[non_error_fields].notna().any(axis=1)
    has_error     = df["thong_tin_khac"].str.startswith("ERROR", na=False)
    not_published = df["thong_tin_khac"].str.startswith(NO_DATA_LABEL, na=False)
    # Skip các dòng "Thông tin không được công bố" — không check, không process
    done_mask = (has_any_data & ~has_error) | not_published
    todo = df.index[~done_mask].tolist()
    total_batches = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE

    if not_published.sum():
        print(f"ℹ️  Skipping {not_published.sum()} rows '{NO_DATA_LABEL}'.")

    print(f"📋 To process: {len(todo)} rows → {total_batches} batches "
          f"(batch_size={BATCH_SIZE})")
    print(f"⏱️  Estimated: ~{total_batches * (DELAY_BETWEEN_BATCHES + 5) // 60 + 1} min\n")

    # Select prompt builder based on mode
    all_columns = list(df.columns)
    if has_html_text:
        def prompt_builder(profiles):
            return build_batch_prompt(profiles)
    else:
        def prompt_builder(profiles):
            return build_batch_prompt_from_columns(profiles, all_columns)

    start = datetime.now()

    for batch_num, chunk_start in enumerate(range(0, len(todo), BATCH_SIZE), 1):
        chunk_idx = todo[chunk_start: chunk_start + BATCH_SIZE]
        profiles = []
        for idx in chunk_idx:
            row = df.loc[idx]
            if has_html_text:
                profiles.append({
                    "ho_ten":      row.get("ho_ten", f"row_{idx}"),
                    "text":        row.get("html_text", "") or "",
                    "idx":         idx,
                })
            else:
                profiles.append({
                    "ho_ten":      row.get("ho_ten", f"row_{idx}"),
                    "raw_columns": row.to_dict(),
                    "idx":         idx,
                })

        names  = ", ".join(p["ho_ten"] for p in profiles[:3])
        suffix = f"... (+{len(profiles)-3})" if len(profiles) > 3 else ""
        print(f"[Batch {batch_num}/{total_batches}] {current_key_label()} | {current_model_label()} | {names}{suffix}")

        results = call_batch(profiles, prompt_builder=prompt_builder)

        for profile, result in zip(profiles, results):
            for f, v in result.items():
                df.at[profile["idx"], f] = v

        # Luôn xuất df sạch — không có duplicate headers
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        print(f"  ✅ Saved checkpoint → {OUTPUT_CSV}")

        if batch_num < total_batches:
            time.sleep(DELAY_BETWEEN_BATCHES)

    elapsed = datetime.now() - start
    print(f"\n🎉 Done! Total time: {elapsed}")
    print(f"📄 Output file: {OUTPUT_CSV}\n")

    # Thống kê cuối — dùng df sạch
    not_published   = df["thong_tin_khac"].str.startswith(NO_DATA_LABEL, na=False)
    has_error_final = df["thong_tin_khac"].str.startswith("ERROR", na=False)
    has_data_final  = df[non_error_fields].notna().any(axis=1)
    error_count     = ((~has_data_final | has_error_final) & ~not_published).sum()
    nodata_count    = not_published.sum()

    if nodata_count:
        print(f"  ℹ️  {nodata_count} rows '{NO_DATA_LABEL}' (bỏ qua).")
    if error_count:
        print(f"  ⚠️  {error_count} rows with errors — re-run script to retry automatically.")
    print("── Statistics ──")
    for f in OUTPUT_FIELDS:
        filled = df[f].notna().sum()
        bar    = "█" * int(filled / total * 20)
        print(f"  {f:<28} {filled:>3}/{total}  {bar}")
    if error_count:
        print(f"\n  ⚠️  {error_count} rows with errors — re-run script to retry automatically.")


if __name__ == "__main__":
    main()