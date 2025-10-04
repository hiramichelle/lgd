import streamlit as st
import pandas as pd
import logging
import requests
import time # <-- リトライ時の待機処理のためにtimeモジュールをインポート
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm # フォント設定を手動で行う場合に備えてインポートは残しておく
import matplotlib.ticker as ticker
import matplotlib.dates as mdates

# --- 日本語フォント設定 ---
# 現状では日本語フォントの設定は行わず、matplotlibのデフォルトフォントを使用します。
try:
    plt.rcParams['axes.unicode_minus'] = False # マイナス記号の表示は維持
    st.info("※グラフの日本語は文字化けする可能性があります。")
except Exception as e:
    st.warning(f"フォント設定中に予期せぬエラーが発生しました: {e}。デフォルトフォントを使用します。")
    plt.rcParams['axes.unicode_minus'] = False

# --- ログ設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

logging.info("--- アプリケーション開始 ---")

# --- 定数設定 ---
MAX_RETRIES = 3
RETRY_DELAY = 5 # リトライ時の待機時間 (秒)

# --------------------------------------------------------------------------
# Webスクレイピング関数 (リトライ機能を追加)
# --------------------------------------------------------------------------
@st.cache_data
def scrape_ranking_data(url):
    """
    Jリーグ公式サイトから順位表をスクレイピングする関数。（リトライ機能付き）
    """
    logging.info(f"scrape_ranking_data: URL {url} からスクレイピング開始。")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # requests.get でHTMLを取得し、それをpandasに渡す
            response = requests.get(url, headers=headers, timeout=30) 
            response.raise_for_status() # HTTPエラーがあれば例外を発生させる
            
            # 順位表のヘッダーが正しく取れない場合があるため、'順位'を含むテーブルをマッチ
            dfs = pd.read_html(response.text, flavor='lxml', header=0, match='順位') 
            
            if not dfs:
                logging.warning(f"read_htmlがテーブルを検出できませんでした。URL: {url}")
                return None
            
            df = dfs[0]
            logging.info(f"順位表スクレイピング成功 (試行 {attempt} 回目)。DataFrameの形状: {df.shape}")
            if '備考' in df.columns:
                df = df.drop(columns=['備考'])
            return df
        
        except requests.exceptions.HTTPError as errh:
            # 5xx エラーの場合のみリトライを試みる
            if 500 <= errh.response.status_code < 600 and attempt < MAX_RETRIES:
                logging.warning(f"HTTP 5xx エラーが発生: {errh}。{RETRY_DELAY}秒後にリトライします (試行 {attempt}/{MAX_RETRIES})。")
                time.sleep(RETRY_DELAY)
                continue
            logging.error(f"HTTPエラーが発生 (最終試行): {errh}")
            return None
        
        except requests.exceptions.RequestException as err:
            # タイムアウトや接続エラーの場合
            if attempt < MAX_RETRIES:
                logging.warning(f"リクエストエラーが発生: {err}。{RETRY_DELAY}秒後にリトライします (試行 {attempt}/{MAX_RETRIES})。")
                time.sleep(RETRY_DELAY)
                continue
            logging.error(f"リクエストエラーが発生 (最終試行): {err}")
            return None
            
        except Exception as e:
            logging.error(f"順位表スクレイピング中に予期せぬエラーが発生: {e}")
            return None
    
    return None # 最大リトライ回数を超えた場合

@st.cache_data
def scrape_schedule_data(url):
    """
    Jリーグ公式サイトから日程表をスクレイピングする関数。（リトライ機能付き）
    """
    logging.info(f"scrape_schedule_data: URL {url} からスクレイピング開始。")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # requests.get でHTMLを取得し、それをpandasに渡す
            response = requests.get(url, headers=headers, timeout=30) # タイムアウトは30秒のまま
            response.raise_for_status() # HTTPエラーがあれば例外を発生させる
            
            dfs = pd.read_html(response.text, flavor='lxml', header=0, match='試合日') 
            
            if not dfs:
                logging.warning(f"read_htmlがテーブルを検出できませんでした。URL: {url}")
                return None
                
            df = dfs[0]
            logging.info(f"日程表スクレイピング成功 (試行 {attempt} 回目)。DataFrameの形状: {df.shape}, カラム数: {len(df.columns)}")
            
            expected_cols = ['大会', '試合日', 'キックオフ', 'スタジアム', 'ホーム', 'スコア', 'アウェイ', 'テレビ中継']
            cols_to_keep = [col for col in expected_cols if col in df.columns]
            
            if len(cols_to_keep) < 5:
                logging.error("抽出できた列数が少なすぎます。サイトのレイアウトが大幅に変更された可能性があります。")
                return None
                
            df = df[cols_to_keep]
            return df
            
        except requests.exceptions.HTTPError as errh:
            # 5xx エラーの場合のみリトライを試みる
            if 500 <= errh.response.status_code < 600 and attempt < MAX_RETRIES:
                logging.warning(f"HTTP 5xx エラーが発生: {errh}。{RETRY_DELAY}秒後にリトライします (試行 {attempt}/{MAX_RETRIES})。")
                time.sleep(RETRY_DELAY)
                continue
            logging.error(f"HTTPエラーが発生 (最終試行): {errh}")
            return None
        
        except requests.exceptions.RequestException as err:
            # タイムアウトや接続エラーの場合
            if attempt < MAX_RETRIES:
                logging.warning(f"リクエストエラーが発生: {err}。{RETRY_DELAY}秒後にリトライします (試行 {attempt}/{MAX_RETRIES})。")
                time.sleep(RETRY_DELAY)
                continue
            logging.error(f"リクエストエラーが発生 (最終試行): {err}")
            return None
            
        except Exception as e:
            logging.error(f"日程表スクレイピング中に予期せぬエラーが発生: {e}")
            return None
            
    return None # 最大リトライ回数を超えた場合

