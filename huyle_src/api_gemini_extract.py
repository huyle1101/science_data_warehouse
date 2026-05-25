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
    wrapped = next_idx == 0 and len(API_KEY_LIST) > 1
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
    wrapped = next_idx == 0
    _model_index = next_idx
    return not wrapped


def current_model_label() -> str:
    return f"{MODEL_LIST[_model_index]} [{_model_index + 1}/{len(MODEL_LIST)}]"


# ==============================================================================
# CONFIG
# INPUT_CSV  : raw data, read when no prior output exists.
# OUTPUT_CSV : written after every batch. On re-runs the script reads this
#              instead of INPUT_CSV so it resumes from where it stopped.
# BATCH_SIZE : number of profiles per Gemini call. Reduce if html_text is large.
# ==============================================================================

INPUT_CSV  = r"f:/science_data_warehouse_repo/output/hust/scls/raw_data/scls.csv"
OUTPUT_CSV = r"f:/science_data_warehouse_repo/output/hust/scls/processed_data/scls_extracted.csv"

BATCH_SIZE               = 10
DELAY_BETWEEN_BATCHES    = 10   # seconds to wait between successful batch calls
ALL_KEYS_EXHAUSTED_WAIT  = 60   # seconds to wait when every key hits quota
MAX_RETRIES              = 4

# Column names for the two status flags.
# extract_status         : False until a row is fully extracted; True when done.
# thong_tin_khong_cong_bo: True when html_text has fewer than 10 words (no data).
#                          These rows are permanently skipped.
EXTRACT_STATUS_COL   = "extract_status"
NO_DATA_COL          = "thong_tin_khong_cong_bo"
HTML_TEXT_COL        = "html_text"
IDENTITY_COL_DEFAULT = "ho_ten"

# Populated once by detect_output_columns(). Never modified afterward.
OUTPUT_FIELDS      = []   # ordered list of column names to extract into
STRING_FIELDS      = set()# subset of OUTPUT_FIELDS that are plain strings
FIELD_DESCRIPTIONS = ""   # human-readable block injected into every prompt
IDENTITY_COL       = IDENTITY_COL_DEFAULT


# ==============================================================================
# SHARED GEMINI HELPER
# Used only for schema-detection calls (not batch extraction).
# Strips markdown code fences from the response before returning raw JSON text.
# Retries up to MAX_RETRIES times. Quota errors wait 30 s; other errors wait 5 s.
# ==============================================================================

def _gemini_call_with_retry(prompt: str, label: str) -> str:
    cfg = types.GenerateContentConfig(
        temperature=0.1,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    for attempt in range(MAX_RETRIES):
        try:
            client   = _make_client(_key_index)
            response = client.models.generate_content(
                model=MODEL_LIST[_model_index],
                contents=prompt,
                config=cfg,
            )
            raw = response.text.strip()
            return re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=re.MULTILINE).strip()
        except Exception as e:
            err      = str(e)
            is_quota = "429" in err or "RESOURCE_EXHAUSTED" in err
            if is_quota and attempt < MAX_RETRIES - 1:
                print(f"  Quota on {label}, waiting 30s...")
                time.sleep(30)
            elif attempt < MAX_RETRIES - 1:
                print(f"  {label} error (attempt {attempt + 1}): {err[:100]}")
                time.sleep(5)
            else:
                raise RuntimeError(f"{label} failed after {MAX_RETRIES} attempts: {err}")


# ==============================================================================
# SCHEMA DETECTION
# Called once at startup. Sends the html_text value from the row with the most
# words to Gemini and asks it to identify structured sections worth extracting.
# The result is used to create new columns (appended wherever pandas puts them)
# and to populate OUTPUT_FIELDS, STRING_FIELDS, FIELD_DESCRIPTIONS, IDENTITY_COL.
#
# Only creates a column if it does not already exist (safe for re-runs).
# Never touches any column that already existed in the CSV before html_text.
# ==============================================================================

