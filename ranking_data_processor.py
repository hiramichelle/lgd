import json
import requests
import pandas as pd
from bs4 import BeautifulSoup # HTMLパースのためにBeautifulSoupをインポート
from datetime import datetime

# グローバル変数をシミュレーション (本番環境では自動で提供される)
# __app_id, __firebase_config は外部で定義されている前提

class RankingDataProcessor:
    """
    過去のシーズンデータから、指定された試合日（または節）直前の
    正確な順位表と累積データを取得・計算するプロセッサ。
    """
    # J3リーグのCompetition IDを年ごとに定義。
    # このIDはJリーグサイトのURLパラメータに必須です。
    J3_COMPETITION_IDS = {
        2025: 657,
        2024: 657, # ご提供いただいたURIリストに基づく
        2023: 650, # 仮の値 (要確認: 正しいIDに置き換えてください)
        2022: 644, # 仮の値 (要確認: 正しいIDに置き換えてください)
        # 必要に応じて過去の年度を追記
    }
    
    def __init__(self, firebase_config, app_id):
        """
        プロセッサの初期化。アプリケーションIDとFirebase設定を保持。
        """
        self.app_id = app_id
        self.firebase_config = json.loads(firebase_config)
        # 順位表データをキャッシュし、同じ節への不要なリクエストを防ぐ
        self.ranking_cache = {} # {year: {match_day: {'チーム名': data}}}
        # print(f"RankingDataProcessor initialized for app: {self.app_id}") # デバッグログ抑制

    def _get_j3_competition_id(self, year: int) -> int:
        """ J3のCompetition IDを年ごとに返す """
        return self.J3_COMPETITION_IDS.get(year, 0)

    def _fetch_past_ranking_data(self, year: int, match_day: int):
        """
        Jリーグ公式サイトから、指定された年と節の『終了時点』の順位表HTMLを取得し、パースする。
        """
        comp_id = self._get_j3_competition_id(year)
        if comp_id == 0:
            print(f"ERROR: {year}年のJ3 Competition IDが未定義です。")
            return None

        # 特定の年、節、J3 IDを指定したURL
        url = (
            "https://data.j-league.or.jp/SFRT01/search"
            f"?competitionSectionId={match_day}"
            f"&competitionId={comp_id}"
            f"&yearId={year}"
        )
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status() 
            
            # --- HTMLパースロジック (BeautifulSoupを使用) ---
            soup = BeautifulSoup(response.content, 'html.parser')
            ranking_table = soup.find('table', class_='rankingTable')
            
            if not ranking_table:
                print(f"WARN: {year}年 第{match_day}節の順位表テーブルが見つかりませんでした。URL: {url}")
                return None

            team_ranking_data = {}
            # テーブルの<tbody>内の行(<tr>)を走査
            for row in ranking_table.find('tbody').find_all('tr'):
                cols = row.find_all('td')
                # 順位表の基本的な要素が揃っているか確認
                if len(cols) >= 11: 
                    try:
                        rank = int(cols[0].text.strip())
                        team_name = cols[2].text.strip()
                        points = int(cols[3].text.strip())
                        # 得失点差は11列目 (cols[10])
                        goal_diff_str = cols[10].text.strip().replace('+', '')
                        total_goal_diff = int(goal_diff_str)
                        
                        team_ranking_data[team_name] = {
                            'rank': rank, 
                            'total_goal_diff': total_goal_diff, 
                            'points': points
                        }
                    except (ValueError, IndexError) as e:
                        print(f"WARN: 順位表の行パース中にエラー発生: {e}")
                        continue
                        
            if not team_ranking_data:
                print(f"WARN: {year}年 第{match_day}節で有効なチームデータが取得できませんでした。")

            return team_ranking_data

        except requests.exceptions.HTTPError as e:
            print(f"順位表データ取得エラー (HTTP {response.status_code}): {e}")
            print(f"→ Competition IDまたは節数が間違っている可能性があります。確認してください。")
            return None
        except requests.exceptions.RequestException as e:
            print(f"順位表データ取得エラー (接続): {e}")
            return None

    def get_ranking_data_before_match(self, year: int, match_day: int, team_name: str):
        """
        指定された試合の前節終了時点の順位データを取得する。
        """
        previous_match_day = max(0, match_day - 1)
        
        # キャッシュの初期化
        if year not in self.ranking_cache:
            self.ranking_cache[year] = {}

        # 試合前節のデータがキャッシュにない場合、取得する
        if previous_match_day not in self.ranking_cache[year]:
            if previous_match_day == 0:
                # 0節（シーズン開始前）は初期値として設定
                data = {'rank': 21, 'total_goal_diff': 0, 'points': 0}
                self.ranking_cache[year][previous_match_day] = data
            else:
                # 試合前節のデータをWebから取得
                data = self._fetch_past_ranking_data(year, previous_match_day)
                if data is None:
                    # データ取得失敗時は、空の辞書をキャッシュして再試行を防ぐ
                    self.ranking_cache[year][previous_match_day] = {}
                    print(f"WARN: {year}年 第{previous_match_day}節の順位データ取得失敗。最下位/得失点差0として計算を継続します。")
                else:
                    self.ranking_cache[year][previous_match_day] = data
        
        # キャッシュからチーム固有のデータを取得
        cached_rankings = self.ranking_cache[year].get(previous_match_day, {})
        
        if previous_match_day == 0:
            # 0節の場合、チーム名に関わらず初期値を返す
            return {'rank': 21, 'total_goal_diff': 0, 'points': 0}

        if team_name in cached_rankings:
            return cached_rankings[team_name]
        else:
            # チームデータが見つからない場合も、最悪の初期値で代用
            return {'rank': 21, 'total_goal_diff': 0, 'points': 0}


    def calculate_features(self, year: int, match_day: int, home_team: str, away_team: str, recent_points_H: int, recent_points_A: int):
        """
        指定された試合の特徴量ベクトル (F1, F2, F3, F4) を計算する。
        """
        # F1 (順位差) と F3 (得失点差の差分) の計算に必要
        home_data = self.get_ranking_data_before_match(year, match_day, home_team)
        away_data = self.get_ranking_data_before_match(year, match_day, away_team)

        if not home_data or not away_data:
            print("特徴量計算に必要なデータが不十分です。計算をスキップします。")
            return None

        # F1: 順位差 (相手の順位 - 自分の順位) -> 値が大きいほどホーム有利
        f1_rank_diff = away_data['rank'] - home_data['rank'] 
        
        # F2: 直近5試合のフォーム差 (ホームの勝ち点 - アウェイの勝ち点)
        f2_form_diff = recent_points_H - recent_points_A
        
        # F3: 得失点差の差分 (ホームの得失点差 - アウェイの得失点差)
        f3_gd_diff = home_data['total_goal_diff'] - away_data['total_goal_diff']
        
        # F4: ホームアドバンテージ (Phase 1では固定値 1.0)
        f4_home_adv = 1.0

        return {
            'F1_RankDiff': f1_rank_diff,
            'F2_FormDiff': f2_form_diff,
            'F3_GDDiff': f3_gd_diff,
            'F4_HomeAdv': f4_home_adv,
        }

