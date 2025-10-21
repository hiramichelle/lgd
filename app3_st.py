import streamlit as st
import pandas as pd
import logging
import requests
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.dates as mdates
import re
import unicodedata
from io import StringIO
from datetime import datetime
import numpy as np

# --- 日本語フォント設定の強化 ---
try:
    font_candidates = ['IPAexGothic', 'Noto Sans CJK JP', 'Hiragino Maru Gothic Pro', 'MS Gothic', 'BIZ UDGothic', 'Yu Gothic']
    
    font_path = None
    font_name = None
    
    for candidate in font_candidates:
        try:
            font_path = fm.findfont(candidate, fontext='ttf')
            if font_path:
                font_name = fm.FontProperties(fname=font_path).get_name()
                break
        except Exception:
            continue
            
    if font_name:
        plt.rcParams['font.family'] = font_name
        plt.rcParams['axes.unicode_minus'] = False
    else:
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['axes.unicode_minus'] = False

except Exception as e:
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams['font.family'] = 'sans-serif'

# --- ログ設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

logging.info("--- アプリケーション開始 ---")

# --------------------------------------------------------------------------
# --- ダミーのPredictorクラスの定義 ---
# --------------------------------------------------------------------------
class LeaguePredictor:
    def __init__(self, league_name, model_type='Dummy'):
        self.league_name = league_name
        self.model_type = model_type
        # ダミーの係数 (F1:順位差, F2:調子差, F3:得失点差)
        self.coefficients = {'F1': 0.15, 'F2': 0.05, 'F3': 0.2, 'Intercept': 0.5}

    def predict_proba(self, features: dict) -> float:
        """
        特徴量ディクショナリからホームチームの勝利確率を予測する (ダミーのロジスティック回帰をシミュレート)
        """
        f1 = features.get('F1_RankDiff', 0)
        f2 = features.get('F2_FormDiff', 0)
        f3 = features.get('F3_GoalDiffDiff', 0)
        fatigue_diff = features.get('F4_FatigueDiff', 0)
        
        # 線形結合 (ロジスティック回帰の線形部分)
        z = (self.coefficients['Intercept'] 
             + self.coefficients['F1'] * f1 
             + self.coefficients['F2'] * f2 
             + self.coefficients['F3'] * f3
             + (-0.05) * fatigue_diff
            )
        
        # シグモイド関数を適用して確率を算出
        try:
            home_win_prob = 1 / (1 + np.exp(-z))
        except OverflowError:
            home_win_prob = 1.0 if z > 0 else 0.0
            
        return home_win_prob