def detect_output_columns(df: pd.DataFrame) -> None:
    global OUTPUT_FIELDS, STRING_FIELDS, FIELD_DESCRIPTIONS, IDENTITY_COL

    print("Step: Detecting output columns from the richest html_text row...")

    # Find the row with the most whitespace-separated words in html_text.
    # html_text values are already pre-stripped of garbage HTML tags.
    valid_mask  = df[HTML_TEXT_COL].notna() & (df[HTML_TEXT_COL].str.strip() != "")
    word_counts = df.loc[valid_mask, HTML_TEXT_COL].str.split().str.len()
    if word_counts.empty:
        raise RuntimeError("No non-empty html_text rows found. Cannot detect schema.")

    richest_idx  = word_counts.idxmax()
    richest_text = df.at[richest_idx, HTML_TEXT_COL]
    print(f"  Using row index {richest_idx} ({word_counts[richest_idx]} words) for schema discovery.")

    # Identify the identity column from existing columns (best-guess: first
    # column before html_text whose name looks like a person's name field).
    html_pos      = df.columns.get_loc(HTML_TEXT_COL)
    cols_before   = list(df.columns[:html_pos])
    identity_guess = IDENTITY_COL_DEFAULT
    for c in cols_before:
        if any(k in c.lower() for k in ("ten", "name", "ho", "full")):
            identity_guess = c
            break
    IDENTITY_COL = identity_guess
    print(f"  Identity column: {IDENTITY_COL}")

    schema_prompt = f"""You are an expert at analyzing researcher/faculty profile pages.
Below is a single profile page (already stripped of HTML tags).
Your task: identify every distinct structured section that contains factual information
about this person and that is worth extracting into its own column.

Strongly prefer sections about:
  - Scientific publications / research papers / journal articles / conference papers
  - Research projects / grants / funded studies
  - Research interests / directions / areas of expertise
  - PhD or master students supervised
  - Books / textbooks / monographs authored
  - Awards / honors related to research
  - Technology transfer / industry collaborations
  - Teaching courses / subjects taught
  - Contact details (email, phone, address, position, department)

Return ONLY a JSON array (no markdown, no explanation):
[
  {{
    "name": "<column_name in snake_case, Vietnamese style matching existing cols>",
    "type": "string" | "list",
    "description": "<2-3 sentence extraction instruction: what section heading to look for,
                    how to format each value, verbatim copy rule, example value>",
    "priority": "high" | "normal"
  }},
  ...
]

type="string"  for single-value fields (email, phone, position, department, address).
type="list"    for multi-value fields (publications, courses, projects, awards, etc.).
priority="high" for all research/science output fields.
priority="normal" for contact/admin fields.

Profile text:
{richest_text}"""

    raw    = _gemini_call_with_retry(schema_prompt, "schema detection")
    fields = json.loads(raw)

    if not isinstance(fields, list) or not fields:
        raise RuntimeError("Schema detection returned an empty or invalid field list.")

    print(f"  Discovered {len(fields)} output field(s):")

    existing_cols = set(df.columns)

    OUTPUT_FIELDS.clear()
    STRING_FIELDS.clear()
    desc_lines = []

    for fd in fields:
        name = fd["name"]
        OUTPUT_FIELDS.append(name)

        if fd.get("type") == "string":
            STRING_FIELDS.add(name)

        priority_tag = " [HIGH PRIORITY]" if fd.get("priority") == "high" else ""
        desc_lines.append(
            f"- {name} ({'string' if fd.get('type') == 'string' else 'list of strings'}){priority_tag}:\n"
            f"    {fd.get('description', 'Extract relevant information verbatim.')}"
        )

        type_label = "str " if fd.get("type") == "string" else "list"
        prio_star  = " (high priority)" if fd.get("priority") == "high" else ""
        new_label  = "" if name in existing_cols else " [new column]"
        print(f"    {type_label}  {name}{prio_star}{new_label}")

        # Only create the column if it does not already exist.
        # This preserves any data already written in a previous run.
        if name not in existing_cols:
            df[name] = None

    FIELD_DESCRIPTIONS = "\n\n".join(desc_lines)
    print("Step complete: output columns ready.")


