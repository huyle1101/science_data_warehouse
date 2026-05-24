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
    # os.getenv("MODEL_05")
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

BATCH_SIZE  = 10     # Reduce if MAX_CHARS is large, to avoid exceeding context window

DELAY_BETWEEN_BATCHES = 10       # seconds between batch calls
ALL_KEYS_EXHAUSTED_WAIT = 60

MAX_RETRIES  = 4

# These will be populated by detect_schema() at startup
OUTPUT_FIELDS    = []   # list of column names to extract into
STRING_FIELDS    = set() # subset of OUTPUT_FIELDS that are plain strings (not lists)
FIELD_DESCRIPTIONS = "" # injected into system prompt
IDENTITY_COL     = "ho_ten"  # best-guess name column, overridden by detect_schema


# ── SCHEMA DETECTION (one-time startup call) ──────────────────────────────────

def detect_schema(df: pd.DataFrame) -> None:
    """
    One Gemini call at startup: inspects column names + sample values and returns
    a JSON schema describing each column's role and extraction instructions.
    Populates OUTPUT_FIELDS, STRING_FIELDS, FIELD_DESCRIPTIONS, IDENTITY_COL.
    """
    global OUTPUT_FIELDS, STRING_FIELDS, FIELD_DESCRIPTIONS, IDENTITY_COL

    # Build a compact sample: column name + up to 3 non-null sample values
    sample_rows = df.dropna(how="all").head(20)
    col_samples = {}
    for col in df.columns:
        vals = sample_rows[col].dropna().astype(str).str.strip()
        vals = [v for v in vals if v and v.lower() not in ("nan", "none", "")]
        col_samples[col] = vals[:3]

    col_summary_lines = []
    for col, samples in col_samples.items():
        samples_str = " | ".join(f'"{s[:120]}"' for s in samples) if samples else "(all empty)"
        col_summary_lines.append(f"  - {col}: {samples_str}")
    col_summary = "\n".join(col_summary_lines)

    detection_prompt = f"""You are a data schema analyst. Below are the columns of a CSV file,
each with up to 3 sample values. The file contains profiles of people (researchers, faculty, students, etc.).

Columns and samples:
{col_summary}

Your task: classify each column and return ONLY a JSON object (no markdown, no explanation) with this structure:
{{
  "identity_col": "<column name that uniquely identifies a person — typically full name>",
  "source_text_col": "<column name containing raw scraped text/HTML to extract from, or null if absent>",
  "output_fields": [
    {{
      "name": "<column name>",
      "type": "string" | "list",
      "description": "<2-3 sentence extraction instruction in the same language as the column data: what to look for, how to format each value, verbatim copy rules, example value>",
      "priority": "high" | "normal"
    }},
    ...
  ]
}}

Rules for classifying columns:
- identity_col: the person's name or unique ID — NOT an output field.
- source_text_col: raw HTML/text blob used as extraction source — NOT an output field.
- output_fields: ONLY columns that contain or should contain structured facts about the person.
  Focus especially on: research areas, publications, projects, scientific interests, education,
  teaching, students supervised, awards, books, collaborations, contact/address.
  Set type="string" for single-value fields (address, email, phone).
  Set type="list" for multi-value fields (publications, courses, projects, research fields, etc.).
  Set priority="high" for research/science-focused fields (publications, projects, research areas,
  students, grants). Set priority="normal" for everything else.
- Skip columns that are: URLs, timestamps, internal IDs, scraping metadata, or clearly irrelevant.
- Write description in the same language as the sample values (Vietnamese if samples are Vietnamese,
  English if English, etc.).
- Be specific: mention section headings, formatting patterns, or keywords that signal where this
  data appears in scraped text.
"""

    print("🔍 Detecting schema from CSV columns (one-time startup call)...")
    client = _make_client(_key_index)
    cfg = types.GenerateContentConfig(
        temperature=0.1,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=MODEL_LIST[_model_index],
                contents=detection_prompt,
                config=cfg,
            )
            raw = response.text.strip()
            raw = re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=re.MULTILINE).strip()
            schema = json.loads(raw)
            break
        except Exception as e:
            err = str(e)
            is_quota = "429" in err or "RESOURCE_EXHAUSTED" in err
            if is_quota and attempt < MAX_RETRIES - 1:
                print(f"  ⚠️  Quota on schema detection, waiting 30s...")
                time.sleep(30)
            elif attempt < MAX_RETRIES - 1:
                print(f"  ⚠️  Schema detection error (attempt {attempt+1}): {err[:100]}")
                time.sleep(5)
            else:
                raise RuntimeError(f"Schema detection failed after {MAX_RETRIES} attempts: {err}")

    # Apply detected schema
    IDENTITY_COL = schema.get("identity_col", "ho_ten")

    fields_data = schema.get("output_fields", [])
    # Only keep output fields that actually exist as columns in the CSV
    existing_cols = set(df.columns)
    fields_data = [f for f in fields_data if f["name"] in existing_cols]

    OUTPUT_FIELDS.clear()
    STRING_FIELDS.clear()

    desc_lines = []
    for fd in fields_data:
        name = fd["name"]
        OUTPUT_FIELDS.append(name)
        if fd.get("type") == "string":
            STRING_FIELDS.add(name)
        priority_tag = " [HIGH PRIORITY]" if fd.get("priority") == "high" else ""
        desc_lines.append(
            f"- {name} ({'string' if fd.get('type') == 'string' else 'list of strings'}){priority_tag}:\n"
            f"    {fd.get('description', 'Extract relevant information verbatim.')}"
        )

    FIELD_DESCRIPTIONS = "\n\n".join(desc_lines)

    print(f"✅ Schema detected:")
    print(f"   Identity column : {IDENTITY_COL}")
    print(f"   Source text col : {schema.get('source_text_col', 'None')}")
    print(f"   Output fields   : {OUTPUT_FIELDS}")
    high_prio = [f["name"] for f in fields_data if f.get("priority") == "high"]
    if high_prio:
        print(f"   High-priority   : {high_prio}")
    print()

    # Return source_text_col so main() can use it
    return schema.get("source_text_col")


