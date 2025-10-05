import streamlit as st
import pandas as pd
import logging
import requests
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.ticker as ticker
import matplotlib.dates as mdates
import re # 正規表現モジュールをインポート

# --- 日本語フォント設定 ---
try:
    plt.rcParams['axes.unicode_minus'] = False
    st.info("※日本語フォントはデプロイ環境で利用できない可能性があります。グラフの日本語が文字化けする場合はご容赦ください。")
except Exception as e:
    st.warning(f"フォント設定中に予期せぬエラーが発生しました: {e}。デフォルトフォントを使用します。")
    plt.rcParams['axes.unicode_minus'] = False

# --- ログ設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

logging.info("--- アプリケーション開始 ---")

# --------------------------------------------------------------------------
# ヘルパー関数: リーグ名を正規化する
# --------------------------------------------------------------------------
def normalize_league_name(league_name):
    """Jリーグ名を半角に統一する"""
    if isinstance(league_name, str):
        # 全角英数字を半角に、全角スペースを半角スペースに、Jリーグ名の全角を半角に
        normalized = league_name.replace('Ｊ', 'J').replace('１', '1').replace('２', '2').replace('３', '3').strip()
        return normalized
    return league_name

# --------------------------------------------------------------------------
# Webスクレイピング関数
# --------------------------------------------------------------------------
@st.cache_data(ttl=3600) # 1時間キャッシュ
def scrape_ranking_data(url):
    """
    Jリーグ公式サイトから順位表をスクレイピングする関数。
    """
    logging.info(f"scrape_ranking_data: URL {url} からスクレイピング開始。")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        dfs = pd.read_html(response.text, flavor='lxml', header=0, match='順位')
        
        if not dfs:
            logging.warning("read_htmlがテーブルを検出できませんでした。URL: %s", url)
            return None
        df = dfs[0]
        logging.info(f"順位表スクレイピング成功。DataFrameの形状: {df.shape}")
        if '備考' in df.columns:
            df = df.drop(columns=['備考'])
        
        # 順位表データにもリーグ名を正規化して追加（J1, J2, J3 など）
        # URLからリーグ名を抽出するロジックをここに挿入するか、呼び出し元で設定
        return df
    except requests.exceptions.HTTPError as errh:
        logging.error(f"HTTPエラーが発生: {errh}")
        st.error(f"順位表データ取得エラー: HTTPエラー {errh.response.status_code}")
        return None
    except requests.exceptions.ConnectionError as errc:
        logging.error(f"接続エラーが発生: {errc}")
        st.error(f"順位表データ取得エラー: 接続に失敗しました。")
        return None
    except requests.exceptions.Timeout as errt:
        logging.error(f"タイムアウトエラーが発生: {errt}")
        st.error(f"順位表データ取得エラー: タイムアウトしました。")
        return None
    except requests.exceptions.RequestException as err:
        logging.error(f"リクエストエラーが発生: {err}")
        st.error(f"順位表データ取得エラー: 不明なリクエストエラー。")
        return None
    except Exception as e:
        logging.error(f"順位表スクレイピング中に予期せぬエラーが発生: {e}", exc_info=True)
        st.error(f"順位表データ取得エラー: {e}")
        return None

@st.cache_data(ttl=3600) # 1時間キャッシュ
def scrape_schedule_data(url):
    """
    Jリーグ公式サイトから日程表をスクレイピングする関数。
    """
    logging.info(f"scrape_schedule_data: URL {url} からスクレイピング開始。")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        dfs = pd.read_html(response.text, flavor='lxml', header=0, match='試合日')
        
        if not dfs:
            logging.warning("read_htmlがテーブルを検出できませんでした。URL: %s", url)
            return None
            
        df = dfs[0]
        logging.info(f"日程表スクレイピング成功。DataFrameの形状: {df.shape}, カラム数: {len(df.columns)}")
        
        expected_cols = ['大会', '試合日', 'キックオフ', 'スタジアム', 'ホーム', 'スコア', 'アウェイ', 'テレビ中継']
        
        # サイトのレイアウト変更に対応するため、存在する列のみを抽出
        cols_to_keep = [col for col in expected_cols if col in df.columns]
        
        if not cols_to_keep: # 保持する列が一つもない場合
            logging.error("抽出できた列が一つもありません。サイトのレイアウトが大幅に変更された可能性があります。")
            st.error("日程表の列情報が想定と異なります。サイトをご確認ください。")
            return None
            
        df = df[cols_to_keep]

        # 大会名を正規化
        if '大会' in df.columns:
            df['大会'] = df['大会'].apply(normalize_league_name)

        return df
        
    except requests.exceptions.HTTPError as errh:
        logging.error(f"HTTPエラーが発生: {errh}")
        st.error(f"日程表データ取得エラー: HTTPエラー {errh.response.status_code}")
        return None
    except requests.exceptions.ConnectionError as errc:
        logging.error(f"接続エラーが発生: {errc}")
        st.error(f"日程表データ取得エラー: 接続に失敗しました。")
        return None
    except requests.exceptions.Timeout as errt:
        logging.error(f"タイムアウトエラーが発生: {errt}")
        st.error(f"日程表データ取得エラー: タイムアウトしました。")
        return None
    except requests.exceptions.RequestException as err:
        logging.error(f"リクエストエラーが発生: {err}")
        st.error(f"日程表データ取得エラー: 不明なリクエストエラー。")
        return None
    except Exception as e:
        logging.error(f"日程表スクレイピング中に予期せぬエラーが発生: {e}", exc_info=True)
        st.error(f"日程表データ取得エラー: {e}")
        return None

