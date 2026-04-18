"""
室戸沖 出船判断システム v3 — 予報データ取得スクリプト
GitHub Actions から実行され、forecast_data.json を生成します。

変更履歴:
  - wave_direction（波向き）追加
  - wind_wave_height（風波）追加
"""
import urllib.request
import json
from datetime import datetime, timezone

LAT, LON, DAYS = 33.2, 134.2, 5
TARGET_HOURS = [0, 6, 12, 18]


def fetch_json(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "muroto-forecast/1.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


print("Marine API 取得中...")
marine = fetch_json(
    "https://marine-api.open-meteo.com/v1/marine"
    f"?latitude={LAT}&longitude={LON}"
    "&hourly=wave_height,wave_direction,wind_wave_height"
    f"&timezone=Asia/Tokyo&forecast_days={DAYS}"
)

print("Weather API 取得中...")
weather = fetch_json(
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={LAT}&longitude={LON}"
    "&hourly=wind_speed_10m,wind_direction_10m,precipitation"
    f"&wind_speed_unit=ms&timezone=Asia/Tokyo&forecast_days={DAYS}"
)

m_times     = marine["hourly"]["time"]
m_wave      = marine["hourly"]["wave_height"]
m_wavedir   = marine["hourly"]["wave_direction"]
m_windwave  = marine["hourly"].get("wind_wave_height")  # 風波（なければ None）
w_wind      = weather["hourly"]["wind_speed_10m"]
w_dir       = weather["hourly"]["wind_direction_10m"]
w_rain      = weather["hourly"]["precipitation"]
wmap        = {t: i for i, t in enumerate(weather["hourly"]["time"])}

rows = []
for i, t in enumerate(m_times):
    if int(t[11:13]) not in TARGET_HOURS:
        continue
    wi = wmap.get(t)
    if wi is None:
        continue
    wave = m_wave[i]
    wind = w_wind[wi]
    if wave is None or wind is None:
        continue

    waveDir  = m_wavedir[i]
    windWave = m_windwave[i] if m_windwave else None
    rows.append({
        "t":        t,
        "wave":     round(float(wave), 2),
        "wind":     round(float(wind), 1),
        "dir":      int(w_dir[wi] or 0),
        "waveDir":  int(waveDir)   if waveDir  is not None else None,
        "windWave": round(float(windWave), 2) if windWave is not None else None,
        "rain":     round(float(w_rain[wi] or 0), 1),
    })

output = {
    "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "rows": rows,
}

with open("data/forecast_data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False)

print(f"✓ {len(rows)} 件保存完了 → data/forecast_data.json")
