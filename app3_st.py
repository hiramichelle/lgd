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
# ユーザーの要望により、表示年度を2025に固定
DISPLAY_YEAR = 2025
# NOTE: 現在のJリーグ公式サイトのURL仕様に基づき、データ取得は2024年のものを使用
# 今後、2025年のデータが公開された際にここをDISPLAY_YEARに変更できます
DATA_FETCH_YEAR = 2024 


# --------------------------------------------------------------------------
# データ正規化関数
# --------------------------------------------------------------------------
def normalize_league_names(df):
    """ '大会'カラムのリーグ名を半角に統一し、データの重複を避ける """
    if df is not None and '大会' in df.columns:
        # 全角の 'Ｊ' を半角の 'J' に置換
        df['大会'] = df['大会'].astype(str).str.replace('Ｊ', 'J')
        # その他の全角数字などを半角に置換する処理も必要に応じて追加可能
        # 例: J１ -> J1, J２ -> J2, J３ -> J3
        df['大会'] = df['大会'].str.normalize('NFKC').str.upper().str.replace(' ', '')
        
        # Jリーグの主要リーグ名のみに絞り込む（不要なカップ戦などを除外）
        valid_leagues = ['J1', 'J2', 'J3', 'YBCルヴァンカップ']
        df = df[df['大会'].isin(valid_leagues) | df['大会'].str.contains('リーグ')] # 'リーグ'を含むものも許容
        
    return df

# --------------------------------------------------------------------------
# Webスクレイピング関数 (リトライ機能付き)
# --------------------------------------------------------------------------
@st.cache_data
def scrape_ranking_data(year):
    """
    Jリーグ公式サイトから順位表をスクレイピングする関数。（リトライ機能付き）
    """
    ranking_urls = {
        'J1': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E5%AE%89%E7%94%B0%EF%BC%AA%EF%BC%91%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={year}&yearId={year}&competitionId=651&competitionSectionId=0&search=search',
        'J2': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%92%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={year}&yearId={year}&competitionId=655&competitionSectionId=0&search=search',
        'J3': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%93%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={year}&yearId={year}&competitionId=657&competitionSectionId=0&search=search'
    }
    
    combined_dfs = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for league, url in ranking_urls.items():
        logging.info(f"scrape_ranking_data: {league} (URL: {url}) からスクレイピング開始。")
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(url, headers=headers, timeout=30) 
                response.raise_for_status()
                dfs = pd.read_html(response.text, flavor='lxml', header=0, match='順位') 
                
                if not dfs:
                    logging.warning(f"read_htmlがテーブルを検出できませんでした。URL: {url}")
                    continue
                
                df = dfs[0]
                if '備考' in df.columns:
                    df = df.drop(columns=['備考'])
                df['大会'] = league # 'J1', 'J2', 'J3' を大会名として追加
                combined_dfs.append(df)
                logging.info(f"{league} 順位表取得成功。")
                break # 成功したら次のリーグへ
            
            except requests.exceptions.RequestException as err:
                if attempt < MAX_RETRIES:
                    logging.warning(f"順位表リクエストエラー ({league}): {err}。リトライします ({attempt}/{MAX_RETRIES})。")
                    time.sleep(RETRY_DELAY)
                    continue
                logging.error(f"順位表リクエストエラー ({league}, 最終試行): {err}")
                
            except Exception as e:
                logging.error(f"順位表スクレイピング中に予期せぬエラー ({league}): {e}")
                break
    
    if combined_dfs:
        # データ正規化を適用
        return normalize_league_names(pd.concat(combined_dfs, ignore_index=True))
    
    return pd.DataFrame(columns=['順位', 'チーム', '勝点', '大会']) # 失敗時は空のDataFrameを返す

@st.cache_data
def scrape_schedule_data(year):
    """
    Jリーグ公式サイトから日程表をスクレイピングする関数。（リトライ機能付き）
    """
    url = f'https://data.j-league.or.jp/SFMS01/search?competition_years={year}&competition_frame_ids=1&competition_frame_ids=2&competition_frame_ids=3&tv_relay_station_name='
    logging.info(f"scrape_schedule_data: URL {url} からスクレイピング開始。")
    headers = {'User-Agent': 'Mozilla/5.0'}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # '試合日'を含むテーブルをマッチ
            dfs = pd.read_html(response.text, flavor='lxml', header=0, match='試合日') 
            
            if not dfs:
                logging.warning(f"read_htmlがテーブルを検出できませんでした。URL: {url}")
                return None
                
            df = dfs[0]
            expected_cols = ['大会', '試合日', 'キックオフ', 'スタジアム', 'ホーム', 'スコア', 'アウェイ', 'テレビ中継']
            cols_to_keep = [col for col in expected_cols if col in df.columns]
            
            if len(cols_to_keep) < 5:
                logging.error("抽出できた列数が少なすぎます。サイトのレイアウトが大幅に変更された可能性があります。")
                return None
                
            df = df[cols_to_keep]
            logging.info(f"日程表スクレイピング成功 (試行 {attempt} 回目)。")
            
            # データ正規化を適用
            return normalize_league_names(df)
            
        except requests.exceptions.RequestException as err:
            if attempt < MAX_RETRIES:
                logging.warning(f"日程表リクエストエラー: {err}。リトライします ({attempt}/{MAX_RETRIES})。")
                time.sleep(RETRY_DELAY)
                continue
            logging.error(f"日程表リクエストエラー (最終試行): {err}")
            return None
            
        except Exception as e:
            logging.error(f"日程表スクレイピング中に予期せぬエラーが発生: {e}")
            return None
            
    return None

