# project-webscraper

A lightweight Python toolkit to generate XML sitemaps by crawling a website, then monitor each page for content changes using SHA-256 hashing and SQLite storage.

Zero external dependencies for the monitor. Only `requests` and `beautifulsoup4` needed for the crawler.

---

## Project Structure

```
project-webscraper/
├── sitemap_generator.py   # crawls a site and produces sitemap.xml
├── monitor.py             # hashes pages and tracks changes in SQLite
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

Or manually:

```bash
pip install requests beautifulsoup4
```

---

## Usage

### 1. Generate sitemap + run monitor (combined)

```bash
python sitemap_generator.py https://example.com
```

This will:

1. Crawl `https://example.com` up to 500 pages (BFS, same domain only)
2. Save `sitemap.xml` in the current directory
3. Automatically run the monitor — hashing every page and storing results in `monitor.db`

Optional flags:

```bash
python sitemap_generator.py https://example.com --output my-sitemap.xml --max-pages 200
```

| Flag          | Default       | Description                      |
| ------------- | ------------- | -------------------------------- |
| `--output`    | `sitemap.xml` | Output path for the sitemap file |
| `--max-pages` | `500`         | Maximum number of pages to crawl |

---

### 2. Run monitor only (no re-crawl)

```bash
python monitor.py
```

Reads `sitemap.xml`, fetches each page, compares its hash against the stored value in `monitor.db`, and reports any changes. Use this for recurring checks without regenerating the sitemap.

Optional flags:

```bash
python monitor.py --sitemap my-sitemap.xml --db custom.db
```

| Flag        | Default       | Description                              |
| ----------- | ------------- | ---------------------------------------- |
| `--sitemap` | `sitemap.xml` | Path to the sitemap XML file             |
| `--db`      | `monitor.db`  | Path to the SQLite database              |
| `--report`  | —             | Print database contents without crawling |

---

### 3. View the database

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
SELECT * FROM changes;
.quit
```

**Using DB Browser for SQLite (free GUI):**

```bash
brew install --cask db-browser-for-sqlite
```

Open the app → File → Open Database → select `monitor.db` → Browse Data tab.

---

## How It Works

### sitemap_generator.py

- Starts a BFS crawl from the root URL using a `deque` queue
- Skips external links, asset files (`.png`, `.pdf`, `.js`, etc.), and non-200 responses
- Parses `<a href>` tags with BeautifulSoup to discover new links
- Outputs a valid `sitemap.xml` with `<loc>`, `<lastmod>`, `<changefreq>`, and `<priority>` for each page
- Calls `monitor.run()` automatically after saving the sitemap

### monitor.py

- Reads `<loc>` URLs from the sitemap
- Fetches each page and computes a SHA-256 hash of the raw HTTP response body
- On first run: inserts every URL as a new snapshot in the `pages` table
- On subsequent runs: compares the new hash against the stored one
  - **Unchanged** → updates `last_seen` and increments `check_count`
  - **Changed** → logs the old/new hash to the `changes` table and updates `pages`
  - **Error** → skips the URL with a warning

### Database schema

**`pages`** — one row per URL, always reflects the latest state:

| column        | description                                                   |
| ------------- | ------------------------------------------------------------- |
| `url`         | page URL (primary key)                                        |
| `hash`        | SHA-256 of the last fetched response body                     |
| `first_seen`  | UTC timestamp of first discovery                              |
| `last_seen`   | UTC timestamp of last successful check                        |
| `last_change` | UTC timestamp of last detected change (NULL if never changed) |
| `check_count` | total number of times this URL has been checked               |

**`changes`** — append-only log of every detected change:

| column        | description                |
| ------------- | -------------------------- |
| `id`          | auto-increment primary key |
| `url`         | the page that changed      |
| `old_hash`    | hash before the change     |
| `new_hash`    | hash after the change      |
| `detected_at` | UTC timestamp              |

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
