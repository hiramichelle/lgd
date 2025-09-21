import streamlit as st
import pandas as pd
import logging
import requests
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.ticker as ticker
import matplotlib.dates as mdates

# --- 日本語フォント設定 ---
# デプロイ環境ではフォント関連でエラーが発生しやすいので、
# ここではエラーでアプリが停止しないように、より慎重な設定をします。
# 日本語は文字化けする可能性がありますが、アプリの起動を優先します。
try:
    plt.rcParams['axes.unicode_minus'] = False # マイナス記号の表示は維持
    # font_prop は、グラフ描画関数内で必要に応じて設定するか、
    # matplotlibのデフォルトフォントに任せる
    st.info("※日本語フォントはデプロイ環境で利用できない可能性があります。グラフの日本語が文字化けする場合はご容赦ください。")
except Exception as e:
    st.warning(f"フォント設定中に予期せぬエラーが発生しました: {e}。デフォルトフォントを使用します。")
    plt.rcParams['axes.unicode_minus'] = False

# --- ログ設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    # デプロイ環境ではファイルへの出力は不要、標準出力にログを出す
    # filename='app.log',
    # filemode='w'
)

logging.info("--- アプリケーション開始 ---")

# --------------------------------------------------------------------------
# Webスクレイピング関数
# --------------------------------------------------------------------------
@st.cache_data
def scrape_ranking_data(url):
    """Jリーグ公式サイトから順位表をスクレイピングする関数"""
    logging.info(f"scrape_ranking_data: URL {url} からスクレイピング開始。")
    try:
        dfs = pd.read_html(url, flavor='lxml', header=0, match='順位')
        if not dfs:
            logging.warning("read_htmlがテーブルを検出できませんでした。URL: %s", url)
            return None
        df = dfs[0]
        logging.info(f"順位表スクレイピング成功。DataFrameの形状: {df.shape}")
        if '備考' in df.columns:
            df = df.drop(columns=['備考'])
        return df
    except Exception as e:
        logging.error(f"順位表スクレイピング中にエラーが発生: {e}")
        st.error(f"順位表データ取得エラー: {e}")
        return None

@st.cache_data
def scrape_schedule_data(url):
    """Jリーグ公式サイトから日程表をスクレイピングする関数"""
    logging.info(f"scrape_schedule_data: URL {url} からスクレイピング開始。")
    try:
        dfs = pd.read_html(url, flavor='lxml', header=0, match='試合日')
        if not dfs:
            logging.warning("read_htmlがテーブルを検出できませんでした。URL: %s", url)
            return None
        df = dfs[0]
        logging.info(f"日程表スクレイピング成功。DataFrameの形状: {df.shape}, カラム数: {len(df.columns)}")
        expected_cols = ['大会', '試合日', 'キックオフ', 'スタジアム', 'ホーム', 'スコア', 'アウェイ', 'テレビ中継']
        cols_to_keep = [col for col in expected_cols if col in df.columns]
        if len(cols_to_keep) < 5:
            logging.error("抽出できた列数が少なすぎます。サイトのレイアウトが大幅に変更された可能性があります。")
            st.error("日程表の列情報が想定と異なります。サイトをご確認ください。")
            return None
        df = df[cols_to_keep]
        return df
    except Exception as e:
        logging.error(f"日程表スクレイピング中にエラーが発生: {e}")
        st.error(f"日程表データ取得エラー: {e}")
        return None

