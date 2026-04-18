// scripts/update-conditions.js
// Open-Meteo APIから差分データを取得して fishing_condition_db.csv に追記する
// GitHub Actions（Node 20）で毎週自動実行

const fs   = require('fs');
const path = require('path');

const CSV_FILE  = path.join(__dirname, '..', 'data', 'fishing_condition_db.csv');
const JSON_FILE = path.join(__dirname, '..', 'data', 'fishing_condition_db.json');

const API_DELAY          = 1200;   // リクエスト間隔(ms)
const TARGET_HOURS       = [6, 7, 8]; // JST 6:00〜8:00 を集計対象
const DEFAULT_START_DATE = '2022-01-01';
const CHUNK_DAYS         = 180;    // 1リクエストの最大日数
const MAX_RETRIES        = 5;      // 429エラー時の最大リトライ回数

const STATIONS = [
  { name: '室戸',   lat: 33.29, lng: 134.18, pref: '高知県' },
  { name: '高知',   lat: 33.56, lng: 133.54, pref: '高知県' },
  { name: '足摺',   lat: 32.72, lng: 132.72, pref: '高知県' },
  { name: '宇和島', lat: 33.22, lng: 132.56, pref: '愛媛県' },
  { name: '松山',   lat: 33.84, lng: 132.77, pref: '愛媛県' },
  { name: '来島',   lat: 34.12, lng: 132.99, pref: '愛媛県' },
  { name: '高松',   lat: 34.35, lng: 134.05, pref: '香川県' },
  { name: '阿南',   lat: 33.92, lng: 134.66, pref: '徳島県' }
];

// ─── 日付ヘルパー ───────────────────────────────────────────────
function localDateStr(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}
function today()              { return localDateStr(new Date()); }
function addDays(dateStr, n)  {
  const d = new Date(dateStr + 'T12:00:00');
  d.setDate(d.getDate() + n);
  return localDateStr(d);
}

// ─── チャンク分割 ────────────────────────────────────────────────
function chunkDateRange(fromDate, toDate, chunkSize) {
  const chunks = [];
  let cur = fromDate;
  while (cur <= toDate) {
    const end = addDays(cur, chunkSize - 1);
    const actualEnd = end > toDate ? toDate : end;
    chunks.push({ from: cur, to: actualEnd });
    cur = addDays(actualEnd, 1);
  }
  return chunks;
}

// ─── API URL ─────────────────────────────────────────────────────
// ※ Open-Meteo archive-api は 5日前までの過去データが揃う
//    forecast-api は当日前後のみ返すため、両者を混在する範囲で一本化すると
//    片方のデータが欠落する（2025-12-11〜2026-04-16 のような長期欠損原因）。
//    必ず境界で分割して個別に呼ぶこと。
function weatherArchiveUrl(lat, lng, fromDate, toDate) {
  return `https://archive-api.open-meteo.com/v1/archive?latitude=${lat}&longitude=${lng}`
    + `&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,precipitation,weather_code`
    + `&timezone=Asia%2FTokyo&start_date=${fromDate}&end_date=${toDate}`;
}
function weatherForecastUrl(lat, lng, fromDate, toDate) {
  return `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lng}`
    + `&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,precipitation,weather_code`
    + `&timezone=Asia%2FTokyo&start_date=${fromDate}&end_date=${toDate}&past_days=0`;
}
function marineApiUrl(lat, lng, fromDate, toDate, params) {
  return `https://marine-api.open-meteo.com/v1/marine?latitude=${lat}&longitude=${lng}`
    + `&${params}&timezone=Asia%2FTokyo&start_date=${fromDate}&end_date=${toDate}`;
}

