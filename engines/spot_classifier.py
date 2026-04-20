"""
spot_classifier.py — Bグループ分類エンジン

役割:
  raw spot（Aグループ A.spot の自由記述）を canonical_spot に正規化し、
  lat/lng から気象8地点・海流5地点を Haversine で割当てる。
  閾値外は "その他" / null に退避する。

設計準拠:
  - 設計_W2-2_Bグループ_20260417.md §3, §4
  - 設計_W3-1_統合アーキ_20260417.md §4.1, §4.2, §4.7
  - 設計_W3-2_物理実装方式_20260418.md §3.2

4段正規化パイプライン:
  1) NFKC Unicode正規化
  2) 空白記号除去（半/全角空白、タブ、括弧）
  3) 県名プレフィックス除去（残余が空にならない場合のみ）
  4) 別名辞書（spot_canonical_rules.json の rules）

閾値:
  - 気象  WEATHER_DISTANCE_THRESHOLD_KM = 300 → 超過で "その他"
  - 海流  CURRENT_DISTANCE_THRESHOLD_KM =  50 → 超過で null

タイブレーク:
  - 距離（小数6桁）＞ マスター定義順 ＞ UTF-8バイト順
"""

from __future__ import annotations

import json
import math
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ============================================================
# 閾値定数（W2-2 §3.3）
# ============================================================
WEATHER_DISTANCE_THRESHOLD_KM = 300.0
CURRENT_DISTANCE_THRESHOLD_KM = 50.0

# "その他" sentinel（W3-1 §4.7 案3：B対応表では "その他"）
OTHER_SENTINEL = "その他"

# "不明" sentinel（W7-1 §1, 2026-04-20 追加）
# 自動分類不能（現時点では座標欠落 ＋ 非空 canonical）で、人レビューが必要な状態。
# "その他"（座標ありで閾値超過 = 分類として正解）と区別するための第二の sentinel。
# CI パイプラインの「不明行検出ガード」が nearest_station=="不明" の行を検出したら
# push をブロックする設計（W7-1 §4-2, §4-3）。
UNKNOWN_SENTINEL = "不明"

# 地球半径（km）
EARTH_RADIUS_KM = 6371.0


# ============================================================
# 結果型
# ============================================================
@dataclass
class ClassifyResult:
    """分類結果。lat/lng が None の場合は station/point は None のまま返す。"""

    raw_spot: str
    canonical_spot: str
    nearest_station: Optional[str]  # 気象地点短名 / "その他" / None（座標不明）
    distance_km: Optional[float]
    current_point: Optional[str]  # 海流地点名 / None
    current_distance_km: Optional[float]