# --------------------------------------------------------------------------
# データ加工関数 (変更なし)
# --------------------------------------------------------------------------
@st.cache_data
def create_point_aggregate_df(schedule_df):
    """日程表データから、チームごとの試合結果を集計するDataFrameを作成"""
    if schedule_df is None or schedule_df.empty:
        return pd.DataFrame()

    df = schedule_df.copy()
    
    # スコアが「数字-数字」の形式でない行を除外
    df = df[df['スコア'].str.contains('^\d+-\d+$', na=False)]
    if df.empty:
        return pd.DataFrame()
    
    df[['得点H', '得点A']] = df['スコア'].str.split('-', expand=True).astype(int)

    # 試合日の前処理
    df['試合日'] = df['試合日'].str.replace(r'\(.+\)', '', regex=True)
    df['試合日'] = df['試合日'].apply(lambda x: '20' + x if not x.startswith('20') else x)
    try:
        df['試合日'] = pd.to_datetime(df['試合日'], format='%Y/%m/%d')
    except ValueError as e:
        logging.error(f"日付変換エラー: {e}")
        return pd.DataFrame()
    
    # ホームチームのデータ集計
    home_df = df.rename(columns={'ホーム': 'チーム', 'アウェイ': '相手', '得点H': '得点', '得点A': '失点'})
    home_df['得失差'] = home_df['得点'] - home_df['失点']
    home_df['勝敗'] = home_df.apply(lambda row: '勝' if row['得点'] > row['失点'] else ('分' if row['得点'] == row['失点'] else '敗'), axis=1)
    home_df['勝点'] = home_df.apply(lambda row: 3 if row['勝敗'] == '勝' else (1 if row['勝敗'] == '分' else 0), axis=1)
    home_df['対戦相手'] = home_df['相手']
    home_df = home_df[['大会', '試合日', 'チーム', '対戦相手', '勝敗', '得点', '失点', '得失差', '勝点']]

    # アウェイチームのデータ集計
    away_df = df.rename(columns={'アウェイ': 'チーム', 'ホーム': '相手', '得点A': '得点', '得点H': '失点'})
    away_df['得失差'] = away_df['得点'] - away_df['失点']
    away_df['勝敗'] = away_df.apply(lambda row: '勝' if row['得点'] > row['失点'] else ('分' if row['得点'] == row['失点'] else '敗'), axis=1)
    away_df['勝点'] = away_df.apply(lambda row: 3 if row['勝敗'] == '勝' else (1 if row['勝敗'] == '分' else 0), axis=1)
    away_df['対戦相手'] = away_df['相手']
    away_df = away_df[['大会', '試合日', 'チーム', '対戦相手', '勝敗', '得点', '失点', '得失差', '勝点']]

    # ホームとアウェイのデータを結合
    pointaggregate_df = pd.concat([home_df, away_df], ignore_index=True)

    # 試合日でソートし、累積勝点を計算
    pointaggregate_df = pointaggregate_df.sort_values(by=['試合日'], ascending=True)
    pointaggregate_df['累積勝点'] = pointaggregate_df.groupby(['チーム'])['勝点'].cumsum()

    return pointaggregate_df


# --------------------------------------------------------------------------
# アプリケーション本体
# --------------------------------------------------------------------------
st.title('📊 Jリーグデータビューア')

