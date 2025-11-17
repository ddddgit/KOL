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
python3 daren_yt.py --keywords-file keywords_kr.txt --min-subs 5000 --save-csv kr_3d_youtuber_111725.csv 

INS: 
example: 
python3 ins_apify.py --hashtags-file hashtagfile.txt   --results-per-tag 200  --output-posts ig_hash.csv --output-users ig_users.csv
