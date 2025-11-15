
# 📺 YouTube Channel Finder (Low-Quota Version)

This tool searches YouTube for channels related to one or more keywords, filters them by subscriber count and country, and extracts **each channel’s latest video date + views** — all while minimizing YouTube API quota usage.

✔ Multi-keyword search (from file)  
✔ Filter by subscriber count  
✔ Optional country filter (ISO format, e.g., `US`, `JP`)  
✔ Low-quota design (uses `activities.list`, avoids expensive `search.list`)  
✔ CSV export  
✔ Limit number of processed channels  
✔ Hard-coded API key supported

---

## ✨ Features

| Feature | Description |
|--------|-------------|
| Keyword search | Pulls channel IDs from videos & channels matching your keywords |
| Low quota design | No per-channel high-cost `search.list` queries |
| Filters | Subscriber minimum & optional country code |
| Latest video extraction | Gets channel’s latest upload (date + views) |
| CSV export | Easy sorting & analysis |
| Max channels | Limit channels processed to avoid quota drain |
| Hard-coded API key | No CLI arg needed |

---

## 📦 Requirements

- Python 3.8+  
- YouTube Data API v3 key  
- Install dependencies:

```bash
pip install google-api-python-client
```

---

## 📂 Project Structure

```
project/
│
├── find_3d_channels.py     # Main script
├── keywords.txt            # List of keywords (one per line)
└── README.md               # This file
```

---

# 📝 keywords.txt Example

```
3D Modeling
3D Printing
Blender
CAD Design
ZBrush Tutorial
```

---

# 🚀 Usage

## Basic command

```bash
python find_3d_channels.py \
  --keywords-file keywords.txt \
  --min-subs 2000
```

---

## Add country filter

```bash
python find_3d_channels.py \
  --keywords-file keywords.txt \
  --min-subs 2000 \
  --country US
```

---

## Save results to CSV

```bash
python find_3d_channels.py \
  --keywords-file keywords.txt \
  --min-subs 2000 \
  --save-csv result.csv
```

---

## Limit number of channels processed (quota safe)

```bash
python find_3d_channels.py \
  --keywords-file keywords.txt \
  --min-subs 2000 \
  --max-channels 20
```

---

## Full example command

```bash
python find_3d_channels.py \
  --keywords-file keywords.txt \
  --min-subs 1000 \
  --country JP \
  --max-channels 30 \
  --save-csv japanese_3d_channels.csv
```

---

# 🔧 API Key Setup

Open `find_3d_channels.py`, find:

```python
API_KEY = "PUT_YOUR_API_KEY_HERE"
```

Replace with your API key.

---

# 📊 Quota Usage (Low-Quota Mode)

### API Cost Reference  
| Method | Cost | Used for |
|--------|------|----------|
| `search.list` | **100 units** | keyword discovery |
| `channels.list` | 1 unit | channel details |
| `activities.list` | **1 unit** | fetch latest uploaded video ID |
| `videos.list` | 1 unit | fetch video views + date |

### Typical quota usage for **1 keyword**

- `search.list`: 100–200 units  
- `channels.list`: ~1  
- `activities.list`: 20–50  
- `videos.list`: ~1  

**Total ≈ 120–250 units**  

---

# 📈 Output Example

### Console

```
BlenderXYZ | Subs: 58200 | Last Video: 2024-01-05, 12000 views | Country: US | https://www.youtube.com/channel/XXXX
```

### CSV

```
channel_name,subscribers,last_video_date,last_video_views,country,url,channel_id
BlenderXYZ,58200,2024-01-05,12000,US,https://www.youtube.com/channel/XXXX,XXXX
```

---

# 🛡️ Tips to Avoid Quota Spikes

- Keep `keywords.txt` small  
- Use `--max-channels`  
- Run only a few times per day  
- Monitor **YouTube API → Quotas → Method Usage**

---

# 🤝 Contributing

PRs welcome!

---

# 📄 License

MIT License.
