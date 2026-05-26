# project-webscraper

A lightweight Python toolkit to generate XML sitemaps by crawling a website, then monitor each page for content changes using SHA-256 hashing and SQLite storage. Includes tools to detect dynamic content, fetch HTML snapshots of changed pages, and visualize the site structure as a tree.

Zero external dependencies for the monitor. Only `requests` and `beautifulsoup4` needed for the crawler.

---

## Project Structure

```
project-webscraper/
├── sitemap_generator.py   # crawls a site and produces sitemap.xml (with parent tracking)
├── sitemap_parser.py      # prints sitemap as a BFS tree using parent-child relationships
├── monitor.py             # hashes pages and tracks changes in SQLite
├── fetch_changes.py       # downloads HTML snapshots of changed pages into the DB
├── detec_dynamic.py       # fetches a URL multiple times to identify dynamic content
├── requirements.txt       # pip dependencies
├── .gitignore
└── README.md
```

---

## Requirements

- Python 3.9+
- `requests`
- `beautifulsoup4`

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Usage

### 1. Generate sitemap + run monitor (combined)

```bash
python sitemap_generator.py https://example.com
```

This will:

1. Crawl `https://example.com` up to 1500 pages (concurrent BFS, same domain + subdomains)
2. Save `sitemap.xml` in the current directory (includes parent-child relationships)
3. Automatically run the monitor — hashing every page and storing results in `monitor.db`
4. If any changes are detected, automatically fetch and store HTML snapshots via `fetch_changes.py`

Optional flags:

```bash
python sitemap_generator.py https://example.com --output my-sitemap.xml --max-pages 200 --workers 10 --delay 0.5
```

| Flag          | Default       | Description                                         |
| ------------- | ------------- | --------------------------------------------------- |
| `--output`    | `sitemap.xml` | Output path for the sitemap file                    |
| `--max-pages` | `1500`        | Maximum number of pages to crawl                    |
| `--workers`   | `10`          | Concurrent workers per BFS level                    |
| `--delay`     | `0.5`         | Minimum seconds between requests to the same domain |

---

### 2. Run monitor only (no re-crawl)

```bash
python monitor.py
```

Reads `sitemap.xml`, fetches each page, compares its hash against the stored value in `monitor.db`, and reports any changes. If changes are found, automatically calls `fetch_changes.py` to snapshot the updated HTML. Use this for recurring checks without regenerating the sitemap.

Optional flags:

```bash
python monitor.py --sitemap my-sitemap.xml --db custom.db --workers 20
```

| Flag        | Default       | Description                              |
| ----------- | ------------- | ---------------------------------------- |
| `--sitemap` | `sitemap.xml` | Path to the sitemap XML file             |
| `--db`      | `monitor.db`  | Path to the SQLite database              |
| `--workers` | `20`          | Number of concurrent hashing threads     |
| `--report`  | —             | Print database contents without crawling |

---

### 3. View sitemap as a BFS tree

Prints pages in the order they were discovered during crawling, showing which links were found on which page:

```bash
python sitemap_parser.py
```

Optional flags:

```bash
python sitemap_parser.py --sitemap my-sitemap.xml
```

Example output:

```
🌐 BFS Site Tree — 12 pages

└── https://example.com  (3 links)
    ├── https://example.com/about
    ├── https://example.com/blog  (2 links)
    │   ├── https://example.com/blog/post-1
    │   └── https://example.com/blog/post-2
    └── https://sub.example.com  (1 links)
        └── https://sub.example.com/page1
```

> **Note:** The sitemap must be generated with the current `sitemap_generator.py`, as the tree view requires the `<parent>` tag.

---

### 4. Fetch HTML snapshots of changed pages

After a monitor run detects changes, `fetch_changes.py` is called automatically. You can also run it manually to (re-)fetch HTML for the most recent batch of changes:

```bash
python fetch_changes.py
```

This adds an `html` column to the `changes` table (if not already present) and saves the current HTML of each changed URL from the latest monitor run.

Optional flags:

```bash
python fetch_changes.py --db custom.db
```

| Flag   | Default      | Description                 |
| ------ | ------------ | --------------------------- |
| `--db` | `monitor.db` | Path to the SQLite database |

---

### 5. Detect dynamic content on a page

If the monitor flags a page as changed on every run, it may contain dynamic content (live counters, timestamps, CSRF tokens). Use this tool to identify what's changing:

```bash
python detec_dynamic.py "https://example.com/page"
```

Fetches the URL multiple times, compares the parsed text between requests, and reports which HTML tags differ. Helps you decide whether to add custom stripping rules in `monitor.py`.

Optional flags:

```bash
python detec_dynamic.py "https://example.com/page" --runs 3
```

| Flag     | Default | Description                       |
| -------- | ------- | --------------------------------- |
| `--runs` | `2`     | Number of times to fetch the page |

---

### 6. View the database

**In the terminal:**

