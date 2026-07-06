import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

INPUT_FILE = "./data/data_with_embeddings.csv"
TABLE = "qa_chunks"
COLUMNS = [
    "topic",
    "section",
    "question",
    "answer",
    "answer_source",
    "tat",
    "source_sheet",
    "source_row",
    "chunk",
    "embedding",
]

DATABASE_URL = os.getenv("DATABASE_URL")
# e.g. DATABASE_URL=postgresql://user:password@localhost:5432/yourdb


def main() -> None:
    copy_sql = (
        f"COPY {TABLE} ({', '.join(COLUMNS)}) "
        "FROM STDIN WITH (FORMAT csv, HEADER true)"
    )

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                with open(INPUT_FILE, newline="", encoding="utf-8") as f:
                    cur.copy_expert(copy_sql, f)
                cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
                count = cur.fetchone()[0]
        print(f"Done. Table {TABLE} now has {count} rows.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()