# --------------------------------------------------------------------------
# データ加工関数 (変更なし)
# --------------------------------------------------------------------------
@st.cache_data
def create_point_aggregate_df(schedule_df):
    """日程表データから、チームごとの試合結果を集計するDataFrameを作成"""
    # 処理ロジックは変更なし
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
    df['試合日'] = df['試合日'].apply(lambda x: str(DATA_FETCH_YEAR) + '/' + x if not x.startswith(str(DATA_FETCH_YEAR)) else x) # データ取得年に合わせる
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
# データロードと前処理
# --------------------------------------------------------------------------
# データを保持するための変数
combined_ranking_df = pd.DataFrame()
schedule_df = None
pointaggregate_df = pd.DataFrame()
data_load_success = False

with st.spinner(f"Jリーグ公式サイトから**{DISPLAY_YEAR}年**の最新データ ({DATA_FETCH_YEAR}年データ) を取得・処理中です..."):
    try:
        # --- データの取得 ---
        combined_ranking_df = scrape_ranking_data(DATA_FETCH_YEAR)
        schedule_df = scrape_schedule_data(DATA_FETCH_YEAR)
        
        # --- データ加工 ---
        if schedule_df is not None and not schedule_df.empty:
            pointaggregate_df = create_point_aggregate_df(schedule_df)
            data_load_success = True
        elif not combined_ranking_df.empty:
             # ランキングデータだけでもあれば成功とする
            data_load_success = True

    except Exception as e:
        logging.critical(f"--- データの初期ロード中に致命的エラー: {e} ---", exc_info=True)
        st.error("データの取得または初期処理中にエラーが発生しました。時間を置いて再度お試しください。")
        st.stop()


# --------------------------------------------------------------------------
# アプリケーション本体
# --------------------------------------------------------------------------
st.title('📊 Jリーグデータビューア')
st.markdown(f"**表示年度:** {DISPLAY_YEAR}年 (データ取得元: {DATA_FETCH_YEAR}年)")

# --- サイドバーの定義 (統合) ---
with st.sidebar:
    
    # --- 1. データ年度選択 ---
    st.header("ステップ 1: データ年度選択")
    # ユーザー要望に基づき、表示は2025年のみ
    selected_year = st.selectbox(
        '年度を選択してください:', 
        [DISPLAY_YEAR],
        index=0,
        disabled=True # 2025年のみ固定のため無効化
    )
    
    # --- 2. 日程表オプション（大会・チーム選択） ---
    st.header("ステップ 2: 日程表オプション（大会・チーム選択）")

    if data_load_success:
        # 大会選択 (ランキングと日程表の両方から存在する大会を抽出)
        all_available_leagues = set()
        if not combined_ranking_df.empty:
            all_available_leagues.update(combined_ranking_df['大会'].unique())
        if schedule_df is not None and not schedule_df.empty:
            all_available_leagues.update(schedule_df['大会'].unique())
            
        league_options = sorted([l for l in list(all_available_leagues) if l and isinstance(l, str)])
        
        if not league_options:
            st.warning("利用可能な大会データがありません。")
            selected_league = None
        else:
            selected_league = st.selectbox(
                '表示したい大会を選択してください:', 
                league_options, 
                key='global_league_selectbox'
            )

        # チーム選択
        team_options = []
        selected_team = None
        if schedule_df is not None and selected_league:
            filtered_by_league_schedule = schedule_df[schedule_df['大会'] == selected_league]
            if not filtered_by_league_schedule.empty:
                # 大会に含まれるすべてのチーム名を取得
                all_teams_in_league = pd.concat([filtered_by_league_schedule['ホーム'], filtered_by_league_schedule['アウェイ']]).unique()
                team_options = sorted([t for t in all_teams_in_league if t and isinstance(t, str)])
            
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
            
        if not team_options and selected_league:
            st.info(f"大会 **{selected_league}** のチームデータはありません。")
    
    else:
        # データロード失敗時/未完了時の表示
        st.warning("データロードが完了していません。")
        selected_league = st.selectbox('表示したい大会を選択してください:', ['データ取得中...'], disabled=True)
        selected_team = st.selectbox('基準となるチームを選択してください:', ['チームを選択'], disabled=True)
        
    # --- 3. 表示データ選択 (ラジオボタンを最後に移動) ---
    st.header("ステップ 3: 表示データ選択")
    data_type = st.radio(
        "表示するデータを選択してください:", 
        ("順位表", "日程表", "直近5試合", "順位変動グラフ")
    )