// ─── fetchWithRetry（429対応・指数バックオフ） ───────────────────
async function fetchWithRetry(url, retries = MAX_RETRIES) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url);
      if (res.ok) return res;
      if (res.status === 429) {
        const retryAfter = parseInt(res.headers.get('Retry-After')) || 60;
        const waitSec = Math.min(retryAfter * Math.pow(2, attempt), 300);
        console.log(`  ⚠ API制限(429) — ${waitSec}秒待機後リトライ (${attempt+1}/${retries})`);
        await new Promise(r => setTimeout(r, waitSec * 1000));
        continue;
      }
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    } catch (e) {
      if (attempt === retries) throw e;
      console.log(`  ⚠ ネットワークエラー — リトライ (${attempt+1}/${retries}): ${e.message}`);
      await new Promise(r => setTimeout(r, 3000 * (attempt + 1)));
    }
  }
  throw new Error(`リトライ失敗 (${retries}回超)`);
}

// ─── 時間帯集計ヘルパー ──────────────────────────────────────────
function groupHourlyByDate(timeArr, dataKeys, dataArrays) {
  const byDate = {};
  for (let i = 0; i < timeArr.length; i++) {
    const t       = timeArr[i];
    const dateStr = t.substring(0, 10);
    const hour    = parseInt(t.substring(11, 13));
    if (!TARGET_HOURS.includes(hour)) continue;
    if (!byDate[dateStr]) byDate[dateStr] = [];
    const entry = { hour };
    for (const key of dataKeys) entry[key] = dataArrays[key][i];
    byDate[dateStr].push(entry);
  }
  return byDate;
}
function avg(arr)    { return arr.length ? Math.round(arr.reduce((a,b)=>a+b,0)/arr.length*10)/10 : null; }
function maxVal(arr) { return arr.length ? Math.round(Math.max(...arr)*10)/10 : null; }
function minVal(arr) { return arr.length ? Math.round(Math.min(...arr)*10)/10 : null; }
function sumVal(arr) { return arr.length ? Math.round(arr.reduce((a,b)=>a+b,0)*10)/10 : null; }

// ─── 天気コード → テキスト ────────────────────────────────────────
function weatherDesc(code) {
  const map = {
    0:'快晴', 1:'晴れ', 2:'一部曇り', 3:'曇り', 45:'霧', 48:'着氷霧',
    51:'弱い霧雨', 53:'霧雨', 55:'強い霧雨', 56:'着氷霧雨(弱)', 57:'着氷霧雨(強)',
    61:'弱い雨', 63:'雨', 65:'強い雨', 66:'着氷雨(弱)', 67:'着氷雨(強)',
    71:'弱い雪', 73:'雪', 75:'強い雪', 77:'霧雪',
    80:'弱いにわか雨', 81:'にわか雨', 82:'激しいにわか雨',
    85:'弱いにわか雪', 86:'強いにわか雪',
    95:'雷雨', 96:'雷雨(雹弱)', 99:'雷雨(雹強)'
  };
  return map[code] || `code${code}`;
}
function windDirStr(deg) {
  if (deg == null) return '';
  const dirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'];
  return dirs[Math.round(deg / 22.5) % 16];
}

// ─── 月齢・潮汐計算（天文計算）───────────────────────────────────
function calcMoonAge(dateStr) {
  const d   = new Date(dateStr + 'T12:00:00');
  const y   = d.getFullYear(), m = d.getMonth()+1, day = d.getDate();
  let a = y, b = m;
  if (b <= 2) { a--; b += 12; }
  const A  = Math.floor(a / 100);
  const B  = 2 - A + Math.floor(A / 4);
  const JD = Math.floor(365.25*(a+4716)) + Math.floor(30.6001*(b+1)) + day + B - 1524.5;
  const newMoonJD     = 2451550.1;
  const synodicMonth  = 29.530588853;
  let age = (JD - newMoonJD) % synodicMonth;
  if (age < 0) age += synodicMonth;
  return Math.round(age * 10) / 10;
}
function moonPhaseName(age) {
  if (age <  1.85) return '新月';
  if (age <  5.55) return '三日月';
  if (age <  9.25) return '上弦';
  if (age < 12.95) return '十日夜';
  if (age < 16.65) return '満月';
  if (age < 20.35) return '十六夜';
  if (age < 24.05) return '下弦';
  if (age < 27.75) return '二十六夜';
  return '晦日';
}
function tideType(moonAge) {
  if (moonAge <= 2  || moonAge >= 28) return '大潮';
  if (moonAge <= 5)  return '中潮';
  if (moonAge <= 8)  return '小潮';
  if (moonAge <= 10) return '長潮';
  if (moonAge <= 12) return '若潮';
  if (moonAge <= 16) return '大潮';
  if (moonAge <= 19) return '中潮';
  if (moonAge <= 22) return '小潮';
  if (moonAge <= 24) return '長潮';
  if (moonAge <= 26) return '若潮';
  return '中潮';
}

