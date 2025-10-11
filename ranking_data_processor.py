import json
import requests
from datetime import datetime

# Firestoreや外部APIとの連携を想定したデータ処理クラス
# 目的：特定の試合が行われた時点での正確な順位表データを提供し、特徴量F1, F3を計算可能にする。

class RankingDataProcessor:
    """
    過去のシーズンデータから、指定された試合日（または節）直前の
    正確な順位表と累積データを取得・計算するプロセッサ。
    """
    def __init__(self, firebase_config, app_id):
        # アプリケーションIDとFirebase設定は、データストレージ（Firestoreなど）にアクセスするために使用
        self.app_id = app_id
        self.firebase_config = json.loads(firebase_config)
        self.ranking_cache = {} # {year: {match_day: ranking_data}}
        
        # データベース接続の初期化（ここではスタブ/コメントアウト）
        # self.db = initialize_firestore(self.firebase_config)
        
        print(f"RankingDataProcessor initialized for app: {self.app_id}")


    def _fetch_past_ranking_data(self, year: int, match_day: int):
        """
        [重要] 外部データストレージ（Firestore or 外部API）から、
        指定された年と節の『終了時点』の順位表を取得する内部メソッド。

        F1 (順位差) と F3 (得失点差の差分) の計算に必須。
        
        実際のデータ取得ロジックはユーザー環境に依存するため、ここではダミーデータを返す。
        ユーザーはこの部分を実際のデータ取得APIに置き換える必要がある。
        
        ランキングデータは、以下の構造を想定する:
        {
            'team_name': 'FC Tokyo',
            'rank': 5,
            'total_goal_diff': 8,
            'points': 45,
            # ... その他の必要なデータ
        }
        """
        # --- 実際のデータ取得ロジックをここに記述する ---
        # 例：Firestoreのパス
        # collection_path = f'/artifacts/{self.app_id}/public/data/j3_rankings/{year}/{match_day}'
        # ranking_data = get_doc(self.db, collection_path) 
        # return ranking_data
        
        print(f"--- DUMMY DATA FETCHING: {year}シーズン 第{match_day}節終了時点 ---")

        # ダミーデータ：第15節終了時点の架空の順位表
        # この順位表は、第16節の試合の特徴量計算に使用される
        dummy_rankings = {
            '八戸': {'rank': 3, 'total_goal_diff': 15, 'points': 28},
            '今治': {'rank': 12, 'total_goal_diff': -3, 'points': 18},
            '琉球': {'rank': 1, 'total_goal_diff': 22, 'points': 35},
            '大宮': {'rank': 5, 'total_goal_diff': 8, 'points': 25},
            '宮崎': {'rank': 15, 'total_goal_diff': -10, 'points': 15},
            # 訓練データに必要なすべてのチームのデータを含めること
        }
        return dummy_rankings

    def get_ranking_data_before_match(self, year: int, match_day: int, team_name: str):
        """
        特定の試合（第N節）の特徴量を計算するために、
        その直前（第N-1節終了時点）のチームデータを取得する。
        
        Args:
            year (int): シーズン年
            match_day (int): 計算したい試合が行われる節 (例: 16節の試合の特徴量を計算したい)
            team_name (str): チーム名
        
        Returns:
            dict: チームの順位、得失点差などを含むデータ。
        """
        # 第1節の試合の特徴量を計算する場合、直前は「第0節」（シーズン開始前）と考える
        previous_match_day = max(0, match_day - 1)
        
        # キャッシュからデータを取得 (効率化のため)
        if year not in self.ranking_cache:
            self.ranking_cache[year] = {}

        if previous_match_day not in self.ranking_cache[year]:
            # 実際のデータ取得。第0節（シーズン開始前）は全て0または最下位（最下位+1など）と仮定
            if previous_match_day == 0:
                # シーズン開始前：順位はチーム数+1、得失点差は0、勝ち点は0とする
                # (J3は概ね20チームのため、ここでは21位として初期化)
                data = {'rank': 21, 'total_goal_diff': 0, 'points': 0}
            else:
                data = self._fetch_past_ranking_data(year, previous_match_day)
                self.ranking_cache[year][previous_match_day] = data
        
        # 必要なチームのデータを取り出し
        if previous_match_day == 0:
             # 第0節データは全チーム共通
             return self.ranking_cache[year][previous_match_day] 
        
        if team_name in self.ranking_cache[year][previous_match_day]:
            return self.ranking_cache[year][previous_match_day][team_name]
        else:
            print(f"ERROR: チーム名 '{team_name}' のデータが第{previous_match_day}節に見つかりません。")
            return None

    def calculate_features(self, year: int, match_day: int, home_team: str, away_team: str, recent_points_H: int, recent_points_A: int):
        """
        LRモデルのための4つの特徴量 (F1-F4) を計算する。
        
        Args:
            year, match_day: 試合情報
            home_team, away_team: 対戦チーム名
            recent_points_H, recent_points_A: 事前に計算された直近5試合の勝ち点（F2に使用）
            
        Returns:
            dict: F1, F2, F3, F4の特徴量を含む辞書。
        """
        # 試合直前のデータ（=前節終了時点のデータ）を取得
        home_data = self.get_ranking_data_before_match(year, match_day, home_team)
        away_data = self.get_ranking_data_before_match(year, match_day, away_team)

        if not home_data or not away_data:
            print("特徴量計算に必要なデータが不十分です。")
            return None

        # --- F1: 順位差 ---
        # 定義: Away Rank - Home Rank
        f1_rank_diff = away_data['rank'] - home_data['rank']

        # --- F2: 直近5試合のフォーム差 ---
        # 定義: Home Recent Points - Away Recent Points
        f2_form_diff = recent_points_H - recent_points_A

        # --- F3: 得失点差の差分 ---
        # 定義: Home Total Goal Diff - Away Total Goal Diff
        f3_gd_diff = home_data['total_goal_diff'] - away_data['total_goal_diff']

        # --- F4: ホームアドバンテージ (Phase 1: 固定値) ---
        # 定義: 定数 1.0
        f4_home_adv = 1.0

        return {
            'F1_RankDiff': f1_rank_diff,
            'F2_FormDiff': f2_form_diff,
            'F3_GDDiff': f3_gd_diff,
            'F4_HomeAdv': f4_home_adv,
        }

# ----------------------------------------------------------------------
# 実装の確認（実行例）
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
        # 期待される入力データ (第15節終了時点のダミーデータ):
        # 八戸 (Home) -> rank: 3, total_goal_diff: +15
        # 琉球 (Away) -> rank: 1, total_goal_diff: +22
        
        # F1 (順位差): Away Rank - Home Rank = 1 - 3 = -2
        # F2 (フォーム差): Home Recent - Away Recent = 8 - 5 = +3
        # F3 (得失点差の差分): Home GD - Away GD = 15 - 22 = -7
        
        print("\n[計算結果] 特徴量ベクトル:")
        print(json.dumps(features, indent=4, ensure_ascii=False))