# ── SYSTEM INSTRUCTION (built after schema detection) ─────────────────────────

def build_system_instruction() -> str:
    high_prio_fields = [f for f in OUTPUT_FIELDS if f not in STRING_FIELDS]
    return f"""You are an expert at extracting structured academic and professional information from researcher/faculty profile pages.
Task: COPY and LIST information verbatim — do NOT summarize, do NOT omit.

Each request will contain N profiles separated by "=== PROFILE_N ===".
Each profile has a label "identity=<name>" — this is the person to extract for.

Return EXACTLY one JSON array of N objects in order PROFILE_0, PROFILE_1, ...
Each object must have these fields:
{FIELD_DESCRIPTIONS}

- unpublished (boolean):
    true if the profile page has no real information — e.g. only "updating", empty,
    or only boilerplate/navigation menu with no actual profile data.
    false if the page has at least one real piece of information.

MANDATORY RULES:
1. ONLY extract information belonging to the person named "identity" in that profile.
   The page may show other people's names in navigation menus — IGNORE those.
2. COPY VERBATIM — no paraphrasing, no shortening, no replacing content with "...".
3. LIST EXHAUSTIVELY — 20 publications → 20 elements; 10 courses → 10 elements.
4. List-type fields must be JSON arrays of strings — each string is one complete item.
5. If information is not found → null. Do NOT invent data.
6. Do NOT add any text or markdown outside the JSON array.
7. Pay special attention to high-priority fields: {', '.join(high_prio_fields) if high_prio_fields else 'all fields'}.
   Search carefully for their section headings before concluding null."""


# ── BATCH PROMPT ──────────────────────────────────────────────────────────────