# ============================================================
# エンジン本体
# ============================================================
class SpotClassifier:
    """釣り場名と座標から気象/海流地点を分類するエンジン。"""

    def __init__(
        self,
        stations_master_path: str | Path,
        canonical_rules_path: str | Path,
    ) -> None:
        self._stations_master_path = Path(stations_master_path)
        self._canonical_rules_path = Path(canonical_rules_path)

        with self._stations_master_path.open(encoding="utf-8") as f:
            self._stations = json.load(f)
        with self._canonical_rules_path.open(encoding="utf-8") as f:
            self._rules_doc = json.load(f)

        # マスター定義順を保持したまま配列として持つ（タイブレーク用）
        self._weather_stations: list[dict] = list(self._stations.get("weather_stations", []))
        self._current_points: list[dict] = list(self._stations.get("current_points", []))

        # 別名辞書（from 正規化キー → to canonical）
        self._aliases: dict[str, str] = {
            r["from"]: r["to"]
            for r in self._rules_doc.get("rules", [])
            if r.get("type") == "alias"
        }

        stopwords = self._rules_doc.get("stopwords", {})
        # 長い方から剥離するため長さ降順
        self._prefixes: list[str] = sorted(
            stopwords.get("prefixes", []), key=len, reverse=True
        )
        self._whitespace: list[str] = list(stopwords.get("whitespace", []))
        self._brackets: list[str] = list(stopwords.get("brackets", []))

    # ------------------------------------------------------------
    # 正規化
    # ------------------------------------------------------------
    def normalize_spot_name(self, raw_spot: str) -> str:
        """
        4段正規化パイプライン。

          Step1: NFKC Unicode正規化
          Step2: 空白・括弧除去
          Step3: 県名プレフィックス除去（残余が空にならない場合のみ）
          Step4: 別名辞書で完全一致変換

        空/None 入力 → "" を返す。
        """
        if raw_spot is None:
            return ""
        s = str(raw_spot)

        # Step1: NFKC
        s = unicodedata.normalize("NFKC", s)

        # Step2: 空白・括弧除去
        for ws in self._whitespace:
            s = s.replace(ws, "")
        for br in self._brackets:
            s = s.replace(br, "")

        if s == "":
            return ""

        # Step3: 県名プレフィックス除去（残余が空にならない場合のみ）
        for pref in self._prefixes:
            if s.startswith(pref) and len(s) > len(pref):
                s = s[len(pref):]
                break  # 一度だけ剥離

        # Step4: 別名辞書
        if s in self._aliases:
            s = self._aliases[s]

        return s

    # ------------------------------------------------------------
    # 距離計算
    # ------------------------------------------------------------
    @staticmethod
    def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Haversineで2点間の大円距離（km）を返す。"""
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlmb = math.radians(lng2 - lng1)
        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return EARTH_RADIUS_KM * c

    # ------------------------------------------------------------
    # 最寄り検索（タイブレーク対応）
    # ------------------------------------------------------------
    def _nearest(
        self, lat: float, lng: float, points: list[dict]
    ) -> tuple[str, float]:
        """
        points から最近傍を返す。タイブレーク規則：
          1. 距離（小数6桁丸め）で小さい方
          2. マスター定義順（先に出現）
          3. 名前のUTF-8バイト順
        """
        best_idx = -1
        best_dist_round = math.inf
        best_raw_dist = math.inf

        for idx, p in enumerate(points):
            d = self.haversine_km(lat, lng, p["lat"], p["lng"])
            d_round = round(d, 6)
            if d_round < best_dist_round:
                best_idx = idx
                best_dist_round = d_round
                best_raw_dist = d
                continue
            if d_round == best_dist_round:
                # タイブレーク2: 既存の方がマスター定義順で先 → 維持
                # （idx は昇順に走査しているので、単に continue で維持される）
                # ただし、名前のUTF-8バイト順も考慮（普通は到達しない）
                cur_name = points[best_idx]["name"].encode("utf-8")
                new_name = p["name"].encode("utf-8")
                if new_name < cur_name:
                    # 万一定義順が逆になっても決定的にする
                    best_idx = idx
                    best_raw_dist = d

        return points[best_idx]["name"], best_raw_dist

    # ------------------------------------------------------------
    # メイン分類
    # ------------------------------------------------------------
    def classify(
        self,
        raw_spot: str,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
    ) -> ClassifyResult:
        """
        raw_spot を canonical に正規化し、lat/lng から最近傍を割り当てる。

        戻り値 nearest_station の判定境界（W7-1 §4-1 の表）：
          - raw が空文字列 / None     : None        （空は空のまま扱う）
          - raw あり＋座標欠落        : "不明"      （W7-1 新、人レビュー必要）
          - raw あり＋座標あり＋>300km: "その他"    （閾値超過、分類として正解）
          - raw あり＋座標あり＋≤300km: station 名
        """
        canonical = self.normalize_spot_name(raw_spot)

        # 空入力は早期 return（None のまま返す、UNKNOWN にはしない）
        if canonical == "":
            return ClassifyResult(
                raw_spot=raw_spot if raw_spot is not None else "",
                canonical_spot="",
                nearest_station=None,
                distance_km=None,
                current_point=None,
                current_distance_km=None,
            )

        # 座標欠落：canonical は取れているが距離判定が不能なので UNKNOWN_SENTINEL を返す。
        # （substring fallback は W7-2 で追加、本フェーズではまだ None→"不明" 昇格のみ）
        if lat is None or lng is None:
            return ClassifyResult(
                raw_spot=raw_spot,
                canonical_spot=canonical,
                nearest_station=UNKNOWN_SENTINEL,
                distance_km=None,
                current_point=None,
                current_distance_km=None,
            )

        # 気象8地点
        w_name, w_dist = self._nearest(lat, lng, self._weather_stations)
        if w_dist > WEATHER_DISTANCE_THRESHOLD_KM:
            nearest_station = OTHER_SENTINEL
        else:
            nearest_station = w_name

        # 海流5地点
        c_name, c_dist = self._nearest(lat, lng, self._current_points)
        if c_dist > CURRENT_DISTANCE_THRESHOLD_KM:
            current_point: Optional[str] = None
            current_distance_km: Optional[float] = None
        else:
            current_point = c_name
            current_distance_km = c_dist

        return ClassifyResult(
            raw_spot=raw_spot,
            canonical_spot=canonical,
            nearest_station=nearest_station,
            distance_km=w_dist,
            current_point=current_point,
            current_distance_km=current_distance_km,
        )


# ============================================================
# CLI（動作確認用）
# ============================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SpotClassifier 単発テスト")
    parser.add_argument("--stations", required=True, help="stations_master.json のパス")
    parser.add_argument("--rules", required=True, help="spot_canonical_rules.json のパス")
    parser.add_argument("--spot", required=True, help="raw spot 文字列")
    parser.add_argument("--lat", type=float, default=None)
    parser.add_argument("--lng", type=float, default=None)
    args = parser.parse_args()

    clf = SpotClassifier(args.stations, args.rules)
    r = clf.classify(args.spot, args.lat, args.lng)
    print(
        "raw={raw!r}\n"
        "canonical={can!r}\n"
        "nearest_station={st!r} (dist={wd})\n"
        "current_point={cp!r} (dist={cd})".format(
            raw=r.raw_spot,
            can=r.canonical_spot,
            st=r.nearest_station,
            wd=r.distance_km,
            cp=r.current_point,
            cd=r.current_distance_km,
        )
    )