# --------------------------------------------------------------------------
# 予測関数のアップデート: 手動ウェイトの引数を追加
# --------------------------------------------------------------------------
def predict_match_outcome(
    home_team: str,
    away_team: str,
    predictor: LeaguePredictor,
    match_year: int,
    combined_ranking_df: pd.DataFrame,
    pointaggregate_df: pd.DataFrame,
    manual_weight_H: float = 0.0 # 手動調整ウェイト
) -> tuple:
    # --- 1. 特徴量計算 (ここではダミー値を使用。実際は計算が必要) ---
    features, debug_info = calculate_dummy_features(
        home_team, away_team, match_year, combined_ranking_df, pointaggregate_df
    )
    
    if not features:
        return "エラー", "特徴量の計算に失敗しました。", "red"

    # --- 2. モデルによる予測 ---
    # モデルが予測するホームチームの勝利確率 (ベースライン)
    baseline_home_win_prob = predictor.predict_proba(features)

    # --- 3. 手動ウェイトの適用 (新しいロジック) ---
    # 手動ウェイトをベースライン確率に直接加算
    final_home_win_prob = baseline_home_win_prob + manual_weight_H

    # 確率を [0.0, 1.0] の範囲にクリッピング
    final_home_win_prob = np.clip(final_home_win_prob, 0.01, 0.99)
    
    # --- 4. 結果の判定 (閾値の調整) ---
    # 引き分けの閾値を 0.05 (47.5% 〜 52.5%) に設定し、判定を厳格化
    DRAW_THRESHOLD = 0.05 
    
    # 引き分けの判定範囲
    lower_bound = 0.5 - DRAW_THRESHOLD
    upper_bound = 0.5 + DRAW_THRESHOLD

    result = ""
    color = "gray"
    
    if final_home_win_prob > upper_bound:
        result = f"{home_team} の勝利"
        color = "#1E90FF"  # ドジャーブルー (ホーム勝利)
    elif final_home_win_prob < lower_bound:
        result = f"{away_team} の勝利"
        color = "#DC143C"  # クリムゾンレッド (アウェイ勝利)
    else:
        result = "引き分け"
        color = "#3CB371"  # ミディアムシ―グリーン (引き分け)

    # 詳細情報の整形
    detail_parts = [
        f"**ベースライン確率**: {baseline_home_win_prob * 100:.1f}% ({home_team}勝利)",
        f"**手動調整ウェイト**: {manual_weight_H * 100:+.1f}%",
        f"**最終予測確率**: {final_home_win_prob * 100:.1f}% ({home_team}勝利)",
    ]
    detail = " | ".join(detail_parts)
    
    # デバッグ情報をセッションに保存
    st.session_state['debug_info'] = debug_info
    st.session_state['predict_debug'] = {
        'F1_RankDiff': features.get('F1_RankDiff'),
        'F2_FormDiff': features.get('F2_FormDiff'),
        'F3_GoalDiffDiff': features.get('F3_GoalDiffDiff'),
        'F4_FatigueDiff': features.get('F4_FatigueDiff'),
        'BaselineProb': f"{baseline_home_win_prob * 100:.1f}%",
        'ManualWeight': f"{manual_weight_H * 100:+.1f}%",
        'FinalProb': f"{final_home_win_prob * 100:.1f}%",
    }
    
    return result, detail, color

# --------------------------------------------------------------------------
# --- ダミー関数定義 ---
# --------------------------------------------------------------------------

def calculate_dummy_features(home_team, away_team, match_year, combined_ranking_df, pointaggregate_df):
    """
    ダミーの特徴量計算ロジック
    """
    # チーム名に基づくダミーの順位・得失点差
    rank_h = combined_ranking_df[combined_ranking_df['team_name'] == home_team]['rank'].iloc[0] if not combined_ranking_df[combined_ranking_df['team_name'] == home_team].empty else 10
    rank_a = combined_ranking_df[combined_ranking_df['team_name'] == away_team]['rank'].iloc[0] if not combined_ranking_df[combined_ranking_df['team_name'] == away_team].empty else 10
    gd_h = combined_ranking_df[combined_ranking_df['team_name'] == home_team]['goal_difference'].iloc[0] if not combined_ranking_df[combined_ranking_df['team_name'] == home_team].empty else 5
    gd_a = combined_ranking_df[combined_ranking_df['team_name'] == away_team]['goal_difference'].iloc[0] if not combined_ranking_df[combined_ranking_df['team_name'] == away_team].empty else -5
    
    # ダミーの直近ポイント
    recent_H = pointaggregate_df[pointaggregate_df['team_name'] == home_team]['recent_points'].iloc[0] if not pointaggregate_df[pointaggregate_df['team_name'] == home_team].empty else 10
    recent_A = pointaggregate_df[pointaggregate_df['team_name'] == away_team]['recent_points'].iloc[0] if not pointaggregate_df[pointaggregate_df['team_name'] == away_team].empty else 5

    # ダミーの疲労係数 (F4)
    days_H = 7
    days_A = 7
    fatigue_factor_H = np.exp(-0.05 * days_H) 
    fatigue_factor_A = np.exp(-0.05 * days_A) 

    features = {
        'F1_RankDiff': rank_a - rank_h,       # 順位差
        'F2_FormDiff': recent_H - recent_A,  # 調子差
        'F3_GoalDiffDiff': gd_h - gd_a,      # 得失点差の差分
        'F4_FatigueDiff': fatigue_factor_H - fatigue_factor_A, # 疲労係数の差
    }
    
    # ダミーのデバッグ情報を作成
    dummy_date = datetime(2025, 10, 14) 
    
    debug_info = {
        'ranking_H': {'rank': rank_h, 'goal_difference': gd_h},
        'ranking_A': {'rank': rank_a, 'goal_difference': gd_a},
        'form_details_H': [{'date': '2024/01/01', 'result': 'W', 'score': 3, 'weight': 1.0, 'weighted_score': 3}], # ダミー
        'form_details_A': [{'date': '2024/01/01', 'result': 'L', 'score': 0, 'weight': 1.0, 'weighted_score': 0}], # ダミー
        'rest_details': {
            'home': {'days': days_H, 'factor': fatigue_factor_H, 'last_match': dummy_date},
            'away': {'days': days_A, 'factor': fatigue_factor_A, 'last_match': dummy_date}
        }
    }

    return features, debug_info

