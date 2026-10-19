"""Package extracted proxy text into compressed files that can be committed.

data/text/ (~150 MB for 50 firms) is gitignored. This writes one gzipped
JSON Lines file per sector to output/proxy_text/, one record per extracted
filing (selected or not, so alternatives such as AAPL's Dec-2017 proxy stay
available). Standard library only: read with
    pandas.read_json(path, lines=True)          # or gzip + json line by line
Each file must stay under the 50 MB limit, or the script fails, so the
caller can shard more finely (e.g. per firm) when scaling to 500 firms.

Usage: python part2_lived_values/src/package_text.py   (after download_proxies.py)
"""
from __future__ import annotations

import gzip
import io
import json
import sys

import pandas as pd

import config

OUT_DIR = config.OUTPUT_DIR / "proxy_text"
MAX_FILE_BYTES = 50 * 1024 * 1024

# Metadata carried with each text so the files stand alone.
FIELDS = ["ticker", "company_name", "sector", "cik", "filing_year", "panel_year", "accession", "form",
          "filing_date", "meeting_type", "selected", "prose_words", "table_words"]


def main() -> int:
    m = pd.read_csv(config.MANIFEST_OUT)
    m = m[m["text_path"].notna()]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.jsonl.gz"):
        old.unlink()  # sectors are rewritten in full; drop stale shards

    too_big = []
    for sector, grp in m.groupby("sector"):
        path = OUT_DIR / f"{sector.lower().replace(' ', '_')}.jsonl.gz"
        # mtime=0: byte-identical output for identical content, so git only
        # sees a change when the text actually changes.
        with gzip.GzipFile(path, "wb", compresslevel=9, mtime=0) as raw, \
                io.TextIOWrapper(raw, encoding="utf-8") as f:
            for r in grp.sort_values(["ticker", "filing_date"]).to_dict("records"):
                rec = {k: r[k] for k in FIELDS}
                rec["selected"] = bool(rec["selected"])
                rec["text"] = (config.REPO_DIR / r["text_path"]).read_text()
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        size = path.stat().st_size
        print(f"{path.name}: {len(grp)} filings, {size / 1e6:.1f} MB")
        if size > MAX_FILE_BYTES:
            too_big.append(path.name)

    if too_big:
        print(f"ERROR: over 50 MB, shard further: {too_big}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