# --- データのロードと初期処理を st.spinner でラップする ---
try:
    with st.spinner("Jリーグ公式サイトから最新データを取得・処理中です。初回ロードには時間がかかります (1〜2分程度)..."):
        
        # --- データの取得 ---
        current_year = 2024 # データ取得年を2024に設定
        ranking_urls = {
            'J1': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E5%AE%89%E7%94%B0%EF%BC%AA%EF%BC%91%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={current_year}&yearId={current_year}&competitionId=651&competitionSectionId=0&search=search',
            'J2': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%92%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={current_year}&yearId={current_year}&competitionId=655&competitionSectionId=0&search=search',
            'J3': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%93%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={current_year}&yearId={current_year}&competitionId=657&competitionSectionId=0&search=search'
        }
        schedule_url = f'https://data.j-league.or.jp/SFMS01/search?competition_years={current_year}&competition_frame_ids=1&competition_frame_ids=2&competition_frame_ids=3&tv_relay_station_name='

        # 順位表データの取得と結合 (4つのウェブスクレイピング実行)
        ranking_dfs = {league: scrape_ranking_data(url) for league, url in ranking_urls.items()}
        for league, df in ranking_dfs.items():
            if df is not None: df['大会'] = league
        combined_ranking_df = pd.concat([df for df in ranking_dfs.values() if df is not None], ignore_index=True)

        # 日程表データの取得 (1つのウェブスクレイピング実行)
        schedule_df = scrape_schedule_data(schedule_url)

        # 累積勝点データフレームの作成
        pointaggregate_df = create_point_aggregate_df(schedule_df)

except Exception as e:
    logging.critical(f"--- データの初期ロード中に致命的エラー: {e} ---", exc_info=True)
    st.error("データの取得または初期処理中にエラーが発生しました。時間を置いて再度お試しください。")
    st.stop() # エラー発生時に以降の処理を停止

# --- サイドバーに大会・チーム選択を上位レイヤーに配置 ---
with st.sidebar:
    st.header("ステップ 1: 大会とチーム選択")

    # 1. 大会選択 (ランキングと日程表の両方から存在する大会を抽出)
    all_available_leagues = set()
    if not combined_ranking_df.empty:
        all_available_leagues.update(combined_ranking_df['大会'].unique())
    if schedule_df is not None and not schedule_df.empty:
        all_available_leagues.update(schedule_df['大会'].unique())
        
    if not all_available_leagues:
        st.error("データが取得できませんでした。大会選択に進めません。")
        st.stop()
    
    league_options = sorted(list(all_available_leagues))
    selected_league = st.selectbox(
        '表示したい大会を選択してください:', 
        league_options, 
        key='global_league_selectbox'
    )

    # 2. チーム選択 (選択された大会の日程表データからチームを抽出)
    team_options = []
    selected_team = None
    if schedule_df is not None and not schedule_df.empty:
        filtered_by_league_schedule = schedule_df[schedule_df['大会'] == selected_league]
        if not filtered_by_league_schedule.empty:
            all_teams_in_league = pd.concat([filtered_by_league_schedule['ホーム'], filtered_by_league_schedule['アウェイ']]).unique()
            team_options = sorted(all_teams_in_league)
        
            if team_options:
                # ユーザーが前に選択したチームをデフォルトにする
                default_team_index = 0
                if 'global_team_selectbox' in st.session_state and st.session_state.global_team_selectbox in team_options:
                    default_team_index = team_options.index(st.session_state.global_team_selectbox)

                selected_team = st.selectbox(
                    '基準となるチームを選択してください:', 
                    team_options, 
                    index=default_team_index,
                    key='global_team_selectbox'
                )
        
    if not team_options:
        st.warning("この大会の日程データがないため、チーム選択はスキップされます。")
    

    st.header("ステップ 2: 表示データ選択")
    data_type = st.radio(
        "表示するデータを選択してください:", 
        ("順位表", "日程表", "直近5試合", "順位変動グラフ")
    )

# --- メイン画面の表示ロジック ---
if data_type == "順位表":
    st.header(f"{selected_league} 順位表")
    if not combined_ranking_df.empty:
        # グローバルで選択された大会でフィルタリング
        filtered_df = combined_ranking_df[combined_ranking_df['大会'] == selected_league].drop(columns=['大会'])
        st.dataframe(filtered_df)
    else:
        st.error("順位表データが正常に取得できませんでした。")

elif data_type == "日程表":
    st.header(f"{selected_league} {selected_team if selected_team else ''} 試合日程")
    if schedule_df is not None and not schedule_df.empty and selected_team:
        # グローバルで選択された大会とチームでフィルタリング
        team_filter = (schedule_df['ホーム'] == selected_team) | (schedule_df['アウェイ'] == selected_team)
        final_filtered_df = schedule_df[(schedule_df['大会'] == selected_league) & team_filter]
        st.dataframe(final_filtered_df)
    elif selected_team is None:
         st.warning("チームデータがないため、日程表を表示できません。")
    else:
        st.error("日程表データが正常に取得できませんでした。")