def create_dummy_ranking_data():
    """ダミーの順位表データを作成"""
    data = {
        'team_name': ['八戸', '琉球', '今治', '大宮', '長野', '福島'],
        'rank': [1, 2, 3, 10, 11, 12],
        'goal_difference': [15, 10, 5, -5, -10, -15],
    }
    return pd.DataFrame(data)

def create_dummy_point_aggregate():
    """ダミーの直近ポイントデータを作成"""
    data = {
        'team_name': ['八戸', '琉球', '今治', '大宮', '長野', '福島'],
        'recent_points': [10, 5, 8, 3, 12, 1], # 直近5試合の勝ち点
    }
    return pd.DataFrame(data)

# --------------------------------------------------------------------------
# メインアプリケーション (UIの定義)
# --------------------------------------------------------------------------

def main():
    st.set_page_config(layout="wide", page_title="Jリーグ試合結果予測アプリ")
    
    # セッションステートの初期化
    if 'current_year' not in st.session_state:
        st.session_state.current_year = 2024
        st.session_state.combined_ranking_df = create_dummy_ranking_data()
        st.session_state.pointaggregate_df = create_dummy_point_aggregate()
        st.session_state.league_predictors = {
            'J1': LeaguePredictor('J1'),
            'J2': LeaguePredictor('J2'),
            'J3': LeaguePredictor('J3'),
        }
        st.session_state.debug_mode = False


    # サイドバーでの設定
    with st.sidebar:
        st.header("⚙️ 設定")
        league_choice = st.selectbox(
            '予測対象リーグを選択',
            list(st.session_state.league_predictors.keys()),
            key='league_choice_sidebar'
        )
        selected_league_predictor = st.session_state.league_predictors[league_choice]
        st.write(f"選択されたモデル: {selected_league_predictor.league_name} ({selected_league_predictor.model_type})")
        
        st.session_state.debug_mode = st.checkbox("デバッグ情報を表示", st.session_state.debug_mode)
        
        st.markdown("---")
        st.caption("※ 本アプリはデモであり、予測結果は実際の試合結果と一致しません。")

    
    # メインコンテンツ
    st.header(f"予測マッチアップ: {st.session_state.current_year}シーズン ({league_choice})")
    
    # --- チーム選択UI ---
    all_teams = sorted(st.session_state.combined_ranking_df['team_name'].unique().tolist())
    
    col_h, col_vs, col_a = st.columns([5, 1, 5])
    
    with col_h:
        home_team = st.selectbox('ホームチーム', all_teams, index=all_teams.index('八戸') if '八戸' in all_teams else 0, key='home_team_select')
        st.markdown(f"<h3 style='text-align: center;'>{home_team}</h3>", unsafe_allow_html=True)
    with col_a:
        away_team = st.selectbox('アウェイチーム', all_teams, index=all_teams.index('琉球') if '琉球' in all_teams else 1, key='away_team_select')
        st.markdown(f"<h3 style='text-align: center;'>{away_team}</h3>", unsafe_allow_html=True)
    with col_vs:
        st.text("")
        st.markdown("<h2 style='text-align: center; margin-top: 15px;'>VS</h2>", unsafe_allow_html=True)
    
    st.divider()

    # --- 予測の重み調整スライダー ---
    st.subheader("🛠️ 予測の重み調整 (任意)")
    st.write("特定の試合要素（主力選手の欠場、ダービーマッチなど）を加味したい場合、スライダーを左右に動かしてホームチーム勝利確率を調整します。")
    adjustment_weight_H = st.slider(
        'ホーム勝利への手動調整ウェイト',
        min_value=-0.15, # 最大±15%の確率シフト
        max_value=0.15,
        value=0.0,
        step=0.01,
        format='%.2f (ホーム確率シフト)',
        key='manual_weight_slider'
    )
    st.divider()


    if home_team == away_team:
        st.error("ホームチームとアウェイチームは異なるチームを選択してください。")
    elif st.button('試合結果を予測する', key='predict_button', use_container_width=True):
        st.subheader(f"📅 {home_team} vs {away_team} の予測結果")
        
        # 予測実行 (手動調整ウェイトを渡す)
        result, detail, color = predict_match_outcome(
            home_team,
            away_team,
            selected_league_predictor,
            st.session_state.current_year,
            st.session_state.combined_ranking_df,
            st.session_state.pointaggregate_df,
            adjustment_weight_H # <--- 手動調整ウェイト
        )
        
        # 予測結果の表示
        st.markdown(
            f"""
            <div style='background-color: {color}; padding: 20px; border-radius: 10px; color: black; text-align: center;'>
                <h3 style='margin: 0; color: white;'>{result}</h3>
            </div>
            <p style='margin-top: 10px; text-align: center;'>{detail}</p>
            """,
            unsafe_allow_html=True
        )

        # デバッグ情報表示のトグル
        if st.session_state.debug_mode and 'predict_debug' in st.session_state:
            st.subheader("📊 予測計算の詳細")
            debug_df = pd.DataFrame(st.session_state['predict_debug'], index=['値']).T
            debug_df.columns = ['説明']
            st.dataframe(debug_df)

            # 詳細なデバッグ情報を表示 (フォーム、休息など)
            debug_info = st.session_state.get('debug_info', {})
            if debug_info:
                # 順位情報
                st.write("**順位・得失点差**")
                rank_h = debug_info['ranking_H'].get('rank', 'N/A')
                rank_a = debug_info['ranking_A'].get('rank', 'N/A')
                gd_h = debug_info['ranking_H'].get('goal_difference', 'N/A')
                gd_a = debug_info['ranking_A'].get('goal_difference', 'N/A')
                
                col_h, col_a = st.columns(2)
                with col_h:
                    st.write(f"**{home_team}**")
                    st.write(f"  順位: {rank_h}位, 得失点差: {gd_h}")
                with col_a:
                    st.write(f"**{away_team}**")
                    st.write(f"  順位: {rank_a}位, 得失点差: {gd_a}")


                # 直近フォーム情報
                if debug_info['form_details_H']:
                    st.write("**ホームチームの直近5試合（加重スコア）**")
                    form_df_h = pd.DataFrame(debug_info['form_details_H'])
                    st.dataframe(form_df_h[['date', 'result', 'score', 'weight', 'weighted_score']])

                if debug_info['form_details_A']:
                    st.write("**アウェーチームの直近5試合（加重スコア）**")
                    form_df_a = pd.DataFrame(debug_info['form_details_A'])
                    st.dataframe(form_df_a[['date', 'result', 'score', 'weight', 'weighted_score']])
                
                # 休息情報
                st.write("**休息日数と疲労係数**")
                rest_details = debug_info['rest_details']
                col_h, col_a = st.columns(2)
                
                with col_h:
                    st.write(f"**{home_team}**")
                    st.write(f"  休息日数: {rest_details['home']['days']}日")
                    if rest_details['home']['last_match']:
                        st.write(f"  前試合: {rest_details['home']['last_match'].strftime('%Y/%m/%d')}")
                    st.write(f"  疲労係数: {rest_details['home']['factor']:.2f}")
                
                with col_a:
                    st.write(f"**{away_team}**")
                    st.write(f"  休息日数: {rest_details['away']['days']}日")
                    if rest_details['away']['last_match']:
                        st.write(f"  前試合: {rest_details['away']['last_match'].strftime('%Y/%m/%d')}")
                    st.write(f"  疲労係数: {rest_details['away']['factor']:.2f}")


# --------------------------------------------------------------------------
# エラーハンドリングと実行
# --------------------------------------------------------------------------
try:
    if __name__ == '__main__':
        main()
except Exception as app_e:
    logging.error(f"メインアプリケーションエラー: {app_e}", exc_info=True)
    st.error(f"アプリケーションの実行中にエラーが発生しました: {app_e}")
