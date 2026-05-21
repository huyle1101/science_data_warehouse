"""
Script xử lý batch CSV sme.csv với Gemini API
Strategy: BATCH JSON mode — gộp N profiles/request → giảm 10x số API calls
"""

import os, re, time, json
import pandas as pd
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv('API_KEY_06'))

# ─── CONFIG ────────────────────────────────────────────────────────────────────
MODEL_NAME  = "gemini-3.1-flash-lite"   # hoặc "gemini-1.5-flash" nếu muốn rẻ hơn, nhưng chất lượng kém hơn chút
INPUT_CSV   = "output\hust\sme\data\sme.csv"
OUTPUT_CSV  = "output\hust\sme\data\sme_extracted.csv"

BATCH_SIZE  = 10     # profiles per API call  → 267 rows = ~27 calls thay vì 267
                     # Giảm xuống 5 nếu vẫn còn lỗi 429

# Free tier: 10 RPM → delay 8s/call là an toàn cho batch
# Paid tier: tăng BATCH_SIZE lên 20, giảm DELAY xuống 2s
DELAY_BETWEEN_BATCHES = 8        # giây giữa các batch call

MAX_RETRIES  = 4
MAX_CHARS    = 15_000            # mỗi profile sau khi clean ~4-5K, batch 10 = ~50K


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

FIELD_DESCRIPTIONS = """
- dia_chi_lam_viec: địa chỉ/cơ quan công tác hiện tại
- cac_mon_giang_day: các môn đang giảng dạy
- linh_vuc_nghien_cuu: hướng/lĩnh vực nghiên cứu
- qua_trinh_dao_tao: học vấn, bằng cấp, nơi đào tạo
- cong_trinh_tieu_bieu: bài báo, công trình nổi bật
- du_an_hien_tai: dự án/đề tài đang thực hiện
- hv_cao_hoc: thông tin hướng dẫn học viên cao học
- ncs_phd: thông tin hướng dẫn nghiên cứu sinh
- sach: sách, giáo trình đã xuất bản
- giai_thuong: giải thưởng, khen thưởng
- hop_tac_chuyen_giao: hợp tác quốc tế, chuyển giao công nghệ
- thong_tin_khac: thông tin khác không thuộc các mục trên
"""

def build_batch_prompt(profiles: list[dict]) -> str:
    """Tạo prompt gộp nhiều profile, yêu cầu trả về JSON array."""
    blocks = []
    for i, p in enumerate(profiles):
        blocks.append(f"=== PROFILE_{i} | {p['ho_ten']} ===\n{p['text']}")
    
    return f"""Bạn là chuyên gia trích xuất thông tin học thuật.
Dưới đây là {len(profiles)} hồ sơ lý lịch khoa học được phân cách bằng "=== PROFILE_N ===".

Trích xuất thông tin từ TỪNG hồ sơ và trả về ĐÚNG một JSON array gồm {len(profiles)} object.
Mỗi object có các field:{FIELD_DESCRIPTIONS}
- Nếu không tìm thấy thông tin cho field nào, để giá trị null.
- KHÔNG thêm bất kỳ text, giải thích, hay markdown nào ngoài JSON array.
- Thứ tự object trong array phải tương ứng với thứ tự PROFILE_0, PROFILE_1, ...

{''.join(chr(10) + b for b in blocks)}

Trả về JSON array:"""


# ─── GỌI API VỚI RETRY ────────────────────────────────────────────────────────
config = types.GenerateContentConfig(
    temperature=0.05,
    response_mime_type="application/json",   # buộc output là JSON
    thinking_config=types.ThinkingConfig(thinking_budget=0),  # tắt thinking chạy nhanh hơn
)

def call_batch(profiles: list[dict]) -> list[dict]:
    """Gọi Gemini với N profiles, trả về list N kết quả."""
    empty = lambda: {f: None for f in OUTPUT_FIELDS}
    fallback = [empty() for _ in profiles]
    prompt = build_batch_prompt(profiles)

    for attempt in range(MAX_RETRIES):
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

            # Đảm bảo chỉ giữ các field hợp lệ
            results = []
            for item in parsed:
                clean = empty()
                for f in OUTPUT_FIELDS:
                    val = item.get(f)
                    clean[f] = str(val).strip() if val else None
                results.append(clean)
            return results

        except Exception as e:
            err = str(e)
            is_quota = "429" in err or "RESOURCE_EXHAUSTED" in err
            is_500   = "500" in err or "INTERNAL" in err

            if (is_quota or is_500) and attempt < MAX_RETRIES - 1:
                # Với quota exhausted, wait lâu hơn nhiều
                wait = 15 * (2 ** attempt)  # 15s, 30s, 60s
                print(f"    ⚠️  {'Quota' if is_quota else 'Server'} error "
                      f"(attempt {attempt+1}/{MAX_RETRIES}), chờ {wait}s...")
                time.sleep(wait)
            else:
                print(f"    ❌ Batch thất bại: {err[:150]}")
                # Đánh dấu lỗi vào thong_tin_khac để dễ retry sau
                for r in fallback:
                    r["thong_tin_khac"] = f"ERROR: {err[:100]}"
                return fallback

    return fallback


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    df = pd.read_csv(OUTPUT_CSV) if os.path.exists(OUTPUT_CSV) else pd.read_csv(INPUT_CSV)
    total = len(df)
    print(f"📂 Loaded {total} rows từ {OUTPUT_CSV}")

    # Khởi tạo cột output
    for f in OUTPUT_FIELDS:
        if f not in df.columns:
            df[f] = None

    # Resume: bỏ qua row đã xử lý thành công (không phải ERROR)
    # done_mask = (
    #     df["dia_chi_lam_viec"].notna() |
    #     (df["thong_tin_khac"].notna() & ~df["thong_tin_khac"].str.startswith("ERROR", na=False))
    # )

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
                "text": clean_profile_text(row.get("html_text", "")),
                "idx": idx,
            })

        names = ", ".join(p["ho_ten"] for p in profiles[:3])
        suffix = f"... (+{len(profiles)-3})" if len(profiles) > 3 else ""
        print(f"[Batch {batch_num}/{total_batches}] {names}{suffix}")

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
        bar = "█" * int(filled / total * 20)
        print(f"  {f:<28} {filled:>3}/{total}  {bar}")
    if errors:
        print(f"\n  ⚠️  {errors} rows bị lỗi — chạy lại script để retry tự động.")


if __name__ == "__main__":
    main()