```bash
python monitor.py --report
```

**Using SQLite CLI (built into macOS):**

```bash
sqlite3 monitor.db
.headers on
.mode column
SELECT url, last_seen, check_count FROM pages;
SELECT url, detected_at, old_hash, new_hash FROM changes;
.quit
```

**Using DB Browser for SQLite (free GUI):**

```bash
brew install --cask db-browser-for-sqlite
```

Open the app → File → Open Database → select `monitor.db` → Browse Data tab.

**Using VS Code:**

Install the **SQLite Viewer** extension (`qwtel.sqlite-viewer`) — click any `.db` file in the explorer to open a table browser directly inside VS Code.

---

### 7. Reset the database

To clear all stored hashes and change history:

```bash
rm monitor.db
```

The next monitor run will recreate it and treat every URL as a fresh first-time snapshot.

---

### 8. Test a URL manually

Check the HTTP response headers:

```bash
curl -I "https://example.com"
```

Extract all links from a page (same as what the crawler does):

```bash
curl -s "https://example.com" | grep -o 'href="[^"]*"'
```

---

## How It Works

### sitemap_generator.py

- Starts a concurrent BFS crawl from the root URL, processing each level with a `ThreadPoolExecutor`
- Per-domain rate limiting (configurable delay) prevents overwhelming any single server
- Follows subdomains of the base domain (e.g. `blog.example.com` when crawling `example.com`)
- Skips external links, asset files (`.png`, `.pdf`, `.js`, etc.), and non-200 responses
- Parses `<a href>` tags with BeautifulSoup to discover new links
- Includes whitelisted document types (`.pdf`, `.pptx`, `.xlsx`, etc.) using HEAD requests to avoid downloading full files
- Outputs a valid `sitemap.xml` with `<loc>`, `<lastmod>`, `<changefreq>`, `<priority>`, and `<parent>` for each page
- Automatically calls `monitor.run()` after saving the sitemap

### sitemap_parser.py

- Reads `<loc>` and `<parent>` tags from `sitemap.xml`
- Reconstructs the parent-child relationship map from the crawl
- Prints the site as an iterative BFS tree (no recursion, handles deep trees without hitting Python's recursion limit)
- Detects and flags cyclic references
- Annotates nodes with the number of outgoing links found

### monitor.py

- Reads `<loc>` URLs from the sitemap
- Fetches each page concurrently (configurable thread count) and computes a SHA-256 hash of the **parsed text content** (scripts, styles, and known dynamic elements stripped) to avoid false positives from CSRF tokens, timestamps, and visitor counters
- Document URLs (`.pdf`, `.pptx`) are fingerprinted via HEAD request headers instead of downloading
- On first run: inserts every URL as a new snapshot in the `pages` table
- On subsequent runs: compares the new hash against the stored one
  - **Unchanged** → updates `last_seen` and increments `check_count`
  - **Changed** → logs the old/new hash to the `changes` table, updates `pages`, then triggers `fetch_changes.py`
  - **Error** → skips the URL with a warning

### fetch_changes.py

- Adds an `html` column to the `changes` table if it doesn't exist
- Looks up the most recent `detected_at` timestamp in the `changes` table
- Fetches and stores the raw HTML for each changed URL from that run (skips URLs already fetched)
- Per-domain rate limiting (1 second between requests to the same host)

### detec_dynamic.py

- Fetches the target URL a configurable number of times with a 1-second delay between requests
- Strips scripts and styles the same way `monitor.py` does
- Compares full-text SHA-256 hashes across runs to confirm whether the page is dynamic
- Diffs individual tag texts between the first two fetches to identify which elements change
- Highlights likely timestamps, counters, and short numeric tokens

### Database schema

**`pages`** — one row per URL, always reflects the latest state:

| column        | description                                                   |
| ------------- | ------------------------------------------------------------- |
| `url`         | page URL (primary key)                                        |
| `hash`        | SHA-256 of the last fetched parsed text content               |
| `first_seen`  | UTC timestamp of first discovery                              |
| `last_seen`   | UTC timestamp of last successful check                        |
| `last_change` | UTC timestamp of last detected change (NULL if never changed) |
| `check_count` | total number of times this URL has been checked               |

**`changes`** — append-only log of every detected change:

| column        | description                            |
| ------------- | -------------------------------------- |
| `id`          | auto-increment primary key             |
| `url`         | the page that changed                  |
| `old_hash`    | hash before the change                 |
| `new_hash`    | hash after the change                  |
| `detected_at` | UTC timestamp                          |
| `html`        | raw HTML snapshot fetched after change |

---

## Automate with Cron

Run the monitor daily at 8am and log output:

```bash
0 8 * * * /usr/bin/python3 /path/to/monitor.py >> /var/log/monitor.log 2>&1
```

---

## .gitignore

```
monitor.db
sitemap.xml
__pycache__/
*.pyc
.venv/
```

---

## License

MIT