# --------------------------------------------------------------------------
# データ加工関数
# --------------------------------------------------------------------------
@st.cache_data
def create_point_aggregate_df(schedule_df):
    """日程表データから、チームごとの試合結果を集計するDataFrameを作成"""
    if schedule_df is None or schedule_df.empty:
        return pd.DataFrame()

    df = schedule_df.copy()
    
    df = df[df['スコア'].str.contains('^\d+-\d+$', na=False)]
    if df.empty:
        return pd.DataFrame()
    
    df[['得点H', '得点A']] = df['スコア'].str.split('-', expand=True).astype(int)

    df['試合日'] = df['試合日'].str.replace(r'\(.+\)', '', regex=True)
    df['試合日'] = df['試合日'].apply(lambda x: '20' + x if not x.startswith('20') else x)
    df['試合日'] = pd.to_datetime(df['試合日'], format='%Y/%m/%d')
    
    home_df = df.rename(columns={'ホーム': 'チーム', 'アウェイ': '相手', '得点H': '得点', '得点A': '失点'})
    home_df['得失差'] = home_df['得点'] - home_df['失点']
    home_df['勝敗'] = home_df.apply(lambda row: '勝' if row['得点'] > row['失点'] else ('分' if row['得点'] == row['失点'] else '敗'), axis=1)
    home_df['勝点'] = home_df.apply(lambda row: 3 if row['勝敗'] == '勝' else (1 if row['勝敗'] == '分' else 0), axis=1)
    home_df['対戦相手'] = home_df['相手']
    home_df = home_df[['大会', '試合日', 'チーム', '対戦相手', '勝敗', '得点', '失点', '得失差', '勝点']]

    away_df = df.rename(columns={'アウェイ': 'チーム', 'ホーム': '相手', '得点A': '得点', '得点H': '失点'})
    away_df['得失差'] = away_df['得点'] - away_df['失点']
    away_df['勝敗'] = away_df.apply(lambda row: '勝' if row['得点'] > row['失点'] else ('分' if row['得点'] == row['失点'] else '敗'), axis=1)
    away_df['勝点'] = away_df.apply(lambda row: 3 if row['勝敗'] == '勝' else (1 if row['勝敗'] == '分' else 0), axis=1)
    away_df['対戦相手'] = away_df['相手']
    away_df = away_df[['大会', '試合日', 'チーム', '対戦相手', '勝敗', '得点', '失点', '得失差', '勝点']]

    pointaggregate_df = pd.concat([home_df, away_df], ignore_index=True)

    pointaggregate_df = pointaggregate_df.sort_values(by=['試合日'], ascending=True)
    pointaggregate_df['累積勝点'] = pointaggregate_df.groupby(['チーム'])['勝点'].cumsum()

    return pointaggregate_df


