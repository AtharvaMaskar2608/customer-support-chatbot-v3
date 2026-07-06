import csv
import os
import time
from typing import List

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

INPUT_FILE = "./data/kb_faq_clean.csv"
OUTPUT_FILE = "./data/data_with_embeddings.csv"
MODEL = "text-embedding-3-large"
BATCH_SIZE = 100
MAX_RETRIES = 3


def generate_embeddings(chunks: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a batch of chunks.
    Retries on transient API failures with exponential backoff.
    """
    for attempt in range(MAX_RETRIES):
        try:
            response = openai_client.embeddings.create(
                model=MODEL,
                input=chunks,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = 2 ** attempt
            print(f"API error: {e}. Retrying in {wait}s...")
            time.sleep(wait)


def main() -> None:
    with open(INPUT_FILE, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No rows found in input file.")
        return

    # Skip rows with empty chunks — the API rejects empty strings
    valid_rows = [r for r in rows if r.get("chunk", "").strip()]
    skipped = len(rows) - len(valid_rows)
    if skipped:
        print(f"Skipping {skipped} row(s) with empty chunk.")

    for i in range(0, len(valid_rows), BATCH_SIZE):
        batch = valid_rows[i : i + BATCH_SIZE]
        embeddings = generate_embeddings([r["chunk"] for r in batch])

        for row, emb in zip(batch, embeddings):
            row["embedding"] = "[" + ",".join(map(str, emb)) + "]"

        print(f"Embedded {min(i + BATCH_SIZE, len(valid_rows))}/{len(valid_rows)}")

    fieldnames = list(valid_rows[0].keys())
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(valid_rows)

    print(f"Done. Wrote {len(valid_rows)} rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()