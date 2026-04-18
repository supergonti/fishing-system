// scripts/merge-data.js
// fishing_data.csv × fishing_condition_db.csv → fishing_integrated.csv (LEFT JOIN)
// 結合キー: date × nearest_station = 日付 × 地点名

const fs   = require('fs');
const path = require('path');

const FISHING_CSV  = path.join(__dirname, '..', 'data', 'fishing_data.csv');
const CONDITION_CSV = path.join(__dirname, '..', 'data', 'fishing_condition_db.csv');
const OUTPUT_CSV   = path.join(__dirname, '..', 'data', 'fishing_integrated.csv');

// ─── 8観測地点マスタ（nearest_station 未設定時のフォールバック用）───
const STATIONS = [
  { name: '室戸',   lat: 33.29, lng: 134.18 },
  { name: '高知',   lat: 33.56, lng: 133.54 },
  { name: '足摺',   lat: 32.72, lng: 132.72 },
  { name: '宇和島', lat: 33.22, lng: 132.56 },
  { name: '松山',   lat: 33.84, lng: 132.77 },
  { name: '来島',   lat: 34.12, lng: 132.99 },
  { name: '高松',   lat: 34.35, lng: 134.05 },
  { name: '阿南',   lat: 33.92, lng: 134.66 }
];

// ─── Haversine 距離（km）────────────────────────────────────────
function haversine(lat1, lng1, lat2, lng2) {
  const R    = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a    = Math.sin(dLat/2)**2
    + Math.cos(lat1*Math.PI/180) * Math.cos(lat2*Math.PI/180) * Math.sin(dLng/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

function findNearestStation(lat, lng) {
  if (!lat || !lng || isNaN(parseFloat(lat)) || isNaN(parseFloat(lng))) return '';
  let nearest = '', minDist = Infinity;
  for (const s of STATIONS) {
    const d = haversine(parseFloat(lat), parseFloat(lng), s.lat, s.lng);
    if (d < minDist) { minDist = d; nearest = s.name; }
  }
  return minDist < 300 ? nearest : ''; // 300km 超は対象外
}

// ─── CSV パーサー（クォート対応）────────────────────────────────
function parseCSVLine(line) {
  const result = [];
  let current  = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i+1] === '"') { current += '"'; i++; }
      else inQuotes = !inQuotes;
    } else if (ch === ',' && !inQuotes) {
      result.push(current); current = '';
    } else {
      current += ch;
    }
  }
  result.push(current);
  return result;
}

function parseCSV(content) {
  const lines   = content.replace(/^\uFEFF/, '').trim().split('\n').filter(l => l.trim());
  if (lines.length === 0) return { headers: [], rows: [] };
  const headers = lines[0].split(',').map(h => h.trim());
  const rows    = [];
  for (let i = 1; i < lines.length; i++) {
    if (!lines[i].trim()) continue;
    const cols = parseCSVLine(lines[i]);
    const obj  = {};
    headers.forEach((h, idx) => { obj[h] = (cols[idx] || '').trim(); });
    rows.push(obj);
  }
  return { headers, rows };
}