# --------------------------------------------------------------------------
# アプリケーション本体
# --------------------------------------------------------------------------
try: # このtryブロックのインデントレベルが重要です
    st.title('📊 Jリーグデータビューア')

    # --- データの取得 ---
    current_year = 2024 # ここを2024に変更！
    ranking_urls = {
        'J1': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E5%AE%89%E7%94%B0%EF%BC%AA%EF%BC%91%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={current_year}&yearId={current_year}&competitionId=651&competitionSectionId=0&search=search',
        'J2': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E5%AE%89%E7%94%B0%EF%BC%AA%EF%BC%92%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={current_year}&yearId={current_year}&competitionId=655&competitionSectionId=0&search=search',
        'J3': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E5%AE%89%E7%94%B0%EF%BC%AA%EF%BC%93%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={current_year}&yearId={current_year}&competitionId=657&competitionSectionId=0&search=search'
    }
    schedule_url = f'https://data.j-league.or.jp/SFMS01/search?competition_years={current_year}&competition_frame_ids=1&competition_frame_ids=2&competition_frame_ids=3&tv_relay_station_name='

    ranking_dfs = {league: scrape_ranking_data(url) for league, url in ranking_urls.items()}
    for league, df in ranking_dfs.items():
        if df is not None: df['大会'] = league
    combined_ranking_df = pd.concat([df for df in ranking_dfs.values() if df is not None], ignore_index=True)

    schedule_df = scrape_schedule_data(schedule_url)

    # --- サイドバーに選択肢を配置 ---
    with st.sidebar:
        st.header("表示データ選択")
        data_type = st.radio("表示するデータを選択してください:", ("順位表", "日程表", "直近5試合", "順位変動グラフ"))

    # --- メイン画面の表示ロジック ---
    if data_type == "順位表":
        st.header("Jリーグ 順位表")
        if not combined_ranking_df.empty:
            with st.sidebar:
                st.header("順位表オプション")
                league_options = combined_ranking_df['大会'].unique()
                selected_league = st.selectbox('表示したい大会を選択してください:', league_options, key='ranking_selectbox')
            filtered_df = combined_ranking_df[combined_ranking_df['大会'] == selected_league].drop(columns=['大会'])
            st.dataframe(filtered_df)
        else:
            st.error("順位表データが正常に取得できませんでした。")

    elif data_type == "日程表":
        st.header("Jリーグ 試合日程")
        if schedule_df is not None and not schedule_df.empty:
            with st.sidebar:
                st.header("日程表オプション")
                
                league_options = sorted(schedule_df['大会'].unique())
                selected_league_schedule = st.selectbox('表示したい大会を選択してください:', league_options, key='schedule_league_selectbox')
                filtered_by_league = schedule_df[schedule_df['大会'] == selected_league_schedule]
                all_teams_in_league = pd.concat([filtered_by_league['ホーム'], filtered_by_league['アウェイ']]).unique()
                team_options = sorted(all_teams_in_league)
                selected_team = st.selectbox('表示したいチームを選択してください:', team_options, key='schedule_team_selectbox')
            
            team_filter = (schedule_df['ホーム'] == selected_team) | (schedule_df['アウェイ'] == selected_team)
            final_filtered_df = schedule_df[(schedule_df['大会'] == selected_league_schedule) & team_filter]
            st.dataframe(final_filtered_df)
        else:
            st.error("日程表データが正常に取得できませんでした。")

    elif data_type == "直近5試合":
        st.header("チーム別 直近5試合結果")
        pointaggregate_df = create_point_aggregate_df(schedule_df)
        if not pointaggregate_df.empty:
            with st.sidebar:
                st.header("直近5試合オプション")
                
                league_options_aggregate = sorted(pointaggregate_df['大会'].unique())
                selected_league_aggregate = st.selectbox('大会を選択してください:', league_options_aggregate, key='aggregate_league_selectbox')

                filtered_df_aggregate = pointaggregate_df[pointaggregate_df['大会'] == selected_league_aggregate]
                team_options_aggregate = sorted(filtered_df_aggregate['チーム'].unique())
                
                selected_team_aggregate = st.selectbox('チームを選択してください:', team_options_aggregate, key='aggregate_team_selectbox')
            
            team_results = pointaggregate_df[(pointaggregate_df['大会'] == selected_league_aggregate) & (pointaggregate_df['チーム'] == selected_team_aggregate)]
            recent_5_games = team_results.sort_values(by='試合日', ascending=False).head(5)
            recent_5_games = recent_5_games.sort_values(by='試合日', ascending=True) # 表示のために再度昇順にソート
            
            recent_5_games['試合日'] = recent_5_games['試合日'].dt.strftime('%y%m%d')
            
            st.dataframe(recent_5_games)
        else:
            st.error("日程表データがないため、直近5試合の集計ができませんでした。")

    elif data_type == "順位変動グラフ": # <= このelifが、メインのif/elifブロックに属しているはず
        st.header("チーム別 順位変動グラフ")
        pointaggregate_df = create_point_aggregate_df(schedule_df)
        if not pointaggregate_df.empty:
            with st.sidebar:
                st.header("順位変動グラフオプション")
                
                league_options_rank = sorted(pointaggregate_df['大会'].unique())
                selected_league_rank = st.selectbox('大会を選択してください:', league_options_rank, key='rank_league_selectbox')

                filtered_df_rank = pointaggregate_df[pointaggregate_df['大会'] == selected_league_rank]
                team_options_rank = sorted(filtered_df_rank['チーム'].unique())
                
                selected_teams_rank = st.multiselect('チームを選択してください (複数選択可):', team_options_rank, default=team_options_rank[:1], key='rank_team_multiselect')
            
            if not selected_teams_rank:
                st.warning("表示するチームを選択してください。")
            else:
                # --- ここから新しい順位算出ロジック ---
                min_date = filtered_df_rank['試合日'].min()
                max_date = filtered_df_rank['試合日'].max()
                
                start_monday_candidate = min_date - pd.to_timedelta(min_date.weekday(), unit='D')
                if start_monday_candidate < min_date:
                    start_monday = start_monday_candidate + pd.to_timedelta(7, unit='D')
                else:
                    start_monday = start_monday_candidate
                
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
                # --- 新しい順位算出ロジックここまで ---
                
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
                
                ax.set_title(f'{selected_league_rank} 順位変動 (毎週月曜日時点)')
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
            st.error("日程表データがないため、順位変動グラフを作成できませんでした。")

except Exception as e: # このexceptブロックのインデントレベルが、tryと同じである必要があります
    logging.critical(f"--- アプリケーションの未補足の致命的エラー: {e} ---", exc_info=True)
    st.error(f"予期せぬエラーが発生しました: {e}")
