import pandas as pd
import numpy as np
import logging
# ranking_data_processor.py が同じディレクトリにあることを前提とします
from ranking_data_processor import RankingDataProcessor
from datetime import datetime

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# グローバル変数をシミュレーション (本番環境では自動で提供される)
# 訓練用では実際には認証は不要だが、Processorの初期化に必要なためダミーを使用
__app_id = 'j3-prediction-v1'
__firebase_config = '{"apiKey": "DUMMY", "projectId": "DUMMY", "appId": "DUMMY"}'
FIREBASE_CONFIG = __firebase_config
APP_ID = __app_id

# 訓練対象とするシーズン (RankingDataProcessorのID設定に合わせる)
TARGET_YEARS = [2022, 2023, 2024] 

def load_all_historical_match_results() -> pd.DataFrame:
    """
    [重要: ユーザーが修正すべき箇所] 
    過去のシーズン（TARGET_YEARS）のJ3全試合の結果をロードする関数。
    
    app3_st.pyなどで利用している、クリーンアップ済みの
    実際の試合結果DataFrameをロードするロジックに置き換えてください。
    
    返却されるDataFrameは、以下のカラムを **必須** とします:
    - '年度' (int): 試合開催年 (例: 2024)
    - '節' (int): 試合開催節 (例: 15)
    - 'リーグ' (str): リーグ名 ('J3'のみを想定)
    - 'ホーム' (str): ホームチーム名 (例: 'FC岐阜')
    - 'アウェイ' (str): アウェイチーム名 (例: 'FC大阪')
    - 'ホーム得点' (int): ホームチームの最終得点
    - 'アウェイ得点' (int): アウェイチームの最終得点
    - 'H_Recent_Points' (int): 試合直前のホームの直近5試合の勝ち点 (F2計算用)
    - 'A_Recent_Points' (int): 試合直前のアウェイの直近5試合の勝ち点 (F2計算用)
    """
    logging.warning("ダミーデータを使用しています。実際のデータロードロジックに置き換えてください。")
    
    # --- ここから実際のデータロードロジックに置き換えてください ---
    
    # 訓練データ構造をシミュレーションするためのダミーデータ (J3のみ)
    data = {
        '年度': [2024, 2024, 2023, 2023, 2022, 2022],
        '節': [5, 5, 20, 20, 30, 30],
        'リーグ': ['J3', 'J3', 'J3', 'J3', 'J3', 'J3'],
        'ホーム': ['大宮', '長野', '八戸', '琉球', '愛媛', '今治'],
        'アウェイ': ['今治', '沼津', '相模原', '宮崎', '鳥取', '福島'],
        'ホーム得点': [2, 1, 1, 3, 0, 2],
        'アウェイ得点': [0, 1, 2, 0, 1, 1],
        'H_Recent_Points': [10, 5, 4, 12, 6, 7], # 直近5試合の勝ち点 (F2のデータ)
        'A_Recent_Points': [4, 8, 9, 3, 10, 5]  # 直近5試合の勝ち点 (F2のデータ)
    }
    df = pd.DataFrame(data)
    
    # --- データ型の強制変換 (ロードしたデータにも適用してください) ---
    for col in ['年度', '節', 'ホーム得点', 'アウェイ得点', 'H_Recent_Points', 'A_Recent_Points']:
        df[col] = df[col].astype(int)
    
    # J3の試合のみを対象とし、ターゲット年のみに絞り込む
    df = df[
        (df['リーグ'] == RankingDataProcessor.TARGET_LEAGUE) & 
        (df['年度'].isin(TARGET_YEARS))
    ].reset_index(drop=True)

    return df

def generate_training_data() -> pd.DataFrame:
    """
    過去の全試合結果から特徴量を計算し、訓練用データセット（DataFrame）を生成する。
    """
    logging.info(f"--- 1. 過去のJ3試合結果 ({', '.join(map(str, TARGET_YEARS))}年) をロード開始 ---")
    
    # 過去の試合結果DataFrameをロード
    match_df = load_all_historical_match_results()
    
    if match_df.empty:
        logging.error("試合結果データが空のため、訓練データ生成を中止します。")
        return pd.DataFrame()

    logging.info(f"ロードされた試合数: {len(match_df)}")
    
    # RankingDataProcessorを初期化
    processor = RankingDataProcessor(firebase_config=FIREBASE_CONFIG, app_id=APP_ID)
    
    feature_list = []

    logging.info("--- 2. 各試合の特徴量 (F1, F2, F3, F4) の計算開始 ---")
    
    # 目的変数 (Target Variable Y): ホーム勝利 (1) or それ以外 (0) を計算
    match_df['Y_HomeWin'] = np.where(match_df['ホーム得点'] > match_df['アウェイ得点'], 1, 0)
    
    for index, row in match_df.iterrows():
        try:
            # F2 (フォーム差) の計算に必要な、直近5試合の勝ち点
            recent_H = row['H_Recent_Points']
            recent_A = row['A_Recent_Points']
            
            # 特徴量ベクトルの計算
            features = processor.calculate_features(
                year=row['年度'],
                match_day=row['節'],
                home_team=row['ホーム'],
                away_team=row['アウェイ'],
                recent_points_H=recent_H,
                recent_points_A=recent_A
            )

            if features:
                # 目的変数Yを特徴量辞書に追加
                features['Y_HomeWin'] = row['Y_HomeWin']
                
                # その他のメタデータも追加（分析やデバッグに便利）
                features['年度'] = row['年度']
                features['節'] = row['節']
                features['ホーム'] = row['ホーム']
                features['アウェイ'] = row['アウェイ']
                
                feature_list.append(features)

        except Exception as e:
            logging.error(f"特徴量計算中にエラーが発生 (Index {index}): {e}", exc_info=True)
            continue

    if not feature_list:
        logging.error("計算可能な特徴量を持つ試合がありませんでした。")
        return pd.DataFrame()

    # 特徴量リストをDataFrameに変換
    training_df = pd.DataFrame(feature_list)
    
    logging.info(f"--- 3. 訓練データセット生成完了。サイズ: {training_df.shape} ---")
    
    return training_df

if __name__ == '__main__':
    # 訓練データの生成と表示（デバッグ）
    final_training_data = generate_training_data()
    
    if not final_training_data.empty:
        print("\n--- 生成された訓練データセットのプレビュー ---")
        print(final_training_data.head())
        print("\n--- 統計情報 ---")
        print(final_training_data[['Y_HomeWin', 'F1_RankDiff', 'F2_FormDiff', 'F3_GDDiff', 'F4_HomeAdv']].describe())