// ─── 天気API レスポンスを日別集計して返すヘルパ ─────────────────
function parseWeatherJson(json) {
  const h = json.hourly;
  if (!h || !h.time) return {};
  const dataKeys   = ['temperature_2m','wind_speed_10m','wind_direction_10m','precipitation','weather_code'];
  const dataArrays = {};
  for (const k of dataKeys) dataArrays[k] = h[k] || [];
  const byDate = groupHourlyByDate(h.time, dataKeys, dataArrays);
  const result = {};
  for (const [dateStr, entries] of Object.entries(byDate)) {
    const temps   = entries.map(e => e.temperature_2m).filter(v => v != null);
    const precips = entries.map(e => e.precipitation).filter(v => v != null);
    const codes   = entries.map(e => e.weather_code).filter(v => v != null);
    let maxWind = null, maxWindDir = null;
    for (const e of entries) {
      if (e.wind_speed_10m != null && (maxWind == null || e.wind_speed_10m > maxWind)) {
        maxWind    = e.wind_speed_10m;
        maxWindDir = e.wind_direction_10m;
      }
    }
    result[dateStr] = {
      気温_平均: avg(temps),
      気温_最高: maxVal(temps),
      気温_最低: minVal(temps),
      風速_最大: maxWind    != null ? Math.round(maxWind*10)/10 : null,
      風向:      maxWindDir != null ? windDirStr(maxWindDir)    : '',
      降水量:    sumVal(precips),
      天気コード: codes.length ? Math.max(...codes)              : null,
      天気:       codes.length ? weatherDesc(Math.max(...codes)) : ''
    };
  }
  return result;
}

// ─── API取得：天気（archive / forecast を境界で分割して両方取る） ──
async function fetchWeatherForStation(station, fromDate, toDate) {
  const fiveDaysAgo = addDays(today(), -5);
  const result = {};

  // ① アーカイブ区間 (fromDate 〜 min(toDate, fiveDaysAgo))
  if (fromDate <= fiveDaysAgo) {
    const arcEnd = toDate <= fiveDaysAgo ? toDate : fiveDaysAgo;
    const url    = weatherArchiveUrl(station.lat, station.lng, fromDate, arcEnd);
    try {
      const res  = await fetchWithRetry(url);
      const json = await res.json();
      Object.assign(result, parseWeatherJson(json));
    } catch (e) {
      console.warn(`    ⚠ archive 天気取得失敗 (${fromDate}〜${arcEnd}): ${e.message}`);
    }
    await new Promise(r => setTimeout(r, API_DELAY));
  }

  // ② フォアキャスト区間 (max(fromDate, fiveDaysAgo+1) 〜 toDate)
  if (toDate > fiveDaysAgo) {
    const fcStart = fromDate > fiveDaysAgo ? fromDate : addDays(fiveDaysAgo, 1);
    const url     = weatherForecastUrl(station.lat, station.lng, fcStart, toDate);
    try {
      const res  = await fetchWithRetry(url);
      const json = await res.json();
      Object.assign(result, parseWeatherJson(json));
    } catch (e) {
      console.warn(`    ⚠ forecast 天気取得失敗 (${fcStart}〜${toDate}): ${e.message}`);
    }
  }

  return result;
}