def build_batch_prompt(profiles: list[dict], source_col: str) -> str:
    """Build dynamic user content — system instruction is separate (cached)."""
    blocks = []
    for i, p in enumerate(profiles):
        blocks.append(f"=== PROFILE_{i} | identity={p['identity']} ===\n{p['text']}")

    profile_text = "\n".join(blocks)
    return (
        f"Below are {len(profiles)} profiles to extract:\n\n"
        f"{profile_text}\n\n"
        f"Return JSON array:"
    )


# ── API CALL WITH RETRY + KEY ROTATION ────────────────────────────────────────
NO_DATA_LABEL = "Thông tin không được công bố"

def call_batch(profiles: list[dict], source_col: str, system_instruction: str) -> list[dict]:
    global _key_index

    empty    = lambda: {f: None for f in OUTPUT_FIELDS}
    fallback = [empty() for _ in profiles]
    prompt   = build_batch_prompt(profiles, source_col)

    # Rebuild config with current system instruction (fields are now known)
    cfg = types.GenerateContentConfig(
        temperature=0.05,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        system_instruction=system_instruction,
    )

    attempt = 0
    keys_tried_this_round = 0

    while attempt < MAX_RETRIES:
        client = _make_client(_key_index)
        try:
            _current_model = MODEL_LIST[_model_index]
            response = client.models.generate_content(
                model=_current_model,
                contents=prompt,
                config=cfg,
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
                if item.get("unpublished") is True:
                    clean["thong_tin_khac"] = NO_DATA_LABEL if "thong_tin_khac" in OUTPUT_FIELDS else None
                    # Store NO_DATA marker in the last output field if thong_tin_khac absent
                    if "thong_tin_khac" not in OUTPUT_FIELDS and OUTPUT_FIELDS:
                        clean[OUTPUT_FIELDS[-1]] = NO_DATA_LABEL
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
            is_500   = "500" in err or "503" in err or "INTERNAL" in err or "UNAVAILABLE" in err

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
                    wait = 15 * (2 ** attempt)
                    print(f"    503 full model cycle (attempt {attempt+1}/{MAX_RETRIES}), waiting {wait}s...")
                    time.sleep(wait)
                    attempt += 1

            else:
                print(f"    ❌ Batch failed ({current_key_label()}): {err[:150]}")
                for r in fallback:
                    last_field = "thong_tin_khac" if "thong_tin_khac" in OUTPUT_FIELDS else OUTPUT_FIELDS[-1]
                    r[last_field] = f"ERROR: {err[:100]}"
                return fallback

    print(f"    ❌ Max retries reached ({MAX_RETRIES}). Skipping this batch.")
    for r in fallback:
        last_field = "thong_tin_khac" if "thong_tin_khac" in OUTPUT_FIELDS else OUTPUT_FIELDS[-1]
        r[last_field] = "ERROR: max retries exceeded"
    return fallback


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    raw_df = pd.read_csv(OUTPUT_CSV) if os.path.exists(OUTPUT_CSV) else pd.read_csv(INPUT_CSV)

    # Remove duplicate header rows
    dup_mask = raw_df.apply(lambda r: r.astype(str).eq(raw_df.columns).all(), axis=1)
    if dup_mask.any():
        print(f"🧹 Removed {dup_mask.sum()} duplicate header rows.")
    df = raw_df[~dup_mask].reset_index(drop=True)

    total = len(df)
    print(f"📂 Loaded {total} rows from {OUTPUT_CSV if os.path.exists(OUTPUT_CSV) else INPUT_CSV}")
    print(f"📋 Available columns: {list(df.columns)}")

    # ── One-time schema detection ──────────────────────────────────────────────
    source_col = detect_schema(df)
    # source_col is the raw text/HTML column name (e.g. "html_text"), or None

    has_source_text = (
        source_col is not None
        and source_col in df.columns
        and df[source_col].notna().any()
    )
    if has_source_text:
        print(f"🟢 Mode: EXTRACT from '{source_col}'")
    else:
        print(f"🔴 No source text column found — nothing to extract from. Exiting.")
        return

    # Build system instruction now that OUTPUT_FIELDS is populated
    system_instruction = build_system_instruction()

    # Initialize output columns if not present
    for f in OUTPUT_FIELDS:
        if f not in df.columns:
            df[f] = None

    # Determine the "no data" sentinel field (prefer thong_tin_khac, else last field)
    sentinel_field = "thong_tin_khac" if "thong_tin_khac" in OUTPUT_FIELDS else OUTPUT_FIELDS[-1]

    # Pre-mark rows with empty/boilerplate source text
    NO_DATA_PATTERNS = ["đang cập nhật", "updating", "coming soon", "to be updated"]

    def _is_no_data(text) -> bool:
        if pd.isna(text):
            return True
        s = str(text).strip()
        if not s:
            return True
        if len(s) < 100 and any(p in s.lower() for p in NO_DATA_PATTERNS):
            return True
        return False

    not_yet_marked = ~df[sentinel_field].astype(str).str.startswith(NO_DATA_LABEL, na=False)
    to_mark = df[source_col].apply(_is_no_data) & not_yet_marked
    if to_mark.any():
        print(f"ℹ️  Marked {to_mark.sum()} rows as '{NO_DATA_LABEL}' (empty/boilerplate source text).")
        df.loc[to_mark, sentinel_field] = NO_DATA_LABEL

    non_sentinel_fields = [f for f in OUTPUT_FIELDS if f != sentinel_field]
    has_any_data  = df[non_sentinel_fields].notna().any(axis=1)
    has_error     = df[sentinel_field].astype(str).str.startswith("ERROR", na=False)
    not_published = df[sentinel_field].astype(str).str.startswith(NO_DATA_LABEL, na=False)
    done_mask     = (has_any_data & ~has_error) | not_published
    todo = df.index[~done_mask].tolist()
    total_batches = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE

    if not_published.sum():
        print(f"ℹ️  Skipping {not_published.sum()} rows '{NO_DATA_LABEL}'.")

    print(f"📋 To process: {len(todo)} rows → {total_batches} batches "
          f"(batch_size={BATCH_SIZE})")
    print(f"⏱️  Estimated: ~{total_batches * (DELAY_BETWEEN_BATCHES + 5) // 60 + 1} min\n")

    start = datetime.now()

    for batch_num, chunk_start in enumerate(range(0, len(todo), BATCH_SIZE), 1):
        chunk_idx = todo[chunk_start: chunk_start + BATCH_SIZE]
        profiles = []
        for idx in chunk_idx:
            row = df.loc[idx]
            profiles.append({
                "identity": row.get(IDENTITY_COL, f"row_{idx}"),
                "text":     str(row.get(source_col, "") or ""),
                "idx":      idx,
            })

        names  = ", ".join(p["identity"] for p in profiles[:3])
        suffix = f"... (+{len(profiles)-3})" if len(profiles) > 3 else ""
        print(f"[Batch {batch_num}/{total_batches}] {current_key_label()} | {current_model_label()} | {names}{suffix}")

        results = call_batch(profiles, source_col, system_instruction)

        for profile, result in zip(profiles, results):
            for f, v in result.items():
                df.at[profile["idx"], f] = v

        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        print(f"  ✅ Saved checkpoint → {OUTPUT_CSV}")

        if batch_num < total_batches:
            time.sleep(DELAY_BETWEEN_BATCHES)

    elapsed = datetime.now() - start
    print(f"\n🎉 Done! Total time: {elapsed}")
    print(f"📄 Output file: {OUTPUT_CSV}\n")

    # Final statistics
    not_published   = df[sentinel_field].astype(str).str.startswith(NO_DATA_LABEL, na=False)
    has_error_final = df[sentinel_field].astype(str).str.startswith("ERROR", na=False)
    has_data_final  = df[non_sentinel_fields].notna().any(axis=1)
    error_count     = ((~has_data_final | has_error_final) & ~not_published).sum()
    nodata_count    = not_published.sum()

    if nodata_count:
        print(f"  ℹ️  {nodata_count} rows '{NO_DATA_LABEL}' (skipped).")
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