// ─── CSV エスケープ ───────────────────────────────────────────────
function escapeCSV(val) {
  if (val == null) return '';
  const s = String(val);
  if (s.includes(',') || s.includes('"') || s.includes('\n')) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

// ─── メイン ───────────────────────────────────────────────────────
function main() {
  console.log('==========================================================');
  console.log(' 釣果 × 環境データ 結合処理 (merge-data.js)');
  console.log(`  実行日時: ${new Date().toISOString()}`);
  console.log('==========================================================');

  // 釣果CSV 読み込み
  if (!fs.existsSync(FISHING_CSV)) {
    console.error(`❌ 釣果CSVが見つかりません: ${FISHING_CSV}`);
    process.exit(1);
  }
  const { rows: fishingRows } = parseCSV(fs.readFileSync(FISHING_CSV, 'utf8'));
  console.log(`釣果データ    : ${fishingRows.length}件`);

  // 環境条件CSV 読み込み
  if (!fs.existsSync(CONDITION_CSV)) {
    console.error(`❌ 環境条件CSVが見つかりません: ${CONDITION_CSV}`);
    process.exit(1);
  }
  const { rows: conditionRows } = parseCSV(fs.readFileSync(CONDITION_CSV, 'utf8'));
  console.log(`環境データ    : ${conditionRows.length}件`);

  // 環境データを「日付_地点名」でインデックス化
  const condMap = new Map();
  for (const row of conditionRows) {
    const key = `${row['日付']}_${row['地点名']}`;
    condMap.set(key, row);
  }
  console.log(`環境インデックス: ${condMap.size}キー`);

  // 統合CSVのヘッダー定義
  // ※ 釣果側の既存列 (weather/temp/water_temp/wind) は手動読み取り値として残す
  // ※ 環境DBからの自動取得値は「_計測」を付けて区別
  const OUTPUT_HEADER = [
    'date', 'time', 'species', 'size_cm', 'weight_kg', 'count', 'bait', 'method',
    'spot', 'spot_lat', 'spot_lng', 'nearest_station',
    'tide', 'weather', 'temp', 'water_temp', 'wind', 'memo', 'source',
    '気温_平均', '気温_最高', '気温_最低', '風速_最大', '風向_計測',
    '降水量', '天気コード', '天気_計測',
    '水温_計測', '最大波高', '波向', '波周期',
    '潮汐_計測', '月齢', '月相'
  ];

  let matched   = 0;
  let unmatched = 0;
  let noStation = 0;
  const outputRows = [];

  for (const r of fishingRows) {
    // nearest_station の決定（V5.5以降は記録済み / 旧データはHaversine再計算）
    let nearestStation = r.nearest_station || '';
    if (!nearestStation) {
      if (r.spot_lat && r.spot_lng) {
        nearestStation = findNearestStation(r.spot_lat, r.spot_lng);
        if (nearestStation) {
          console.log(`  ℹ Haversine補完: ${r.date} ${r.spot} → ${nearestStation}`);
        }
      }
    }

    // 環境データとの結合
    const lookupKey = nearestStation ? `${r.date}_${nearestStation}` : '';
    const cond      = lookupKey ? condMap.get(lookupKey) : null;

    if (!nearestStation) {
      noStation++;
    } else if (cond) {
      matched++;
    } else {
      unmatched++;
    }

    outputRows.push([
      r.date          || '',
      r.time          || '',
      r.species       || '',
      r.size_cm       || '',
      r.weight_kg     || '',
      r.count         || '',
      r.bait          || '',
      r.method        || '',
      r.spot          || '',
      r.spot_lat      || '',
      r.spot_lng      || '',
      nearestStation,
      r.tide          || '',
      r.weather       || '',
      r.temp          || '',
      r.water_temp    || '',
      r.wind          || '',
      r.memo          || '',
      r.source        || '',
      // 環境DB由来（_計測）
      cond?.['気温_平均']  ?? '',
      cond?.['気温_最高']  ?? '',
      cond?.['気温_最低']  ?? '',
      cond?.['風速_最大']  ?? '',
      cond?.['風向']       ?? '',
      cond?.['降水量']     ?? '',
      cond?.['天気コード'] ?? '',
      cond?.['天気']       ?? '',
      cond?.['水温']       ?? '',
      cond?.['最大波高']   ?? '',
      cond?.['波向']       ?? '',
      cond?.['波周期']     ?? '',
      cond?.['潮汐']       ?? '',
      cond?.['月齢']       ?? '',
      cond?.['月相']       ?? ''
    ].map(escapeCSV).join(','));
  }

  // 出力
  const csvContent = '\uFEFF' + OUTPUT_HEADER.join(',') + '\n' + outputRows.join('\n') + '\n';
  fs.writeFileSync(OUTPUT_CSV, csvContent, 'utf8');

  console.log('\n─── 結合結果 ───────────────────────────────');
  console.log(`  総レコード数     : ${fishingRows.length}件`);
  console.log(`  結合成功         : ${matched}件`);
  console.log(`  地点データなし   : ${noStation}件 (nearest_station未設定)`);
  console.log(`  環境データ未収録 : ${unmatched}件 (2022-01-01以前 or 地点未対応)`);
  console.log(`  出力ファイル     : ${path.basename(OUTPUT_CSV)}`);
  console.log('==========================================================');
  console.log(' 結合完了');
  console.log('==========================================================');
}

main();