// ─── API取得：波浪 ────────────────────────────────────────────────
async function fetchMarineForStation(station, fromDate, toDate) {
  const url  = marineApiUrl(station.lat, station.lng, fromDate, toDate, 'hourly=wave_height,wave_direction,wave_period');
  const res  = await fetchWithRetry(url);
  const json = await res.json();
  const h    = json.hourly;
  if (!h || !h.time) return {};

  const dataKeys   = ['wave_height','wave_direction','wave_period'];
  const dataArrays = {};
  for (const k of dataKeys) dataArrays[k] = h[k] || [];
  const byDate = groupHourlyByDate(h.time, dataKeys, dataArrays);

  const result = {};
  for (const [dateStr, entries] of Object.entries(byDate)) {
    const heights = entries.map(e => e.wave_height).filter(v => v != null);
    const dirs    = entries.map(e => e.wave_direction).filter(v => v != null);
    const periods = entries.map(e => e.wave_period).filter(v => v != null);
    result[dateStr] = {
      最大波高: maxVal(heights),
      波向:     dirs.length ? windDirStr(avg(dirs)) : '',
      波周期:   avg(periods)
    };
  }
  return result;
}

// ─── API取得：水温（時間別→日別フォールバック）────────────────────
async function fetchWaterTempForStation(station, fromDate, toDate) {
  try {
    const url  = marineApiUrl(station.lat, station.lng, fromDate, toDate, 'hourly=sea_surface_temperature');
    const res  = await fetchWithRetry(url);
    const json = await res.json();
    const h    = json.hourly;
    if (h && h.time && h.sea_surface_temperature) {
      const byDate = groupHourlyByDate(h.time, ['sea_surface_temperature'], { sea_surface_temperature: h.sea_surface_temperature });
      const result = {};
      for (const [dateStr, entries] of Object.entries(byDate)) {
        const temps = entries.map(e => e.sea_surface_temperature).filter(v => v != null);
        if (temps.length) result[dateStr] = { 水温: avg(temps) };
      }
      if (Object.keys(result).length > 0) return result;
    }
  } catch (e) {
    console.warn('  hourly水温取得失敗、日別フォールバックに切替:', e.message);
  }
  // 日別フォールバック
  const url2  = marineApiUrl(station.lat, station.lng, fromDate, toDate, 'daily=sea_surface_temperature_mean');
  const res2  = await fetchWithRetry(url2);
  const json2 = await res2.json();
  const d     = json2.daily;
  if (!d || !d.time) return {};
  const result = {};
  for (let i = 0; i < d.time.length; i++) {
    const mean = d.sea_surface_temperature_mean ? d.sea_surface_temperature_mean[i] : null;
    if (mean != null) result[d.time[i]] = { 水温: Math.round(mean*10)/10 };
  }
  return result;
}

// ─── CSV 読み書き ─────────────────────────────────────────────────
const CSV_HEADER = '日付,地点名,観測地点名,県,緯度,経度,気温_平均,気温_最高,気温_最低,風速_最大,風向,降水量,天気コード,天気,水温,最大波高,波向,波周期,潮汐,月齢,月相';

// 全地点共通の最新日（従来ロジック互換、主に初期化用）
function readLatestDate() {
  if (!fs.existsSync(CSV_FILE)) return DEFAULT_START_DATE;
  const lines = fs.readFileSync(CSV_FILE, 'utf8').replace(/^\uFEFF/, '').trim().split('\n').filter(l => l.trim());
  if (lines.length <= 1) return DEFAULT_START_DATE;
  let latest = DEFAULT_START_DATE;
  for (let i = 1; i < lines.length; i++) {
    const date = lines[i].split(',')[0];
    if (date && date > latest) latest = date;
  }
  return latest;
}

// 地点ごとの最新日。ある地点が前回途中失敗していても欠損を取り直す。
function readLatestDateByStation() {
  const map = {};
  if (!fs.existsSync(CSV_FILE)) return map;
  const lines = fs.readFileSync(CSV_FILE, 'utf8').replace(/^\uFEFF/, '').trim().split('\n').filter(l => l.trim());
  if (lines.length <= 1) return map;
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(',');
    const date = cols[0], station = cols[1];
    if (!date || !station) continue;
    if (!map[station] || date > map[station]) map[station] = date;
  }
  return map;
}

function readExistingKeys() {
  const existing = new Set();
  if (!fs.existsSync(CSV_FILE)) return existing;
  const lines = fs.readFileSync(CSV_FILE, 'utf8').replace(/^\uFEFF/, '').trim().split('\n').filter(l => l.trim());
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(',');
    if (cols[0] && cols[1]) existing.add(`${cols[0]}_${cols[1]}`);
  }
  return existing;
}