# --- メイン画面の表示ロジック ---
if not data_load_success:
    st.error("データを表示できません。サイドバーのオプションが機能していない場合は、アプリケーションをリロードするか、時間をおいてお試しください。")
elif data_type == "順位表":
    st.header(f"{selected_league} {DISPLAY_YEAR} 順位表")
    if selected_league and not combined_ranking_df.empty:
        filtered_df = combined_ranking_df[combined_ranking_df['大会'] == selected_league].drop(columns=['大会'])
        st.dataframe(filtered_df)
    else:
        st.warning(f"大会 **{selected_league}** の順位表データは取得できませんでした。")

elif data_type == "日程表":
    st.header(f"{selected_league} {selected_team if selected_team else '全試合'} {DISPLAY_YEAR} 試合日程")
    if schedule_df is not None and selected_league and selected_team:
        team_filter = (schedule_df['ホーム'] == selected_team) | (schedule_df['アウェイ'] == selected_team)
        final_filtered_df = schedule_df[(schedule_df['大会'] == selected_league) & team_filter]
        st.dataframe(final_filtered_df)
    elif selected_league and not selected_team:
        # チームが選択されていなければ大会全体を表示
        final_filtered_df = schedule_df[schedule_df['大会'] == selected_league]
        st.dataframe(final_filtered_df)
    else:
        st.warning("日程表データが正常に取得できなかったか、大会/チームが選択されていません。")

elif data_type == "直近5試合":
    st.header(f"{selected_league} {selected_team if selected_team else ''} 直近5試合結果")
    if not pointaggregate_df.empty and selected_team and selected_league:
        team_results = pointaggregate_df[(pointaggregate_df['大会'] == selected_league) & (pointaggregate_df['チーム'] == selected_team)]
        
        if team_results.empty:
             st.info(f"チーム **{selected_team}** の試合結果データがまだありません。")
        else:
            recent_5_games = team_results.sort_values(by='試合日', ascending=False).head(5)
            recent_5_games = recent_5_games.sort_values(by='試合日', ascending=True)
            recent_5_games['試合日'] = recent_5_games['試合日'].dt.strftime('%m/%d')
            
            st.dataframe(recent_5_games[['試合日', '対戦相手', '勝敗', '得点', '失点', '勝点']])
    else:
        st.warning("日程表データがないため、直近5試合の集計ができませんでした。またはチームが選択されていません。")

elif data_type == "順位変動グラフ":
    st.header(f"{selected_league} {DISPLAY_YEAR} 順位変動グラフ")
    if not pointaggregate_df.empty and selected_league:
        
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

        if not selected_teams_rank:
            st.warning("表示するチームを選択してください。")
        else:
            # 順位算出ロジックは省略（前回のコードと同じで動作します）
            
            # --- 順位算出ロジック ---
            min_date = filtered_df_rank['試合日'].min()
            max_date = filtered_df_rank['試合日'].max()
            start_monday = min_date - pd.to_timedelta(min_date.weekday(), unit='D')
            if start_monday < min_date:
                start_monday += pd.to_timedelta(7, unit='D')
            
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
            weekly_rank_df_rank = weekly_rank_data.rank(axis=1, ascending=False, method='min')
            # --- 順位算出ロジックここまで ---

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
                ax.invert_yaxis()
                ax.set_ylim(num_teams_in_league + 1, 0)
            else:
                st.warning("選択したチームの順位データがありません。")
                st.stop()
            
            ax.set_title(f'{selected_league} 順位変動 (毎週月曜日時点)')
            ax.set_xlabel('試合日 (毎週月曜日)')
            ax.set_ylabel('順位')
            ax.grid(True)
            ax.legend(title="チーム", loc='best')
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=14))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
            
            plt.xticks(rotation=90)
            plt.tight_layout()
            
            st.pyplot(fig)
    else:
        st.warning("日程表データがないため、順位変動グラフを作成できませんでした。")