# --------------------------------------------------------------------------
# データ加工関数
# --------------------------------------------------------------------------
@st.cache_data(ttl=3600) # 1時間キャッシュ
def create_point_aggregate_df(schedule_df):
    """日程表データから、チームごとの試合結果を集計するDataFrameを作成"""
    if schedule_df is None or schedule_df.empty:
        return pd.DataFrame()

    df = schedule_df.copy()
    
    # スコアが「数字-数字」の形式でない行を除外 (r'' で SyntaxWarning を回避)
    df = df[df['スコア'].str.contains(r'^\d+-\d+$', na=False)]
    if df.empty:
        return pd.DataFrame()
    
    df[['得点H', '得点A']] = df['スコア'].str.split('-', expand=True).astype(int)

    # 試合日の前処理
    df['試合日'] = df['試合日'].str.replace(r'\(.+\)', '', regex=True)
    df['試合日'] = df['試合日'].apply(lambda x: '20' + x if not x.startswith('20') else x)
    df['試合日'] = pd.to_datetime(df['試合日'], format='%Y/%m/%d')
    
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
try:
    st.title('📊 Jリーグデータビューア')

    # --- サイドバーで年度を選択できるようにする ---
    with st.sidebar:
        st.header("データ年度選択")
        # 2024年をデフォルトに、過去数年と未来数年を考慮
        years = list(range(2020, pd.Timestamp.now().year + 2))
        current_year = st.selectbox("表示する年度を選択してください:", years, index=years.index(pd.Timestamp.now().year), key='year_selector')

    # --- データの取得 ---
    # 順位表URLは、現在スクレイピングがブロックされているため、
    # 実際にはデータが取得できない可能性が高いことを考慮して構築
    ranking_urls = {
        'J1': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E5%AE%89%E7%94%B0%EF%BC%AA%EF%BC%91%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={current_year}&yearId={current_year}&competitionId=651&competitionSectionId=0&search=search',
        'J2': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%92%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={current_year}&yearId={current_year}&competitionId=655&competitionSectionId=0&search=search',
        'J3': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%93%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={current_year}&yearId={current_year}&competitionId=657&competitionSectionId=0&search=search'
    }
    schedule_url = f'https://data.j-league.or.jp/SFMS01/search?competition_years={current_year}&competition_frame_ids=1&competition_frame_ids=2&competition_frame_ids=3&tv_relay_station_name='

    ranking_dfs_raw = {league: scrape_ranking_data(url) for league, url in ranking_urls.items()}
    
    # 順位表は取得できない可能性が高いため、空のDataFrameで初期化し、エラーメッセージを出す
    combined_ranking_df = pd.DataFrame()
    ranking_data_available = False
    
    valid_ranking_dfs = [df for df in ranking_dfs_raw.values() if df is not None]
    if valid_ranking_dfs:
        try:
            for league, df in ranking_dfs_raw.items():
                if df is not None:
                    # 順位表に直接「大会」カラムを追加する際に、半角で固定
                    df['大会'] = normalize_league_name(league) 
            combined_ranking_df = pd.concat(valid_ranking_dfs, ignore_index=True)
            ranking_data_available = True
        except ValueError as e:
            logging.error(f"順位表データ結合エラー: {e}", exc_info=True)
            st.error("順位表データを結合できませんでした。")
    
    if not ranking_data_available:
        st.warning("現在、Jリーグ公式サイトからの順位表データの取得に問題が発生しています。時間を置いて再度お試しください。")

    schedule_df = scrape_schedule_data(schedule_url) # 日程表データはここで取得し、内部で正規化済み

    # --- サイドバーに選択肢を配置 ---
    with st.sidebar:
        st.header("表示データ選択")
        # 順位表は基本的に利用できないため、初期表示選択肢から外す
        data_type_options = ["日程表", "直近5試合", "順位変動グラフ"]
        if ranking_data_available and not combined_ranking_df.empty: # 順位表データが取得できた場合のみ表示
             data_type_options.insert(0, "順位表")
             
        data_type = st.radio("表示するデータを選択してください:", data_type_options)

    # --- メイン画面の表示ロジック ---
    if data_type == "順位表":
        st.header(f"Jリーグ {current_year} 順位表")
        if ranking_data_available and not combined_ranking_df.empty:
            with st.sidebar:
                st.header("順位表オプション")
                # 順位表データがある場合のみ、大会選択肢を表示
                league_options = combined_ranking_df['大会'].unique()
                selected_league = st.selectbox('表示したい大会を選択してください:', league_options, key='ranking_selectbox')
            
            filtered_df = combined_ranking_df[combined_ranking_df['大会'] == selected_league].drop(columns=['大会'])
            st.dataframe(filtered_df)
        else:
            st.error("順位表データが利用できません。")

    elif data_type == "日程表":
        st.header(f"Jリーグ {current_year} 試合日程")
        if schedule_df is not None and not schedule_df.empty:
            with st.sidebar:
                st.header("日程表オプション")
                
                # 正規化された大会名を使用するため、`schedule_df` から直接取得
                league_options = sorted(schedule_df['大会'].unique())
                if not league_options:
                    st.warning("日程表データから大会情報を取得できませんでした。")
                    st.stop()
                
                selected_league_schedule = st.selectbox('表示したい大会を選択してください:', league_options, key='schedule_league_selectbox')
                filtered_by_league = schedule_df[schedule_df['大会'] == selected_league_schedule]
                
                # チーム名も正規化されていることを期待するが、ここではWebサイトの表示に合わせる
                all_teams_in_league = pd.concat([filtered_by_league['ホーム'], filtered_by_league['アウェイ']]).unique()
                team_options = sorted(all_teams_in_league)
                
                selected_team = st.selectbox('表示したいチームを選択してください:', team_options, key='schedule_team_selectbox')
            
            team_filter = (schedule_df['ホーム'] == selected_team) | (schedule_df['アウェイ'] == selected_team)
            final_filtered_df = schedule_df[(schedule_df['大会'] == selected_league_schedule) & team_filter]
            st.dataframe(final_filtered_df)
        else:
            st.error("日程表データが正常に取得できませんでした。")

    elif data_type == "直近5試合":
        st.header(f"{current_year} チーム別 直近5試合結果")
        pointaggregate_df = create_point_aggregate_df(schedule_df)
        if not pointaggregate_df.empty:
            with st.sidebar:
                st.header("直近5試合オプション")
                
                # 正規化された大会名を使用
                league_options_aggregate = sorted(pointaggregate_df['大会'].unique())
                if not league_options_aggregate:
                    st.warning("集計データから大会情報を取得できませんでした。")
                    st.stop()
                    
                selected_league_aggregate = st.selectbox('大会を選択してください:', league_options_aggregate, key='aggregate_league_selectbox')

                filtered_df_aggregate = pointaggregate_df[pointaggregate_df['大会'] == selected_league_aggregate]
                team_options_aggregate = sorted(filtered_df_aggregate['チーム'].unique())
                
                selected_team_aggregate = st.selectbox('チームを選択してください:', team_options_aggregate, key='aggregate_team_selectbox')
            
            team_results = pointaggregate_df[(pointaggregate_df['大会'] == selected_league_aggregate) & (pointaggregate_df['チーム'] == selected_team_aggregate)]
            recent_5_games = team_results.sort_values(by='試合日', ascending=False).head(5)
            recent_5_games = recent_5_games.sort_values(by='試合日', ascending=True)
            
            recent_5_games['試合日'] = recent_5_games['試合日'].dt.strftime('%y%m%d')
            
            st.dataframe(recent_5_games)
        else:
            st.error("日程表データがないため、直近5試合の集計ができませんでした。")

    elif data_type == "順位変動グラフ":
        st.header(f"{current_year} チーム別 順位変動グラフ")
        pointaggregate_df = create_point_aggregate_df(schedule_df)
        if not pointaggregate_df.empty:
            with st.sidebar:
                st.header("順位変動グラフオプション")
                
                # 正規化された大会名を使用
                league_options_rank = sorted(pointaggregate_df['大会'].unique())
                if not league_options_rank:
                    st.warning("集計データから大会情報を取得できませんでした。")
                    st.stop()
                    
                selected_league_rank = st.selectbox('大会を選択してください:', league_options_rank, key='rank_league_selectbox')

                filtered_df_rank = pointaggregate_df[pointaggregate_df['大会'] == selected_league_rank]
                team_options_rank = sorted(filtered_df_rank['チーム'].unique())
                
                selected_teams_rank = st.multiselect('チームを選択してください (複数選択可):', team_options_rank, default=team_options_rank[:1], key='rank_team_multiselect')
            
            if not selected_teams_rank:
                st.warning("表示するチームを選択してください。")
            else:
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
                
                ax.set_title(f'{selected_league_rank} 順位変動 ({current_year}年 毎週月曜日時点)')
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

except Exception as e:
    logging.critical(f"--- アプリケーションの未補足の致命的エラー: {e} ---", exc_info=True)
    st.error(f"予期せぬエラーが発生しました: {e}")