# ----------------------------------------------------------------------
# 実行例（デバッグ用）
# ----------------------------------------------------------------------

if __name__ == '__main__':
    # グローバル変数をシミュレーション (本番環境では自動で提供される)
    __app_id = 'j3-prediction-v1'
    __firebase_config = '{"apiKey": "...", "projectId": "...", "appId": "..."}'
    
    # 1. プロセッサの初期化
    processor = RankingDataProcessor(firebase_config=__firebase_config, app_id=__app_id)

    # 2. ダミーの入力データ
    # 例: 2023シーズンの第16節で行われる「八戸 vs 琉球」の試合を予測したい
    match_year = 2023
    match_day = 16 # 第16節の試合
    match_home_team = '八戸'
    match_away_team = '琉球'
    
    # F2に必要な直近5試合の勝ち点（これは別途、試合結果から算出済みとする）
    dummy_recent_H = 8 # 八戸: 2勝 2分 1敗 = 8点
    dummy_recent_A = 5 # 琉球: 1勝 2分 2敗 = 5点

    # 3. 特徴量の計算
    # get_ranking_data_before_match() の内部で、第15節終了時点のデータが使われる
    print("\n--- 特徴量計算の実行 ---")
    features = processor.calculate_features(
        year=match_year,
        match_day=match_day,
        home_team=match_home_team,
        away_team=match_away_team,
        recent_points_H=dummy_recent_H,
        recent_points_A=dummy_recent_A
    )

    if features:
        print("\n--- 計算された特徴量 ---")
        for key, value in features.items():
            print(f"{key}: {value}")
    else:
        print("特徴量の計算に失敗しました。")