# ==============================================================================
# SYSTEM INSTRUCTION
# Built once after detect_output_columns() has populated OUTPUT_FIELDS.
# Passed as a separate system instruction (not part of the user prompt) so it
# can be cached by the API across calls within the same session.
# ==============================================================================

def build_system_instruction() -> str:
    high_prio = [f for f in OUTPUT_FIELDS if f not in STRING_FIELDS]
    return f"""You are an expert at extracting structured academic and professional information
from researcher/faculty profile pages.
Task: COPY and LIST information verbatim. Do NOT summarize. Do NOT omit.

Each request contains N profiles separated by "=== PROFILE_N ===".
Each profile has a label "identity=<name>" identifying the person to extract for.

Return EXACTLY one JSON array of N objects in order PROFILE_0, PROFILE_1, ...
Each object must have these fields:
{FIELD_DESCRIPTIONS}

- thong_tin_khong_cong_bo (boolean):
    true  if the profile has no real information (empty, boilerplate, or navigation only).
    false if at least one real piece of information is present.

MANDATORY RULES:
1. Extract ONLY for the person named "identity" in that profile block.
   Navigation menus may show other names. Ignore those entirely.
2. COPY VERBATIM. No paraphrasing, no shortening, no replacing content with "...".
3. LIST EXHAUSTIVELY. 20 publications means 20 array elements. 10 courses means 10.
4. List-type fields must be JSON arrays of strings. Each string is one complete item.
5. If a section is not found, return null. Do NOT invent data.
6. Do NOT add any text or markdown outside the JSON array.
7. Pay special attention to high-priority fields: {', '.join(high_prio) if high_prio else 'all fields'}.
   Search carefully for their section headings before concluding null."""


# ==============================================================================
# BATCH PROMPT BUILDER
# Formats the user-side prompt. The system instruction is passed separately.
# Each profile block is delimited by "=== PROFILE_N ===" so the model can
# unambiguously associate its output object with the correct input profile.
# ==============================================================================

def build_batch_prompt(profiles: list[dict]) -> str:
    blocks = []
    for i, p in enumerate(profiles):
        blocks.append(f"=== PROFILE_{i} | identity={p['identity']} ===\n{p['text']}")
    return (
        f"Below are {len(profiles)} profiles to extract:\n\n"
        + "\n\n".join(blocks)
        + "\n\nReturn JSON array:"
    )


# ==============================================================================
# BATCH API CALL WITH RETRY AND ROTATION
# Handles all transient failures without losing work:
#
# Quota error (429) with multiple keys:
#   Rotate to the next key immediately and retry without incrementing attempt.
#   If all keys are exhausted in one round, wait ALL_KEYS_EXHAUSTED_WAIT seconds
#   then resume — this counts as one attempt.
#
# Quota error with a single key:
#   Exponential backoff (15s, 30s, 60s...) up to MAX_RETRIES.
#
# Server error (500/503):
#   Rotate to the next model. If all models are cycled, exponential backoff.
#
# Any other error:
#   Non-transient. Return the fallback immediately with a logged reason per row.
#   Do not retry. The extract_status stays False so the row is retried next run.
#
# Max retries exceeded:
#   Return fallback with reason. extract_status stays False.
# ==============================================================================