// 地点ごとに既存日付のSetを返す
function readExistingDatesByStation() {
  const map = {};
  if (!fs.existsSync(CSV_FILE)) return map;
  const lines = fs.readFileSync(CSV_FILE, 'utf8').replace(/^\uFEFF/, '').trim().split('\n').filter(l => l.trim());
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(',');
    const date = cols[0], station = cols[1];
    if (!date || !station) continue;
    if (!map[station]) map[station] = new Set();
    map[station].add(date);
  }
  return map;
}

// 連続日付を CHUNK_DAYS 以内のブロックにまとめる
// 入力: ソート済みの日付配列。出力: [{from, to}] の配列
function groupContiguous(sortedDates, maxDays) {
  if (sortedDates.length === 0) return [];
  const chunks = [];
  let start = sortedDates[0], end = sortedDates[0], count = 1;
  for (let i = 1; i < sortedDates.length; i++) {
    const expectedNext = addDays(end, 1);
    if (sortedDates[i] === expectedNext && count < maxDays) {
      end = sortedDates[i]; count++;
    } else {
      chunks.push({ from: start, to: end });
      start = sortedDates[i]; end = sortedDates[i]; count = 1;
    }
  }
  chunks.push({ from: start, to: end });
  return chunks;
}

function appendToCSV(rows) {
  if (rows.length === 0) return;
  if (!fs.existsSync(CSV_FILE)) {
    fs.writeFileSync(CSV_FILE, '\uFEFF' + CSV_HEADER + '\n', 'utf8');
  }
  const lines = rows.map(r => [
    r.日付, r.地点名, r.観測地点名, r.県, r.緯度, r.経度,
    r.気温_平均  ?? '', r.気温_最高  ?? '', r.気温_最低 ?? '',
    r.風速_最大  ?? '', r.風向       ?? '', r.降水量    ?? '',
    r.天気コード ?? '', r.天気       ?? '',
    r.水温       ?? '', r.最大波高   ?? '', r.波向      ?? '', r.波周期 ?? '',
    r.潮汐       ?? '', r.月齢       ?? '', r.月相      ?? ''
  ].join(','));
  fs.appendFileSync(CSV_FILE, lines.join('\n') + '\n', 'utf8');
}

function readAllCSV() {
  if (!fs.existsSync(CSV_FILE)) return [];
  const lines   = fs.readFileSync(CSV_FILE, 'utf8').replace(/^\uFEFF/, '').trim().split('\n').filter(l => l.trim());
  if (lines.length <= 1) return [];
  const headers = lines[0].split(',');
  return lines.slice(1).map(line => {
    const cols = line.split(',');
    const obj  = {};
    headers.forEach((h, i) => { obj[h] = cols[i] || ''; });
    return obj;
  });
}

