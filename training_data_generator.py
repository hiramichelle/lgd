import pandas as pd
import json
from ranking_data_processor import RankingDataProcessor
from datetime import datetime

# グローバル変数をシミュレーション (本番環境では自動で提供される)
__app_id = 'j3-prediction-v1'
__firebase_config = '{"apiKey": "...", "projectId": "...", "appId": "..."}'
processor = RankingDataProcessor(firebase_config=__firebase_config, app_id=__app_id)


def _fetch_all_past_match_results(years: list) -> list:
    """
    [重要] 過去のシーズン（指定された年）の全試合結果を取得するダミー関数。
    
    ユーザーはここを、実際のFirestoreやAPIから過去の試合データを取得する
    ロジックに置き換える必要があります。

    想定されるデータの構造:
    {
        'year': 2023, 
        'match_day': 16, 
        'home_team': '八戸', 
        'away_team': '琉球',
        'home_score': 1,
        'away_score': 0,
        'home_recent_points': 8, # 既に計算済みの直近5試合の勝ち点
        'away_recent_points': 5, # 既に計算済みの直近5試合の勝ち点
    }
    """
    print(f"--- DUMMY DATA FETCHING: {years}シーズンの全試合結果 ---")
    
    # ダミーデータとして2試合のみ提供 (実際は数千行になる)
    dummy_results = [
        # 試合1: 2023年 第16節 八戸(H) vs 琉球(A) -> 八戸勝利 (HomeWin=1)
        {
            'year': 2023, 'match_day': 16, 'home_team': '八戸', 'away_team': '琉球',
            'home_score': 1, 'away_score': 0,
            'home_recent_points': 8, 'away_recent_points': 5
        },
        # 試合2: 2023年 第16節 今治(H) vs 大宮(A) -> 引き分け (HomeWin=0)
        {
            'year': 2023, 'match_day': 16, 'home_team': '今治', 'away_team': '大宮',
            'home_score': 1, 'away_score': 1,
            'home_recent_points': 6, 'away_recent_points': 10
        }
        # 実際には、2022, 2023, 2024年の全試合（約600試合）のデータをここに結合
    ]
    return dummy_results

def generate_training_data(years_to_include: list):
    """
    過去の試合結果に基づき、LRモデル訓練用のデータセットを生成しDataFrameを返す。
    """
    all_match_results = _fetch_all_past_match_results(years_to_include)
    
    if not all_match_results:
        print("過去の試合結果データが取得できませんでした。")
        return pd.DataFrame()

    feature_list = []
    
    for match in all_match_results:
        home_win = 1 if match['home_score'] > match['away_score'] else 0
        
        # 試合直前の特徴量 (F1, F3はranking_data_processorが前節終了時点を参照して計算)
        features = processor.calculate_features(
            year=match['year'],
            match_day=match['match_day'],
            home_team=match['home_team'],
            away_team=match['away_team'],
            recent_points_H=match['home_recent_points'],
            recent_points_A=match['away_recent_points']
        )
        
        if features:
            # 目的変数を特徴量に追加
            features['HomeWin'] = home_win
            
            # メタデータも追加（分析やデバッグに便利）
            features['Year'] = match['year']
            features['MatchDay'] = match['match_day']
            features['HomeTeam'] = match['home_team']
            features['AwayTeam'] = match['away_team']
            
            feature_list.append(features)
            
    # DataFrameに変換
    df_training = pd.DataFrame(feature_list)
    print(f"\n訓練データ生成完了。合計 {len(df_training)} 試合分のデータが作成されました。")
    return df_training

if __name__ == '__main__':
    # 訓練対象とするシーズン
    target_years = [2022, 2023, 2024] 
    
    df_data = generate_training_data(target_years)
    
    if not df_data.empty:
        # 実際には、このDataFrameを使ってモデル訓練に進みます
        # print("--- 訓練データセットのプレビュー ---")
        # print(df_data.head())
        
        # データセットをCSVとして保存することも可能
        # df_data.to_csv('j3_training_data.csv', index=False)
        print("\nこれでロジスティック回帰モデルの訓練準備が整いました。")
