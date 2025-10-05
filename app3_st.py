import streamlit as st
import pandas as pd
import logging
import requests
import time
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
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
# Webスクレイピング関数 (リトライ機能付き)
# --------------------------------------------------------------------------
# @st.cache_data デコレータは、関数が受け取る引数（urlとyear）が変わらなければ、
# データの再取得を行いません。そのため、引数にyearを加えます。
@st.cache_data
def scrape_ranking_data(url, year):
    """
    Jリーグ公式サイトから順位表をスクレイピングする関数。（リトライ機能付き）
    """
    # yearを引数として受け取るが、ロジック内で直接は使用しない。st.cache_dataのため。
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
def scrape_schedule_data(url, year):
    """
    Jリーグ公式サイトから日程表をスクレイピングする関数。（リトライ機能付き）
    """
    # yearを引数として受け取るが、ロジック内で直接は使用しない。st.cache_dataのため。
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

# --- サイドバーに大会・チーム選択を上位レイヤーに配置 ---
with st.sidebar:
    # --- 1. データ年度選択 (Step 1) ---
    st.header("ステップ 1: データ年度選択")
    # 現状は2024年のみ選択可能
    selected_year = st.selectbox(
        '年度を選択してください:', 
        [2024], # 今後、公式サイトの仕様が分かればここを拡張
        index=0
    )
    current_year = selected_year # 以降のデータ取得にこの値を使用

    # --- 2. 日程表オプション（大会・チーム選択） (Step 2) ---
    st.header("ステップ 2: 大会とチーム選択")

    # データが取得されるまでは空のリストを設定
    league_options = []
    selected_league = None
    team_options = []
    selected_team = None

    # ここでは仮の選択肢を表示するため、実際のデータフィルタリングはtryブロック後に行う
    # ダミーの選択肢を表示
    selected_league = st.selectbox(
        '表示したい大会を選択してください:', 
        ['J1', 'J2', 'J3', 'データ取得中...'],
        key='global_league_selectbox_placeholder',
        disabled=True
    )
    selected_team = st.selectbox(
        '基準となるチームを選択してください:', 
        ['チームを選択'],
        key='global_team_selectbox_placeholder',
        disabled=True
    )

    # --- 3. 表示データ選択 (Step 3) ---
    st.header("ステップ 3: 表示データ選択")
    data_type = st.radio(
        "表示するデータを選択してください:", 
        ("順位表", "日程表", "直近5試合", "順位変動グラフ")
    )

# --- データのロードと初期処理を st.spinner でラップする ---
try:
    with st.spinner(f"Jリーグ公式サイトから**{current_year}年**の最新データを取得・処理中です..."):
        
        # --- データの取得 ---
        ranking_urls = {
            'J1': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E5%AE%89%E7%94%B0%EF%BC%AA%EF%BC%91%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={current_year}&yearId={current_year}&competitionId=651&competitionSectionId=0&search=search',
            'J2': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%92%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={current_year}&yearId={current_year}&competitionId=655&competitionSectionId=0&search=search',
            'J3': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%93%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={current_year}&yearId={current_year}&competitionId=657&competitionSectionId=0&search=search'
        }
        schedule_url = f'https://data.j-league.or.jp/SFMS01/search?competition_years={current_year}&competition_frame_ids=1&competition_frame_ids=2&competition_frame_ids=3&tv_relay_station_name='

        # 順位表データの取得 (年度をcache_dataの引数に追加)
        ranking_dfs = {league: scrape_ranking_data(url, current_year) for league, url in ranking_urls.items()}

        # 順位表データの結合 (クラッシュ回避ロジック)
        non_none_ranking_dfs = []
        for league, df in ranking_dfs.items():
            if df is not None:
                df['大会'] = league
                non_none_ranking_dfs.append(df)
        
        if non_none_ranking_dfs:
            combined_ranking_df = pd.concat(non_none_ranking_dfs, ignore_index=True)
        else:
            logging.warning("全てのランキングデータ取得に失敗しました。combined_ranking_dfを空で初期化します。")
            combined_ranking_df = pd.DataFrame(columns=['順位', 'チーム', '勝点', '大会']) # 必要なカラムを仮定義

        # 日程表データの取得 (年度をcache_dataの引数に追加)
        schedule_df = scrape_schedule_data(schedule_url, current_year)

        # 累積勝点データフレームの作成
        pointaggregate_df = create_point_aggregate_df(schedule_df)

except Exception as e:
    logging.critical(f"--- データの初期ロード中に致命的エラー: {e} ---", exc_info=True)
    st.error("データの取得または初期処理中にエラーが発生しました。時間を置いて再度お試しください。")
    st.stop() # エラー発生時に以降の処理を停止


# --- データを取得した後のサイドバー選択肢の再定義 ---
# Sidebarのウィジェットを再度作成し、Placeholderを上書きする
with st.sidebar:
    # Step 2の選択肢を再定義
    st.header("ステップ 2: 大会とチーム選択")
    
    # 1. 大会選択 (ランキングと日程表の両方から存在する大会を抽出)
    all_available_leagues = set()
    if not combined_ranking_df.empty:
        all_available_leagues.update(combined_ranking_df['大会'].unique())
    if schedule_df is not None and not schedule_df.empty:
        all_available_leagues.update(schedule_df['大会'].unique())
        
    if not all_available_leagues:
        st.error("データが取得できなかったため、大会選択に進めません。")
        st.stop()
    
    league_options = sorted(list(all_available_leagues))
    selected_league = st.selectbox(
        '表示したい大会を選択してください:', 
        league_options, 
        key='global_league_selectbox' # キーはプレースホルダと分ける
    )

    # 2. チーム選択 (選択された大会の日程表データからチームを抽出)
    team_options = []
    selected_team = None
    if schedule_df is not None and not schedule_df.empty:
        filtered_by_league_schedule = schedule_df[schedule_df['大会'] == selected_league]
        if not filtered_by_league_schedule.empty:
            # 大会に含まれるすべてのチーム名を取得
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
                    key='global_team_selectbox' # キーはプレースホルダと分ける
                )
        
    if not team_options and selected_league is not None:
        st.warning(f"大会 {selected_league} の日程データがないため、チーム選択はスキップされます。")
    
    # Step 3 (ラジオボタン) は上書きされないため、ここでは何もしなくてOK


# --- メイン画面の表示ロジック ---
if data_type == "順位表":
    st.header(f"{selected_league} {current_year} 順位表")
    if not combined_ranking_df.empty:
        # グローバルで選択された大会でフィルタリング
        filtered_df = combined_ranking_df[combined_ranking_df['大会'] == selected_league].drop(columns=['大会'])
        st.dataframe(filtered_df)
    else:
        st.error("順位表データは外部サーバーの障害により取得できませんでした。時間を置いて再度お試しください。")

elif data_type == "日程表":
    st.header(f"{selected_league} {selected_team if selected_team else ''} {current_year} 試合日程")
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
    st.header(f"{selected_league} {current_year} 順位変動グラフ")
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