// ─── メイン ───────────────────────────────────────────────────────
async function main() {
  console.log('==========================================================');
  console.log(' 釣り条件データ自動更新 (update-conditions.js)');
  console.log(`  実行日時: ${new Date().toISOString()}`);
  console.log('==========================================================');

  const existingByStation = readExistingDatesByStation();
  const toDate = addDays(today(), -1); // APIの安定性のため前日まで

  console.log(`取得上限日      : ${toDate}`);
  console.log(`地点別既存日数  : ${Object.entries(existingByStation).map(([k,v])=>`${k}=${v.size}`).join(', ')}`);

  const existingKeys = readExistingKeys();
  const newRows      = [];

  for (const station of STATIONS) {
    const existing = existingByStation[station.name] || new Set();
    // その地点が DB に初登場した日を基準にし、以降の欠損日のみ取得する
    let earliest = DEFAULT_START_DATE;
    if (existing.size > 0) {
      earliest = [...existing].sort()[0];
    }
    // earliest 〜 toDate の全日付から実在する日を引いて欠損日リストを作る
    const missing = [];
    let cur = earliest;
    while (cur <= toDate) {
      if (!existing.has(cur)) missing.push(cur);
      cur = addDays(cur, 1);
    }
    if (missing.length === 0) {
      console.log(`\n📍 ${station.name} (${station.pref}) — 欠損なし、スキップ`);
      continue;
    }
    console.log(`\n📍 ${station.name} (${station.pref}) — 欠損 ${missing.length}日分 (${missing[0]} 〜 ${missing[missing.length-1]})`);
    const chunks = groupContiguous(missing, CHUNK_DAYS);
    console.log(`  チャンク数: ${chunks.length}`);

    for (const chunk of chunks) {
      console.log(`  チャンク: ${chunk.from} 〜 ${chunk.to}`);

      let weatherData = {}, waterData = {}, marineData = {};

      try {
        weatherData = await fetchWeatherForStation(station, chunk.from, chunk.to);
        console.log(`  ✓ 天気: ${Object.keys(weatherData).length}日分`);
      } catch (e) { console.error(`  ✗ 天気取得エラー: ${e.message}`); }
      await new Promise(r => setTimeout(r, API_DELAY));

      try {
        waterData = await fetchWaterTempForStation(station, chunk.from, chunk.to);
        console.log(`  ✓ 水温: ${Object.keys(waterData).length}日分`);
      } catch (e) { console.error(`  ✗ 水温取得エラー: ${e.message}`); }
      await new Promise(r => setTimeout(r, API_DELAY));

      try {
        marineData = await fetchMarineForStation(station, chunk.from, chunk.to);
        console.log(`  ✓ 波浪: ${Object.keys(marineData).length}日分`);
      } catch (e) { console.error(`  ✗ 波浪取得エラー: ${e.message}`); }
      await new Promise(r => setTimeout(r, API_DELAY));

      // 期間内の全日付を列挙して1行ずつ組み立て
      const allDates = new Set([
        ...Object.keys(weatherData),
        ...Object.keys(waterData),
        ...Object.keys(marineData)
      ]);
      let cur = chunk.from;
      while (cur <= chunk.to) { allDates.add(cur); cur = addDays(cur, 1); }

      for (const dateStr of [...allDates].sort()) {
        const key = `${dateStr}_${station.name}`;
        if (existingKeys.has(key)) continue;

        const w       = weatherData[dateStr] || {};
        const wt      = waterData[dateStr]   || {};
        const m       = marineData[dateStr]  || {};
        const moonAge = calcMoonAge(dateStr);

        newRows.push({
          日付:      dateStr,
          地点名:    station.name,
          観測地点名: station.name,
          県:        station.pref,
          緯度:      station.lat,
          経度:      station.lng,
          気温_平均:  w.気温_平均  ?? '',
          気温_最高:  w.気温_最高  ?? '',
          気温_最低:  w.気温_最低  ?? '',
          風速_最大:  w.風速_最大  ?? '',
          風向:       w.風向       ?? '',
          降水量:     w.降水量     ?? '',
          天気コード: w.天気コード ?? '',
          天気:       w.天気       ?? '',
          水温:       wt.水温      ?? '',
          最大波高:   m.最大波高   ?? '',
          波向:       m.波向       ?? '',
          波周期:     m.波周期     ?? '',
          潮汐:       tideType(moonAge),
          月齢:       moonAge,
          月相:       moonPhaseName(moonAge)
        });
        existingKeys.add(key);
      }
    }
  }

  console.log(`\n新規レコード数: ${newRows.length}件`);

  if (newRows.length > 0) {
    appendToCSV(newRows);
    console.log(`✅ CSV追記完了: ${path.basename(CSV_FILE)}`);

    const allData = readAllCSV();
    fs.writeFileSync(JSON_FILE, JSON.stringify(allData, null, 2), 'utf8');
    console.log(`✅ JSONバックアップ更新: ${path.basename(JSON_FILE)}`);
  } else {
    console.log('新規データなし。');
  }

  console.log('\n==========================================================');
  console.log(' 更新完了');
  console.log('==========================================================');
}

main().catch(e => {
  console.error('\n❌ 致命的エラー:', e.message);
  process.exit(1);
});
