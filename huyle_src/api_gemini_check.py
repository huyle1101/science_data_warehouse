import os
import re
import time
import json
import sys
import pandas as pd
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()


# ==============================================================================
# API KEY ROTATION
# Up to 6 keys loaded from .env. Empty/missing keys are filtered out.
# _key_index tracks the currently active key. _rotate_key() advances it by one
# using modular arithmetic. Returns False when a full cycle completes (all keys
# have been tried), which triggers the all-keys-exhausted wait before retrying.
# ==============================================================================

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
    raise ValueError("No API keys found. Check your .env file.")

print(f"Found {len(API_KEY_LIST)} API key(s).")

_key_index = 0


def _make_client(key_idx: int) -> genai.Client:
    return genai.Client(api_key=API_KEY_LIST[key_idx])


def _rotate_key() -> bool:
    # Advance to the next key. Returns False if we wrapped back to index 0,
    # meaning all keys have been exhausted in this round.
    global _key_index
    next_idx = (_key_index + 1) % len(API_KEY_LIST)
    wrapped  = next_idx == 0 and len(API_KEY_LIST) > 1
    _key_index = next_idx
    return not wrapped


def current_key_label() -> str:
    return f"key[{_key_index + 1}/{len(API_KEY_LIST)}]"


# ==============================================================================
# MODEL ROTATION
# Up to 4 models loaded from .env. _model_index tracks the active model.
# _rotate_model() advances it. Returns False when all models have been tried
# in one round, which triggers an exponential backoff before the next retry.
# ==============================================================================

MODEL_LIST = [
    os.getenv("MODEL_01"),
    os.getenv("MODEL_02"),
    os.getenv("MODEL_03"),
    os.getenv("MODEL_04"),
]
MODEL_LIST = [m for m in MODEL_LIST if m]

if not MODEL_LIST:
    raise ValueError("No models found. Check your .env file.")

print(f"Model list ({len(MODEL_LIST)}): {MODEL_LIST}")

_model_index = 0


def _rotate_model() -> bool:
    # Advance to the next model. Returns False when a full cycle completes.
    global _model_index
    next_idx = (_model_index + 1) % len(MODEL_LIST)
    wrapped  = next_idx == 0
    _model_index = next_idx
    return not wrapped


def current_model_label() -> str:
    return f"{MODEL_LIST[_model_index]} [{_model_index + 1}/{len(MODEL_LIST)}]"


# ==============================================================================
# CONFIG
# EXTRACTED_CSV : input — the output of api_gemini_extract.py.
# CHECKED_CSV   : output — written after every row. On re-runs the script reads
#                 this instead so it resumes from where it stopped.
# BATCH_SIZE    : number of rows per Gemini call during re-extraction.
# ==============================================================================

EXTRACTED_CSV            = r"f:/science_data_warehouse_repo/output/hust/scls/processed_data/scls_extracted.csv"
CHECKED_CSV              = r"f:/science_data_warehouse_repo/output/hust/scls/processed_data/scls_checked.csv"

BATCH_SIZE               = 10
DELAY_BETWEEN_BATCHES    = 10
ALL_KEYS_EXHAUSTED_WAIT  = 60
MAX_RETRIES              = 4

# Column names — must match the extract script exactly.
EXTRACT_STATUS_COL = "extract_status"
NO_DATA_COL        = "thong_tin_khong_cong_bo"
HTML_TEXT_COL      = "html_text"
IS_CHECKED_COL     = "is_checked"
IDENTITY_COL       = "ho_ten"   # used only for logging; overridden below if detected


# ==============================================================================
# UTILITY: resolve which columns sit after html_text and are eligible to check.
# Columns before html_text are untouched (they pre-date extraction).
# The two status columns (extract_status, thong_tin_khong_cong_bo) are excluded
# even if they happen to appear after html_text in the column order.
# is_checked itself is excluded as well.
# ==============================================================================

COLS_TO_EXCLUDE_FROM_CHECK = {
    EXTRACT_STATUS_COL,
    NO_DATA_COL,
    IS_CHECKED_COL,
    "_failure_reason",
    "_check_failure_reason",
}


def get_extraction_columns(df: pd.DataFrame) -> list[str]:
    # Return the ordered list of columns that come strictly after html_text
    # and are not internal status columns.
    html_pos = df.columns.get_loc(HTML_TEXT_COL)
    return [
        c for c in df.columns[html_pos + 1:]
        if c not in COLS_TO_EXCLUDE_FROM_CHECK
    ]


