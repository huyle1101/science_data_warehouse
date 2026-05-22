"""
Script xử lý batch CSV sme.csv với Gemini API
Strategy: BATCH JSON mode — gộp N profiles/request → giảm 10x số API calls
Key rotation: tự động xoay vòng API key khi chạm quota (429/RESOURCE_EXHAUSTED)
"""

import os, re, time, json
import pandas as pd
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# ─── API KEY ROTATION ──────────────────────────────────────────────────────────
# Thêm/bớt key tại đây. Script sẽ tự xoay vòng khi key hiện tại chạm quota.
API_KEY_LIST = [
    os.getenv("API_KEY_01"),
    os.getenv("API_KEY_02"),
    os.getenv("API_KEY_03"),
    os.getenv("API_KEY_04"),
    os.getenv("API_KEY_05"),
    os.getenv("API_KEY_06"),
]
# Lọc bỏ các key None/rỗng (chưa set trong .env)
API_KEY_LIST = [k for k in API_KEY_LIST if k]

if not API_KEY_LIST:
    raise ValueError("Không tìm thấy API key nào! Kiểm tra file .env.")

print(f"🔑 Tìm thấy {len(API_KEY_LIST)} API key(s).")

_key_index = 0   # index của key đang dùng

def _make_client(key_idx: int) -> genai.Client:
    return genai.Client(api_key=API_KEY_LIST[key_idx])

def _rotate_key() -> bool:
    """Chuyển sang key tiếp theo. Trả về False nếu đã hết vòng."""
    global _key_index
    next_idx = (_key_index + 1) % len(API_KEY_LIST)
    if next_idx == 0 and len(API_KEY_LIST) > 1:
        # Đã quay về key đầu tiên → hết một vòng đầy
        _key_index = next_idx
        return False   # báo hiệu đã xoay hết 1 vòng
    _key_index = next_idx
    return True

def current_key_label() -> str:
    return f"key[{_key_index + 1}/{len(API_KEY_LIST)}]"


# ─── CONFIG ────────────────────────────────────────────────────────────────────
MODEL_NAME  = "gemini-3.1-flash-lite"   # hoặc "gemini-1.5-flash" nếu muốn rẻ hơn
INPUT_CSV   = r"output/hust/sme/raw_data/sme.csv"
OUTPUT_CSV  = r"output/hust/sme/processed_data/sme_extracted.csv"

BATCH_SIZE  = 10     # profiles per API call  → 267 rows = ~27 calls thay vì 267
                     # Giảm xuống 5 nếu vẫn còn lỗi 429

# Free tier: 10 RPM → delay 8s/call là an toàn cho batch
# Paid tier: tăng BATCH_SIZE lên 20, giảm DELAY xuống 2s
DELAY_BETWEEN_BATCHES = 8        # giây giữa các batch call

MAX_RETRIES  = 4     # số lần thử lại tối đa mỗi batch (tính cả xoay key)
MAX_CHARS    = 15_000            # mỗi profile sau khi clean ~4-5K, batch 10 = ~50K

# Thời gian chờ khi TẤT CẢ key đều bị quota — trước khi thử lại từ đầu
ALL_KEYS_EXHAUSTED_WAIT = 60     # giây


# ─── TIỀN XỬ LÝ ───────────────────────────────────────────────────────────────
PROFILE_MARKERS = ["Lý lịch khoa học", "Thông tin nhân sự", "Thông tin cơ bản"]

def clean_profile_text(text: str) -> str:
    """Cắt boilerplate nav/menu, chỉ giữ nội dung profile."""
    if not isinstance(text, str):
        return ""
    earliest = len(text)
    for marker in PROFILE_MARKERS:
        pos = text.find(marker)
        if pos != -1 and pos < earliest:
            earliest = pos
    if earliest < len(text):
        text = text[earliest:]
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_CHARS]


# ─── BATCH PROMPT ─────────────────────────────────────────────────────────────
OUTPUT_FIELDS = [
    "dia_chi_lam_viec", "cac_mon_giang_day", "linh_vuc_nghien_cuu",
    "qua_trinh_dao_tao", "cong_trinh_tieu_bieu", "du_an_hien_tai",
    "hv_cao_hoc", "ncs_phd", "sach", "giai_thuong",
    "hop_tac_chuyen_giao", "thong_tin_khac",
]

# Field nào trả về string đơn, field nào trả về list
STRING_FIELDS = {"dia_chi_lam_viec"}   # chỉ những field thực sự là 1 giá trị duy nhất

