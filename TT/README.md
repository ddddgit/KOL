# TikTok Scraper via Apify (clockworks/tiktok-scraper)

Python CLI tool to run Apify's **`clockworks/tiktok-scraper`** actor and
**append results into a CSV**.

Supports:

✔ Load **hashtags from file**\
✔ Load **search queries from file**\
✔ Optional inline `--hashtags` and `--search-queries`\
✔ No defaults --- only scrape what you provide\
✔ Automatically append each run to the same CSV\
✔ No media downloads (metadata only)

------------------------------------------------------------------------

## **Features**

-   Uses the official Apify REST API\
-   Only scrapes hashtags and searches **you explicitly provide**\
-   Automatically detects dataset from the run\
-   Appends new records to CSV (never overwrites)\
-   Supports both **file-based** and **command-line** inputs\
-   Clean and simple to automate (cron, GitHub Actions, etc.)

------------------------------------------------------------------------

## **Installation**

### **1. Install Python dependencies**

``` bash
pip3 install requests
```

### **2. Download the script**

Save the file as:

    tiktok_apify.py

Or clone your repo.

------------------------------------------------------------------------

## **Usage**

### **Basic run**

``` bash
python3 tiktok_apify.py   --token apify_api_xxxxxxxxxxxxxxxxxx   --output-csv tiktok.csv   --hashtags 3dprinting   --search-queries AI
```

------------------------------------------------------------------------

## **Using Input Files**

### **1. Hashtags file**

    hashtags.txt

Example content:

    3dprinting
    3dmodel
    printer

Run:

``` bash
python3 tiktok_apify.py   --token apify_api_xxxxxxxxxxxxxxxxxx   --hashtags-file hashtags.txt   --output-csv results.csv
```

------------------------------------------------------------------------

### **2. Search query file**

    search.txt

Example content:

    AI
    robot arm
    3d printing house

Run:

``` bash
python3 tiktok_apify.py   --token apify_api_xxxxxxxxxxxxxxxxxx   --search-file search.txt   --output-csv results.csv
```

------------------------------------------------------------------------

### **3. BOTH hashtags + search queries**

``` bash
python3 tiktok_apify.py   --token apify_api_xxxxxxxxxxxxxxxxxx   --hashtags-file hashtags.txt   --search-file search.txt   --output-csv results.csv
```

------------------------------------------------------------------------

## **Appending CSV Automatically**

All runs append new rows to the same CSV:

-   First run → creates CSV + header\
-   Next runs → add new rows at the bottom\
-   No duplicates removed automatically (optional feature---can add)

------------------------------------------------------------------------

## **Arguments**

  -----------------------------------------------------------------------
  Argument                      Description
  ----------------------------- -----------------------------------------
  `--token`                     **Required.** Your Apify API token.

  `--output-csv`                **Required.** Output CSV file path.
                                Appends if exists.

  `--hashtags`                  Inline hashtags list.

  `--hashtags-file`             File with one hashtag per line.

  `--search-queries`            Inline search queries.

  `--search-file`               File with one search query per line.

  `--results-per-page`          Number of results per tag/search (default
                                20).

  `--proxy-country`             Apify proxy country. Default `"None"`.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## **Example Automation (cron)**

Run every hour:

    0 * * * * python3 /path/tiktok_apify.py --token apify_api_xx --hashtags-file hashtags.txt --output-csv hourly.csv

------------------------------------------------------------------------

## **Script Behavior**

-   Only adds `hashtags` if provided\
-   Only adds `searchQueries` if provided\
-   If neither provided → actor runs with empty search\
-   Scraper **never downloads videos** (meta info only)

------------------------------------------------------------------------

## **License**

MIT License --- free to use, modify, and integrate.