def call_batch(
    profiles: list[dict],
    system_instruction: str,
) -> list[dict]:
    global _key_index

    def empty_result():
        return {f: None for f in OUTPUT_FIELDS}

    fallback = [empty_result() for _ in profiles]
    prompt   = build_batch_prompt(profiles)

    cfg = types.GenerateContentConfig(
        temperature=0.05,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        system_instruction=system_instruction,
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

            # Extract the JSON array from the response. The model sometimes
            # wraps it in markdown fences or adds a preamble sentence.
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if not match:
                raise ValueError(f"No JSON array in response: {raw[:200]}")

            parsed = json.loads(match.group())
            if not isinstance(parsed, list) or len(parsed) != len(profiles):
                raise ValueError(
                    f"Expected {len(profiles)} objects, got {len(parsed)}"
                )

            results = []
            for item in parsed:
                result = empty_result()

                # thong_tin_khong_cong_bo flag from the model.
                # We store it in the result dict with a special key so the
                # caller can write it to the dedicated status column.
                if item.get("thong_tin_khong_cong_bo") is True:
                    result["_no_data"] = True
                    results.append(result)
                    continue

                for f in OUTPUT_FIELDS:
                    val = item.get(f)
                    if val is None:
                        result[f] = None
                    elif f in STRING_FIELDS:
                        result[f] = str(val).strip() if val else None
                    elif isinstance(val, list):
                        items = [str(v).strip() for v in val if v and str(v).strip()]
                        result[f] = json.dumps(items, ensure_ascii=False) if items else None
                    else:
                        # Model returned a scalar for a list field. Wrap it.
                        result[f] = json.dumps([str(val).strip()], ensure_ascii=False)

                results.append(result)

            # Successful call. Reset the per-round key counter.
            keys_tried_this_round = 0
            return results

        except Exception as e:
            err      = str(e)
            is_quota = "429" in err or "RESOURCE_EXHAUSTED" in err
            is_500   = any(x in err for x in ("500", "503", "INTERNAL", "UNAVAILABLE"))

            if is_quota and len(API_KEY_LIST) > 1:
                # Try the next key before counting this as an attempt.
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
                print(f"  Quota error (attempt {attempt + 1}/{MAX_RETRIES}), waiting {wait}s...")
                time.sleep(wait)
                attempt += 1

            elif is_500:
                # Server-side error. Rotate model before retrying.
                full_cycle = not _rotate_model()
                if full_cycle:
                    wait = 15 * (2 ** attempt)
                    print(
                        f"  Server error, all models tried "
                        f"(attempt {attempt + 1}/{MAX_RETRIES}), waiting {wait}s..."
                    )
                    time.sleep(wait)
                    attempt += 1
                else:
                    print(f"  Server error, rotating to model {current_model_label()}...")

            else:
                # Non-transient error. Log reason and return fallback immediately.
                reason = f"ERROR: {err[:150]}"
                print(f"  Batch failed ({current_key_label()}): {reason}")
                for r in fallback:
                    r["_failure_reason"] = reason
                return fallback

    # Exhausted all retry attempts.
    reason = "ERROR: max retries exceeded"
    print(f"  Max retries reached. Skipping batch.")
    for r in fallback:
        r["_failure_reason"] = reason
    return fallback


# ==============================================================================
# MAIN
# ==============================================================================

def main():

    # --------------------------------------------------------------------------
    # Step 1: Load CSV
    # Prefer OUTPUT_CSV if it exists (resuming an interrupted run).
    # Otherwise start fresh from INPUT_CSV.
    # --------------------------------------------------------------------------
    source_path = OUTPUT_CSV if os.path.exists(OUTPUT_CSV) else INPUT_CSV
    print(f"Step 1: Loading CSV from {source_path}...")
    raw_df = pd.read_csv(source_path, dtype=str)
    print(f"  Loaded {len(raw_df)} rows, {len(raw_df.columns)} columns.")

    # --------------------------------------------------------------------------
    # Step 2: Remove duplicate header rows and reset the index.
    # Duplicate header rows are rows where every cell equals the column name —
    # a common artifact when CSVs are concatenated naively.
    # All subsequent operations use only this cleaned df.
    # --------------------------------------------------------------------------
    print("Step 2: Removing duplicate header rows...")
    dup_mask = raw_df.apply(lambda r: r.astype(str).eq(raw_df.columns).all(), axis=1)
    if dup_mask.any():
        print(f"  Removed {dup_mask.sum()} duplicate header row(s).")
    df = raw_df[~dup_mask].reset_index(drop=True)
    total = len(df)
    print(f"  Clean dataframe: {total} rows.")

    if HTML_TEXT_COL not in df.columns:
        raise RuntimeError(f"Column '{HTML_TEXT_COL}' not found. Cannot proceed.")

    # --------------------------------------------------------------------------
    # Step 3: Create extract_status column if it does not exist.
    # If it already exists (resume run), existing True values are preserved.
    # --------------------------------------------------------------------------
    print("Step 3: Initialising extract_status column...")
    if EXTRACT_STATUS_COL not in df.columns:
        df[EXTRACT_STATUS_COL] = False
        print("  Created extract_status column (all False).")
    else:
        already_done = df[EXTRACT_STATUS_COL].astype(str).str.lower().eq("true").sum()
        print(f"  extract_status already exists. {already_done} rows already done.")

    # Normalise to actual booleans in case the column was loaded as strings.
    df[EXTRACT_STATUS_COL] = df[EXTRACT_STATUS_COL].astype(str).str.lower().eq("true")

    # --------------------------------------------------------------------------
    # Step 4: Create thong_tin_khong_cong_bo column if it does not exist.
    # A row is marked True when its html_text has fewer than 10 words.
    # Both thong_tin_khong_cong_bo and extract_status are set to True for
    # those rows so they are permanently skipped in the extraction phase.
    # html_text is assumed to be already stripped of garbage HTML tags.
    # --------------------------------------------------------------------------
    print("Step 4: Marking rows with insufficient html_text content...")
    if NO_DATA_COL not in df.columns:
        df[NO_DATA_COL] = False
        word_counts = df[HTML_TEXT_COL].fillna("").str.split().str.len()
        sparse_mask = word_counts < 10

        if sparse_mask.any():
            df.loc[sparse_mask, NO_DATA_COL]          = True
            df.loc[sparse_mask, EXTRACT_STATUS_COL]   = True
            print(
                f"  Marked {sparse_mask.sum()} row(s) as thong_tin_khong_cong_bo=True "
                f"(html_text < 10 words). They will be skipped."
            )
        else:
            print("  No sparse rows found. All rows have >= 10 words in html_text.")
    else:
        df[NO_DATA_COL] = df[NO_DATA_COL].astype(str).str.lower().eq("true")
        already_marked  = df[NO_DATA_COL].sum()
        print(f"  thong_tin_khong_cong_bo already exists. {already_marked} rows marked.")

    # --------------------------------------------------------------------------
    # Step 5 (implicit): Columns that existed before html_text are never written
    # to during extraction. detect_output_columns() only creates columns after
    # the existing ones. The batch write loop below checks OUTPUT_FIELDS, which
    # never includes pre-existing columns.
    # --------------------------------------------------------------------------

    # --------------------------------------------------------------------------
    # Step 6: Detect output columns from the richest html_text row.
    # Uses the row with the most words in html_text (sparse rows excluded).
    # Only creates new columns — existing ones are preserved as-is.
    # --------------------------------------------------------------------------
    print("Step 6: Running schema detection...")
    detect_output_columns(df)

    # --------------------------------------------------------------------------
    # Step 7: Build system instruction now that OUTPUT_FIELDS is populated.
    # --------------------------------------------------------------------------
    print("Step 7: Building system instruction...")
    system_instruction = build_system_instruction()
    print("  System instruction ready.")

    # Initialise any output columns that are newly discovered and not yet in df.
    for f in OUTPUT_FIELDS:
        if f not in df.columns:
            df[f] = None

    # --------------------------------------------------------------------------
    # Catch-up / resume logic:
    # A row needs processing if extract_status is False.
    # Rows with thong_tin_khong_cong_bo=True already have extract_status=True
    # (set in Step 4), so they are automatically excluded here.
    # On a fresh run, todo = all rows. On a resume run, todo = only unfinished rows.
    # --------------------------------------------------------------------------
    todo          = df.index[~df[EXTRACT_STATUS_COL]].tolist()
    total_batches = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE

    print(
        f"\nExtraction plan: {len(todo)} row(s) to process across {total_batches} batch(es) "
        f"(batch_size={BATCH_SIZE})."
    )
    print(f"Skipping {df[NO_DATA_COL].sum()} no-data row(s) and "
          f"{df[EXTRACT_STATUS_COL].sum() - df[NO_DATA_COL].sum()} already-done row(s).")
    print(f"Estimated time: ~{total_batches * (DELAY_BETWEEN_BATCHES + 5) // 60 + 1} minute(s).\n")

    if not todo:
        print("Nothing to extract. All rows are already done.")
    else:
        start = datetime.now()

        for batch_num, chunk_start in enumerate(range(0, len(todo), BATCH_SIZE), 1):
            chunk_idx = todo[chunk_start: chunk_start + BATCH_SIZE]

            # Build the profile list for this batch.
            profiles = []
            for idx in chunk_idx:
                row = df.loc[idx]
                profiles.append({
                    "identity": str(row.get(IDENTITY_COL, f"row_{idx}")),
                    "text":     str(row.get(HTML_TEXT_COL, "") or ""),
                    "idx":      idx,
                })

            names  = ", ".join(p["identity"] for p in profiles[:3])
            suffix = f"... (+{len(profiles) - 3})" if len(profiles) > 3 else ""
            print(
                f"Batch {batch_num}/{total_batches} | "
                f"{current_key_label()} | {current_model_label()} | "
                f"{names}{suffix}"
            )

            results = call_batch(profiles, system_instruction)

            # Write results back to df row by row.
            # extract_status is set to True immediately after each successful
            # write so that a crash mid-batch loses at most one row of work.
            for profile, result in zip(profiles, results):
                idx = profile["idx"]

                if "_failure_reason" in result:
                    # Non-transient failure. Log the reason in a dedicated column
                    # so the user can inspect why this row failed. extract_status
                    # stays False so the row is retried on the next run.
                    if "_failure_reason_col" not in df.columns:
                        df["_failure_reason"] = None
                    df.at[idx, "_failure_reason"] = result["_failure_reason"]
                    print(f"  Row {idx} failed: {result['_failure_reason'][:80]}")
                    continue

                if result.get("_no_data"):
                    # Model confirmed this row has no real data.
                    # Mark both status columns True so it is never processed again.
                    df.at[idx, NO_DATA_COL]        = True
                    df.at[idx, EXTRACT_STATUS_COL] = True
                    continue

                # Write each extracted field. Only OUTPUT_FIELDS are written —
                # no pre-existing column is ever touched.
                for f in OUTPUT_FIELDS:
                    if f in result:
                        df.at[idx, f] = result[f]

                # Step 8: Set extract_status=True immediately after writing,
                # before the checkpoint save. This guarantees that even if the
                # save is interrupted, the in-memory df reflects completion.
                df.at[idx, EXTRACT_STATUS_COL] = True

            # Save a checkpoint after every batch so progress is never lost.
            df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
            print(f"  Checkpoint saved to {OUTPUT_CSV}.")

            if batch_num < total_batches:
                time.sleep(DELAY_BETWEEN_BATCHES)

        elapsed = datetime.now() - start
        print(f"\nExtraction complete. Total time: {elapsed}.")

    # --------------------------------------------------------------------------
    # Step 9: Final summary
    # --------------------------------------------------------------------------
    print("\nStep 9: Final summary")

    no_data_count    = df[NO_DATA_COL].astype(bool).sum()
    not_done_count   = (~df[EXTRACT_STATUS_COL].astype(bool)).sum()
    done_count       = df[EXTRACT_STATUS_COL].astype(bool).sum() - no_data_count
    failure_col_present = "_failure_reason" in df.columns
    failure_count    = df["_failure_reason"].notna().sum() if failure_col_present else 0

    print(f"  Total rows             : {total}")
    print(f"  Successfully extracted : {done_count} ({done_count / total * 100:.1f}%)")
    print(f"  No data (skipped)      : {no_data_count} ({no_data_count / total * 100:.1f}%)")
    print(f"  Failed (extract=False) : {not_done_count} ({not_done_count / total * 100:.1f}%)")
    if failure_count:
        print(f"  Rows with logged error : {failure_count}")
        print("  Re-run this script to retry failed rows automatically.")

    print(f"\nOutput file: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()