FIELD_DESCRIPTIONS = """
- dia_chi_lam_viec (string): địa chỉ đầy đủ và tên cơ quan/đơn vị công tác hiện tại, sao chép nguyên văn

- cac_mon_giang_day (list of strings): mỗi phần tử là TÊN ĐẦY ĐỦ một môn học.
  Ví dụ: ["Lập trình hướng đối tượng", "Cơ sở dữ liệu", "Trí tuệ nhân tạo"]

- linh_vuc_nghien_cuu (list of strings): mỗi phần tử là một hướng/lĩnh vực nghiên cứu, sao chép nguyên văn.
  Ví dụ: ["Xử lý ngôn ngữ tự nhiên", "Học máy", "Khai phá dữ liệu"]

- qua_trinh_dao_tao (list of strings): mỗi phần tử là MỘT bằng cấp/giai đoạn đào tạo, bao gồm bằng cấp, chuyên ngành, trường, năm.
  Ví dụ: ["Tiến sĩ Khoa học Máy tính, ĐH Tokyo, 2005", "Thạc sĩ CNTT, ĐHBK Hà Nội, 2001"]

- cong_trinh_tieu_bieu (list of strings): mỗi phần tử là MỘT công trình/bài báo đầy đủ.
  Nhóm theo loại bằng phần tử tiêu đề nếu hồ sơ có phân loại (bài báo quốc tế, bài báo trong nước, hội thảo...).
  Ví dụ: ["--- Bài báo quốc tế ---", "Nguyen V.A., Tran T.B. (2022). Title. Journal Name, 10(2), 100-110. DOI:...", "--- Hội thảo ---", "Nguyen V.A. (2021). Title. Proc. AAAI, pp.50-55."]

- du_an_hien_tai (list of strings): mỗi phần tử là MỘT đề tài/dự án đầy đủ, bao gồm tên, mã số, cấp, vai trò, thời gian, kinh phí nếu có.
  Ví dụ: ["Đề tài NAFOSTED mã số 102.01-2020.15: 'Nghiên cứu ...', Chủ nhiệm, 2020-2022, 500 triệu đồng"]

- hv_cao_hoc (list of strings): mỗi phần tử là MỘT học viên, bao gồm tên, đề tài, năm bảo vệ nếu có.
  Ví dụ: ["Nguyễn Văn A — 'Đề tài X' — Bảo vệ 2021"]

- ncs_phd (list of strings): mỗi phần tử là MỘT nghiên cứu sinh, bao gồm tên, đề tài, năm bảo vệ nếu có.

- sach (list of strings): mỗi phần tử là MỘT cuốn sách/giáo trình, bao gồm tên, NXB, năm, đồng tác giả nếu có.
  Ví dụ: ["Giáo trình Lập trình Python, NXB ĐHQG, 2020, đồng tác giả: Trần T.B."]

- giai_thuong (list of strings): mỗi phần tử là MỘT giải thưởng/bằng khen, bao gồm tên giải, tổ chức trao, năm.

- hop_tac_chuyen_giao (list of strings): mỗi phần tử là MỘT hợp tác/chuyển giao, bao gồm tên đối tác, nội dung, thời gian.

- thong_tin_khac (list of strings): mỗi phần tử là MỘT thông tin còn lại (chức vụ, thành viên hội đồng, biên tập tạp chí...).
"""

def build_batch_prompt(profiles: list[dict]) -> str:
    """Tạo prompt gộp nhiều profile, yêu cầu trả về JSON array với list cho mỗi field đa giá trị."""
    blocks = []
    for i, p in enumerate(profiles):
        blocks.append(f"=== PROFILE_{i} | ho_ten={p['ho_ten']} ===\n{p['text']}")

    return f"""Bạn là chuyên gia trích xuất thông tin học thuật. Nhiệm vụ của bạn là SAO CHÉP và LIỆT KÊ thông tin, KHÔNG phải tóm tắt.

Dưới đây là {len(profiles)} hồ sơ lý lịch khoa học được phân cách bằng "=== PROFILE_N ===".
Mỗi profile có nhãn "ho_ten=<tên người>" — đây là tên người CẦN trích xuất thông tin.

Trích xuất thông tin từ TỪNG hồ sơ và trả về ĐÚNG một JSON array gồm {len(profiles)} object.
Mỗi object có các field sau:
{FIELD_DESCRIPTIONS}

QUY TẮC BẮT BUỘC:
1. CHỈ LẤY thông tin của đúng người có tên "ho_ten" trong profile đó.
   Nếu trang web bị lỗi và hiển thị thông tin của người KHÁC (tên khác với ho_ten), hãy BỎ QUA thông tin đó.
   Chỉ giữ lại những gì chắc chắn thuộc về người có tên ho_ten.
2. SAO CHÉP NGUYÊN VĂN — không paraphrase, không rút gọn, không dùng "..." hay "v.v." thay cho nội dung thực.
3. LIỆT KÊ ĐẦY ĐỦ — nếu có 20 bài báo thì ghi đủ 20 phần tử trong list, nếu có 10 môn học thì ghi đủ 10.
4. Các field kiểu list phải là JSON array of strings — mỗi string là một mục hoàn chỉnh, không lồng array.
5. Nếu không tìm thấy thông tin cho field nào, để giá trị null — KHÔNG bịa thêm.
6. KHÔNG thêm bất kỳ text, giải thích, hay markdown nào bên ngoài JSON array.
7. Thứ tự object trong array phải tương ứng với PROFILE_0, PROFILE_1, ...

{''.join(chr(10) + b for b in blocks)}
 
Trả về JSON array:"""