# ==============================================================================
# VERBATIM CHECK PROMPT
# Sends one row's html_text and all its extracted column values to Gemini.
# Asks Gemini to return a per-field verdict: "ok" if every list item (or the
# string value) appears verbatim as a substring of html_text, or the correct
# verbatim extraction if something is wrong or missing.
#
# Using a per-field verdict in a single call gives both speed (one round-trip
# per row) and granularity (we know exactly which fields need correction).
# ==============================================================================

def build_check_prompt(
    identity: str,
    html_text: str,
    field_values: dict[str, str | None],
) -> str:
    field_lines = []
    for col, val in field_values.items():
        display = val if val is not None else "(null)"
        field_lines.append(f"  [{col}]: {display}")
    fields_block = "\n".join(field_lines)

    return f"""You are an expert data auditor for academic researcher profiles.

Profile identity: {identity}

Source text (html_text):
{html_text}

Extracted field values:
{fields_block}

Your task:
For each field listed above, verify that every item in the extracted value appears
VERBATIM as a substring of the source text. "Verbatim" means character-for-character
identical — no paraphrasing, no summarising, no shortening.

Rules:
- For list fields (JSON arrays): every element must appear verbatim in html_text.
- For string fields: the value must appear verbatim in html_text.
- If a field is null and the information genuinely does not exist in html_text, that is correct.
- If a field is null but the information IS present in html_text, extract it verbatim.
- If a field has a value that does NOT appear verbatim in html_text, replace it with the
  correct verbatim extraction from html_text.
- If a field is correct, return the exact same value unchanged.
- Never invent data. If something is not in html_text, return null.

Return ONLY a JSON object (no markdown, no explanation) with this structure:
{{
  "<field_name>": {{
    "verdict": "ok" | "corrected",
    "value": <corrected value, or the original value if ok, or null>
  }},
  ...
}}

One key per field. "verdict" is "ok" if the value was already correct, "corrected" if you changed it."""


# ==============================================================================
# SINGLE-ROW CHECK API CALL WITH RETRY AND ROTATION
# Handles transient failures identically to the extract script.
#
# Quota error (429) with multiple keys:
#   Rotate to the next key immediately. If all keys exhausted, wait then retry.
#
# Quota error with a single key:
#   Exponential backoff up to MAX_RETRIES.
#
# Server error (500/503):
#   Rotate to the next model. If all models exhausted, exponential backoff.
#
# Any other error:
#   Non-transient. Return None immediately with a logged reason.
#   is_checked stays False so the row is retried on the next run.
# ==============================================================================

def call_check(prompt: str, label: str) -> dict | None:
    cfg = types.GenerateContentConfig(
        temperature=0.05,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    attempt               = 0
    keys_tried_this_round = 0

    while attempt < MAX_RETRIES:
        client = _make_client(_key_index)
        try:
            response = client.models.generate_content(
                model=MODEL_LIST[_model_index],
                contents=prompt,
                config=cfg,
            )
            raw = response.text.strip()
            raw = re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=re.MULTILINE).strip()
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError(f"Expected a JSON object, got: {raw[:200]}")
            return parsed

        except Exception as e:
            err      = str(e)
            is_quota = "429" in err or "RESOURCE_EXHAUSTED" in err
            is_500   = any(x in err for x in ("500", "503", "INTERNAL", "UNAVAILABLE"))

            if is_quota and len(API_KEY_LIST) > 1:
                keys_tried_this_round += 1
                full_cycle = not _rotate_key()
                if full_cycle or keys_tried_this_round >= len(API_KEY_LIST):
                    print(
                        f"  All {len(API_KEY_LIST)} keys exhausted quota. "
                        f"Waiting {ALL_KEYS_EXHAUSTED_WAIT}s..."
                    )
                    time.sleep(ALL_KEYS_EXHAUSTED_WAIT)
                    keys_tried_this_round = 0
                    attempt += 1
                else:
                    print(f"  Quota on {current_key_label()}, rotating key...")

            elif is_quota and len(API_KEY_LIST) == 1:
                wait = 15 * (2 ** attempt)
                print(f"  Quota error ({label}, attempt {attempt + 1}/{MAX_RETRIES}), waiting {wait}s...")
                time.sleep(wait)
                attempt += 1

            elif is_500:
                full_cycle = not _rotate_model()
                if full_cycle:
                    wait = 15 * (2 ** attempt)
                    print(
                        f"  Server error, all models tried ({label}, "
                        f"attempt {attempt + 1}/{MAX_RETRIES}), waiting {wait}s..."
                    )
                    time.sleep(wait)
                    attempt += 1
                else:
                    print(f"  Server error, rotating to {current_model_label()}...")

            else:
                print(f"  Non-transient error on {label} ({current_key_label()}): {err[:150]}")
                return None

    print(f"  Max retries reached on {label}. Skipping row.")
    return None


