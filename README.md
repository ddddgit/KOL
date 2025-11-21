# 📺 KOL Finder 

This tool searches YouTube for channels related to one or more keywords, filters them by subscriber count and country, and extracts **each channel’s latest video date + views** — all while minimizing YouTube API quota usage.

✔ Multi-keyword search (from file)  
✔ Filter by subscriber count  
✔ Optional country filter (ISO format, e.g., `US`, `JP`)   
✔ CSV export  
✔ Limit number of processed channels  
✔ Hard-coded API key supported

YT:  
example:
default 50 video for each keywords
export API_KEY="xxx"
python3 tuberfinder.py --keywords-file keywords_kr.txt --min-subs 5000 --save-csv tuberslist.csv 

INS: 
example: 
export APIFY_TOKEN="xxx"
python3 ins_apify_bio.py --hashtags-file hashtagfile.txt   --results-per-tag 200  --output-posts ig_posts.csv --output-users ig_users.csv

INS_M
LOCAL ONLY

TT:
example:
python3 tt_apify.py --token apify_api_xxx --hashtags-file hashtags.txt --search-file keywords.txt  --results-per-page 20 --output-csv tiktok_search_AI.csv