# ─── GỌI API VỚI RETRY + KEY ROTATION ────────────────────────────────────────
config = types.GenerateContentConfig(
    temperature=0.05,
    response_mime_type="application/json",   # buộc output là JSON
    thinking_config=types.ThinkingConfig(thinking_budget=0),  # tắt thinking → nhanh hơn
)

def call_batch(profiles: list[dict]) -> list[dict]:
    """
    Gọi Gemini với N profiles, trả về list N kết quả.
    Khi gặp quota error (429): xoay sang key tiếp theo ngay lập tức.
    Nếu tất cả key đều hết quota: chờ ALL_KEYS_EXHAUSTED_WAIT giây rồi thử lại.
    """
    global _key_index

    empty    = lambda: {f: None for f in OUTPUT_FIELDS}
    fallback = [empty() for _ in profiles]
    prompt   = build_batch_prompt(profiles)

    attempt = 0
    keys_tried_this_round = 0   # đếm số key đã thử trong 1 vòng liên tiếp lỗi quota

    while attempt < MAX_RETRIES:
        client = _make_client(_key_index)
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=config,
            )
            raw = response.text.strip()

            # Bóc JSON ra dù có bị bọc trong ```json hay không
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if not match:
                raise ValueError(f"Không tìm thấy JSON array trong response: {raw[:200]}")

            parsed = json.loads(match.group())
            if not isinstance(parsed, list) or len(parsed) != len(profiles):
                raise ValueError(
                    f"JSON array trả về {len(parsed)} items, mong đợi {len(profiles)}"
                )

            # Đảm bảo chỉ giữ các field hợp lệ, giữ nguyên list/string tùy field
            results = []
            for item in parsed:
                clean = empty()
                for f in OUTPUT_FIELDS:
                    val = item.get(f)
                    if val is None:
                        clean[f] = None
                    elif f in STRING_FIELDS:
                        # Field string đơn
                        clean[f] = str(val).strip() if val else None
                    elif isinstance(val, list):
                        # Field list: lọc bỏ phần tử rỗng, serialize thành JSON string để lưu CSV
                        items = [str(v).strip() for v in val if v and str(v).strip()]
                        clean[f] = json.dumps(items, ensure_ascii=False) if items else None
                    else:
                        # Model trả về string thay vì list → bọc vào list 1 phần tử
                        clean[f] = json.dumps([str(val).strip()], ensure_ascii=False)
                results.append(clean)

            # Reset bộ đếm key khi thành công
            keys_tried_this_round = 0
            return results

        except Exception as e:
            err      = str(e)
            is_quota = "429" in err or "RESOURCE_EXHAUSTED" in err
            is_500   = "500" in err or "INTERNAL" in err

            if is_quota and len(API_KEY_LIST) > 1:
                # ── Xoay key trước khi quyết định chờ ──
                keys_tried_this_round += 1
                rotated_full_circle = not _rotate_key()

                if rotated_full_circle or keys_tried_this_round >= len(API_KEY_LIST):
                    # Đã thử hết tất cả key → chờ rồi bắt đầu vòng mới
                    print(f"    ⚠️  Tất cả {len(API_KEY_LIST)} key đều bị quota. "
                          f"Chờ {ALL_KEYS_EXHAUSTED_WAIT}s rồi thử lại...")
                    time.sleep(ALL_KEYS_EXHAUSTED_WAIT)
                    keys_tried_this_round = 0
                    attempt += 1
                else:
                    print(f"    🔄 Quota {current_key_label()} — xoay sang {current_key_label()}")
                    # Không tăng attempt khi chỉ xoay key (chưa tốn 1 retry thực sự)

            elif is_quota and len(API_KEY_LIST) == 1:
                # Chỉ có 1 key → fallback về chờ theo exponential backoff
                if attempt < MAX_RETRIES - 1:
                    wait = 15 * (2 ** attempt)   # 15s, 30s, 60s
                    print(f"    ⚠️  Quota error (attempt {attempt+1}/{MAX_RETRIES}), "
                          f"chờ {wait}s... (chỉ có 1 key)")
                    time.sleep(wait)
                attempt += 1

            elif is_500 and attempt < MAX_RETRIES - 1:
                wait = 15 * (2 ** attempt)
                print(f"    ⚠️  Server error (attempt {attempt+1}/{MAX_RETRIES}), chờ {wait}s...")
                time.sleep(wait)
                attempt += 1

            else:
                print(f"    ❌ Batch thất bại ({current_key_label()}): {err[:150]}")
                for r in fallback:
                    r["thong_tin_khac"] = f"ERROR: {err[:100]}"
                return fallback

    print(f"    ❌ Hết số lần retry ({MAX_RETRIES}). Bỏ qua batch này.")
    for r in fallback:
        r["thong_tin_khac"] = "ERROR: max retries exceeded"
    return fallback


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    df = pd.read_csv(OUTPUT_CSV) if os.path.exists(OUTPUT_CSV) else pd.read_csv(INPUT_CSV)
    total = len(df)
    print(f"📂 Loaded {total} rows từ {OUTPUT_CSV if os.path.exists(OUTPUT_CSV) else INPUT_CSV}")

    # Khởi tạo cột output
    for f in OUTPUT_FIELDS:
        if f not in df.columns:
            df[f] = None

    non_error_fields = [f for f in OUTPUT_FIELDS if f != "thong_tin_khac"]
    has_any_data = df[non_error_fields].notna().any(axis=1)
    has_error    = df["thong_tin_khac"].str.startswith("ERROR", na=False)
    done_mask    = has_any_data & ~has_error
    todo = df.index[~done_mask].tolist()
    total_batches = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE

    print(f"📋 Cần xử lý: {len(todo)} rows → {total_batches} batches "
          f"(batch_size={BATCH_SIZE})")
    print(f"⏱️  Ước tính: ~{total_batches * (DELAY_BETWEEN_BATCHES + 5) // 60 + 1} phút\n")

    start = datetime.now()

    for batch_num, chunk_start in enumerate(range(0, len(todo), BATCH_SIZE), 1):
        chunk_idx = todo[chunk_start: chunk_start + BATCH_SIZE]
        profiles = []
        for idx in chunk_idx:
            row = df.loc[idx]
            profiles.append({
                "ho_ten": row.get("ho_ten", f"row_{idx}"),
                "text":   clean_profile_text(row.get("html_text", "")),
                "idx":    idx,
            })

        names  = ", ".join(p["ho_ten"] for p in profiles[:3])
        suffix = f"... (+{len(profiles)-3})" if len(profiles) > 3 else ""
        print(f"[Batch {batch_num}/{total_batches}] {current_key_label()} | {names}{suffix}")

        results = call_batch(profiles)

        # Ghi kết quả
        for profile, result in zip(profiles, results):
            for f, v in result.items():
                df.at[profile["idx"], f] = v

        # Checkpoint
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        print(f"  ✅ Saved checkpoint → {OUTPUT_CSV}")

        if batch_num < total_batches:
            time.sleep(DELAY_BETWEEN_BATCHES)

    elapsed = datetime.now() - start
    print(f"\n🎉 Xong! Tổng thời gian: {elapsed}")
    print(f"📄 File output: {OUTPUT_CSV}\n")

    # Thống kê
    df_out = pd.read_csv(OUTPUT_CSV)
    errors = df_out["thong_tin_khac"].str.startswith("ERROR", na=False).sum()
    print("── Thống kê ──")
    for f in OUTPUT_FIELDS:
        filled = df_out[f].notna().sum()
        bar    = "█" * int(filled / total * 20)
        print(f"  {f:<28} {filled:>3}/{total}  {bar}")
    if errors:
        print(f"\n  ⚠️  {errors} rows bị lỗi — chạy lại script để retry tự động.")


if __name__ == "__main__":
    main()