elif data_type == "直近5試合":
    st.header(f"{selected_league} {selected_team if selected_team else ''} 直近5試合結果")
    if not pointaggregate_df.empty and selected_team:
        # グローバルで選択された大会とチームでフィルタリング
        team_results = pointaggregate_df[(pointaggregate_df['大会'] == selected_league) & (pointaggregate_df['チーム'] == selected_team)]
        
        if team_results.empty:
             st.info(f"チーム {selected_team} の試合結果データがまだありません。")
        else:
            # 最新の5試合を取得
            recent_5_games = team_results.sort_values(by='試合日', ascending=False).head(5)
            recent_5_games = recent_5_games.sort_values(by='試合日', ascending=True) # 表示のために再度昇順にソート
            recent_5_games['試合日'] = recent_5_games['試合日'].dt.strftime('%y%m%d')
            
            st.dataframe(recent_5_games[['試合日', '対戦相手', '勝敗', '得点', '失点', '勝点']])
    elif selected_team is None:
         st.warning("チームデータがないため、直近5試合の結果を表示できません。")
    else:
        st.error("日程表データがないため、直近5試合の集計ができませんでした。")

elif data_type == "順位変動グラフ":
    st.header(f"{selected_league} 順位変動グラフ")
    if not pointaggregate_df.empty:
        
        # --- グラフ表示用のチームマルチセレクトをここで定義 ---
        filtered_df_rank = pointaggregate_df[pointaggregate_df['大会'] == selected_league]
        team_options_rank = sorted(filtered_df_rank['チーム'].unique())
        
        # グラフ用のチーム選択（複数選択）
        default_teams = []
        if selected_team in team_options_rank:
            default_teams = [selected_team]
        elif team_options_rank:
             default_teams = team_options_rank[:1]

        selected_teams_rank = st.multiselect(
            'グラフに表示するチームを選択してください (複数選択可):', 
            team_options_rank, 
            default=default_teams, 
            key='rank_team_multiselect'
        )
        # --- グラフ表示用のチームマルチセレクトここまで ---

        if not selected_teams_rank:
            st.warning("表示するチームを選択してください。")
        else:
            # 順位算出ロジックは変更なし
            min_date = filtered_df_rank['試合日'].min()
            max_date = filtered_df_rank['試合日'].max()
            
            # 最初の月曜日を計算
            start_monday_candidate = min_date - pd.to_timedelta(min_date.weekday(), unit='D')
            if start_monday_candidate < min_date:
                start_monday = start_monday_candidate + pd.to_timedelta(7, unit='D')
            else:
                start_monday = start_monday_candidate
            
            # 毎週月曜日の日付範囲を生成
            weekly_mondays = pd.date_range(start=start_monday, end=max_date + pd.to_timedelta(7, unit='D'), freq='W-MON')
            
            all_teams_in_selected_league = filtered_df_rank['チーム'].unique()
            
            weekly_rank_data = pd.DataFrame(index=weekly_mondays)

            for team in all_teams_in_selected_league: 
                team_cumulative_points = filtered_df_rank[
                    filtered_df_rank['チーム'] == team
                ].set_index('試合日')['累積勝点']
                
                team_weekly_points = team_cumulative_points.reindex(weekly_mondays, method='ffill')
                weekly_rank_data[team] = team_weekly_points
            
            weekly_rank_data = weekly_rank_data.fillna(0)

            # 週ごとの順位を計算
            weekly_rank_df_rank = weekly_rank_data.rank(axis=1, ascending=False, method='min')
            
            # --- グラフ描画 ---
            fig, ax = plt.subplots(figsize=(12, 8))
            
            all_plotted_rank_data = []
            
            for team in selected_teams_rank:
                if team in weekly_rank_df_rank.columns:
                    team_rank_data = weekly_rank_df_rank[team].dropna()
                    ax.plot(team_rank_data.index, team_rank_data.values, marker='o', linestyle='-', label=team)
                    all_plotted_rank_data.append(team_rank_data)

            if all_plotted_rank_data:
                num_teams_in_league = len(all_teams_in_selected_league)
                
                ax.set_yticks(range(1, num_teams_in_league + 1)) 
                ax.invert_yaxis() # 順位は小さい方が上に来るように反転
                
                # y軸の範囲を調整（順位の最大値まで）
                ax.set_ylim(num_teams_in_league + 1, 0)
            else:
                st.warning("選択したチームの順位データがありません。")
                st.stop()
            
            ax.set_title(f'{selected_league} 順位変動 (毎週月曜日時点)')
            ax.set_xlabel('試合日 (毎週月曜日)')
            ax.set_ylabel('順位')
            ax.grid(True)
            
            ax.legend(title="チーム", loc='best')
            
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=14)) # 2週間ごとの目盛り
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d')) # 月/日の形式
            
            plt.xticks(rotation=90) # X軸のラベルを縦に
            plt.tight_layout() # レイアウトを調整
            
            st.pyplot(fig)
    else:
        st.error("日程表データがないため、順位変動グラフを作成できませんでした。")