# ==============================================================================
# MAIN
# ==============================================================================

def main():

    # --------------------------------------------------------------------------
    # Step 1: Load CSV
    # Prefer CHECKED_CSV if it exists (resuming an interrupted check run).
    # Otherwise start from EXTRACTED_CSV (the extract script's output).
    # Rows with thong_tin_khong_cong_bo=True are dropped immediately and never
    # touched again — they have no content to check.
    # --------------------------------------------------------------------------
    source_path = CHECKED_CSV if os.path.exists(CHECKED_CSV) else EXTRACTED_CSV
    print(f"Step 1: Loading CSV from {source_path}...")

    raw_df = pd.read_csv(source_path, dtype=str)
    print(f"  Loaded {len(raw_df)} total rows.")

    # Normalise boolean columns that were saved as strings.
    for bool_col in (EXTRACT_STATUS_COL, NO_DATA_COL):
        if bool_col in raw_df.columns:
            raw_df[bool_col] = raw_df[bool_col].astype(str).str.lower().eq("true")

    # Drop no-data rows. They are excluded permanently from the check.
    if NO_DATA_COL in raw_df.columns:
        no_data_count = raw_df[NO_DATA_COL].sum()
        df = raw_df[~raw_df[NO_DATA_COL]].reset_index(drop=True)
        print(f"  Skipped {no_data_count} row(s) with thong_tin_khong_cong_bo=True.")
    else:
        df = raw_df.reset_index(drop=True)
        print(f"  thong_tin_khong_cong_bo column not found. Processing all rows.")

    total = len(df)
    print(f"  Working set: {total} row(s).")

    if HTML_TEXT_COL not in df.columns:
        print(f"Column '{HTML_TEXT_COL}' not found. Cannot proceed.")
        sys.exit(1)

    # --------------------------------------------------------------------------
    # Step 2: Create is_checked column if it does not exist.
    # If it already exists (resume run), existing True values are preserved.
    # --------------------------------------------------------------------------
    print("Step 2: Initialising is_checked column...")
    if IS_CHECKED_COL not in df.columns:
        df[IS_CHECKED_COL] = False
        print("  Created is_checked column (all False).")
    else:
        df[IS_CHECKED_COL] = df[IS_CHECKED_COL].astype(str).str.lower().eq("true")
        already_checked = df[IS_CHECKED_COL].sum()
        print(f"  is_checked already exists. {already_checked} row(s) already checked.")

    # --------------------------------------------------------------------------
    # Step 3: Gate — terminate if any row still has extract_status=False.
    # This means the extract script did not finish. Running the check on
    # partially-extracted data would produce misleading results.
    # --------------------------------------------------------------------------
    print("Step 3: Verifying extract_status...")
    if EXTRACT_STATUS_COL not in df.columns:
        print("  extract_status column not found. Cannot verify extraction completeness.")
        sys.exit(1)

    df[EXTRACT_STATUS_COL] = df[EXTRACT_STATUS_COL].astype(str).str.lower().eq("true")
    incomplete = (~df[EXTRACT_STATUS_COL]).sum()

    if incomplete > 0:
        print(
            f"  TERMINATED: {incomplete} row(s) have extract_status=False. "
            f"Run api_gemini_extract.py first to complete extraction."
        )
        sys.exit(1)

    print("  All rows have extract_status=True. Proceeding.")

    # --------------------------------------------------------------------------
    # Resolve which columns sit after html_text and are eligible to check.
    # These are the columns created by the extract script.
    # --------------------------------------------------------------------------
    extraction_cols = get_extraction_columns(df)
    print(f"  Columns to check ({len(extraction_cols)}): {extraction_cols}")

    if not extraction_cols:
        print("  No extraction columns found after html_text. Nothing to check.")
        sys.exit(0)

    # Detect identity column for logging (first col before html_text with a name-like name).
    html_pos = df.columns.get_loc(HTML_TEXT_COL)
    global IDENTITY_COL
    for c in df.columns[:html_pos]:
        if any(k in c.lower() for k in ("ten", "name", "ho", "full")):
            IDENTITY_COL = c
            break
    print(f"  Identity column: {IDENTITY_COL}")

    # Ensure failure-reason column exists for logging check errors.
    if "_check_failure_reason" not in df.columns:
        df["_check_failure_reason"] = None

    # --------------------------------------------------------------------------
    # Catch-up / resume logic:
    # Only process rows where is_checked=False.
    # On a fresh run, todo = all rows. On a resume run, todo = only unchecked rows.
    # --------------------------------------------------------------------------
    todo = df.index[~df[IS_CHECKED_COL]].tolist()
    print(
        f"\nCheck plan: {len(todo)} row(s) to check, "
        f"{df[IS_CHECKED_COL].sum()} already done.\n"
    )

    if not todo:
        print("Nothing to check. All rows are already verified.")
    else:
        start          = datetime.now()
        reextracted    = 0    # rows where at least one field was corrected
        failed_rows    = 0    # rows where the API call failed entirely

        for row_num, idx in enumerate(todo, 1):
            row      = df.loc[idx]
            identity = str(row.get(IDENTITY_COL, f"row_{idx}"))
            html_text = str(row.get(HTML_TEXT_COL, "") or "")

            # Gather current extracted values for this row.
            field_values = {}
            for col in extraction_cols:
                val = row.get(col)
                field_values[col] = str(val) if pd.notna(val) and str(val).strip() else None

            print(
                f"Row {row_num}/{len(todo)} | "
                f"{current_key_label()} | {current_model_label()} | "
                f"{identity}"
            )

            # --------------------------------------------------------------------------
            # Step 4: Per-row check.
            # Send html_text and all extracted field values to Gemini in one call.
            # Gemini returns a per-field verdict: "ok" or "corrected" with the new value.
            # If a field is corrected, write the new value back to df immediately.
            # is_checked is set to True after a successful call (even if corrections
            # were made — the row has now been verified and corrected).
            # is_checked stays False if the API call itself fails, so the row
            # is retried on the next run.
            # --------------------------------------------------------------------------
            prompt  = build_check_prompt(identity, html_text, field_values)
            label   = f"row {idx} ({identity})"
            verdict = call_check(prompt, label)

            if verdict is None:
                # API call failed entirely. Log reason, leave is_checked=False.
                reason = "ERROR: API call failed after max retries"
                df.at[idx, "_check_failure_reason"] = reason
                failed_rows += 1
                print(f"  Failed to check row {idx}. Will retry on next run.")
            else:
                row_was_corrected = False
                for col, result in verdict.items():
                    if col not in extraction_cols:
                        # Ignore any field Gemini returned that we did not ask about.
                        continue

                    field_verdict = result.get("verdict", "ok")
                    new_value     = result.get("value")

                    if field_verdict == "corrected":
                        # Write the corrected verbatim value back.
                        # new_value may be a list (for list fields) or a string.
                        if isinstance(new_value, list):
                            items = [str(v).strip() for v in new_value if v and str(v).strip()]
                            df.at[idx, col] = json.dumps(items, ensure_ascii=False) if items else None
                        elif new_value is not None:
                            df.at[idx, col] = str(new_value).strip() or None
                        else:
                            df.at[idx, col] = None

                        row_was_corrected = True

                if row_was_corrected:
                    reextracted += 1
                    print(f"  Corrected {sum(1 for r in verdict.values() if r.get('verdict') == 'corrected')} field(s).")
                else:
                    print(f"  All fields verified correct.")

                # Mark as checked. This happens before the save so a crash
                # mid-save does not leave the row ambiguously half-written.
                df.at[idx, IS_CHECKED_COL] = True

            # Save a checkpoint after every row so no check work is lost.
            df.to_csv(CHECKED_CSV, index=False, encoding="utf-8-sig")

            # Delay only between rows to avoid hammering the API.
            if row_num < len(todo):
                time.sleep(1)

        elapsed = datetime.now() - start
        print(f"\nCheck complete. Total time: {elapsed}.")

    # --------------------------------------------------------------------------
    # Step 5: Final summary
    # --------------------------------------------------------------------------
    print("\nStep 5: Final summary")

    checked_count   = df[IS_CHECKED_COL].astype(bool).sum()
    unchecked_count = (~df[IS_CHECKED_COL].astype(bool)).sum()
    failure_count   = df["_check_failure_reason"].notna().sum() if "_check_failure_reason" in df.columns else 0

    # reextracted is only accurate for the current run. For a full-history count,
    # re-check would need a separate column. This is intentional: the user can
    # diff EXTRACTED_CSV and CHECKED_CSV to see all changes made.
    print(f"  Total rows processed   : {total}")
    print(f"  Verified correct       : {checked_count - (reextracted if 'reextracted' in dir() else 0)} ({(checked_count) / total * 100:.1f}% checked total)")
    print(f"  Re-extracted (this run): {reextracted if 'reextracted' in dir() else 'N/A (resume run)'}")
    print(f"  Failed (is_checked=False): {unchecked_count} ({unchecked_count / total * 100:.1f}%)")
    if failure_count:
        print(f"  Rows with logged error : {failure_count}")
        print("  Re-run this script to retry failed rows automatically.")

    print(f"\nOutput file: {CHECKED_CSV}")


if __name__ == "__main__":
    main()