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
# ヘルパー関数: リーグ名・チーム名を正規化する
# --------------------------------------------------------------------------
def normalize_j_name(name):
    """Jリーグ名やチーム名を半角に統一する"""
    if isinstance(name, str):
        # 全角英数字を半角に、全角スペースを半角スペースに
        normalized = name.translate(str.maketrans('１２３', '123')).replace('　', ' ').strip()
        # Jリーグ名の全角を半角に
        normalized = normalized.replace('Ｊ', 'J')
        # その他の特定の全角文字（もしあれば）を半角に変換する例
        # 例: チーム名に「FC東京」や「柏レイソル」などの揺れがある場合、別途処理が必要
        return normalized
    return name

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
        
        cols_to_keep = [col for col in expected_cols if col in df.columns]
        
        if not cols_to_keep:
            logging.error("抽出できた列が一つもありません。サイトのレイアウトが大幅に変更された可能性があります。")
            st.error("日程表の列情報が想定と異なります。サイトをご確認ください。")
            return None
            
        df = df[cols_to_keep]

        # 大会名とチーム名を正規化
        if '大会' in df.columns:
            df['大会'] = df['大会'].apply(normalize_j_name)
        if 'ホーム' in df.columns:
            df['ホーム'] = df['ホーム'].apply(normalize_j_name)
        if 'アウェイ' in df.columns:
            df['アウェイ'] = df['アウェイ'].apply(normalize_j_name)

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
        logging.info("create_point_aggregate_df: 入力schedule_dfがNoneまたは空です。")
        return pd.DataFrame()

    df = schedule_df.copy()
    logging.info(f"create_point_aggregate_df: 元のschedule_dfの行数: {len(df)}")

    # スコアが「数字-数字」の形式でない行を除外 (r'' で SyntaxWarning を回避)
    # 2025年などの未開催試合では「-」のみ、または空の場合があるため、これらを弾く
    initial_rows = len(df)
    df = df[df['スコア'].str.contains(r'^\d+-\d+$', na=False)]
    logging.info(f"create_point_aggregate_df: スコアでフィルタリング後の行数: {len(df)} (除外: {initial_rows - len(df)})")

    if df.empty:
        logging.info("create_point_aggregate_df: スコア形式のデータが見つかりませんでした。")
        return pd.DataFrame()
    
    df[['得点H', '得点A']] = df['スコア'].str.split('-', expand=True).astype(int)

    # 試合日の前処理
    # '24/02/24(土)' -> '2024/02/24'
    # 2025年のサイトの日付形式に柔軟に対応するため、複数のパターンを試す
    initial_rows = len(df)
    
    # 括弧内の曜日情報を削除
    df['試合日'] = df['試合日'].str.replace(r'\(.+\)', '', regex=True)
    
    # 年が省略されている場合（例: '02/24'）に現在の年度を付与
    # 'YY/MM/DD' 形式を前提とするが、'MM/DD' の可能性も考慮
    def parse_match_date(date_str, current_year):
        if pd.isna(date_str) or not isinstance(date_str, str):
            return pd.NaT # Not a Time
        
        # 'YY/MM/DD' または 'YYYY/MM/DD' の形式を試す
        try:
            # 'YY/MM/DD' の形式をまず試す (例: '25/02/24')
            return pd.to_datetime(date_str, format='%y/%m/%d')
        except ValueError:
            try:
                # 'YYYY/MM/DD' の形式を試す (例: '2025/02/24')
                return pd.to_datetime(date_str, format='%Y/%m/%d')
            except ValueError:
                # 'MM/DD' の形式の場合、現在の年度を付与して試す (例: '02/24')
                try:
                    return pd.to_datetime(f'{current_year}/{date_str}', format='%Y/%m/%d')
                except ValueError:
                    return pd.NaT
    
    df['試合日'] = df['試合日'].apply(lambda x: parse_match_date(x, st.session_state.current_year)) # selectboxで選択されたcurrent_yearを使用
    
    # 無効な日付（NaT）の行を削除
    df.dropna(subset=['試合日'], inplace=True)
    logging.info(f"create_point_aggregate_df: 日付パース後の行数: {len(df)} (除外: {initial_rows - len(df)})")

    if df.empty:
        logging.info("create_point_aggregate_df: 日付が有効なデータが見つかりませんでした。")
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
    logging.info(f"create_point_aggregate_df: 結合後の総試合データ行数: {len(pointaggregate_df)}")

    # 試合日でソートし、累積勝点を計算
    pointaggregate_df = pointaggregate_df.sort_values(by=['試合日'], ascending=True)
    pointaggregate_df['累積勝点'] = pointaggregate_df.groupby(['チーム'])['勝点'].cumsum()
    logging.info(f"create_point_aggregate_df: 累積勝点計算後の最終行数: {len(pointaggregate_df)}")

    return pointaggregate_df


# --------------------------------------------------------------------------
# アプリケーション本体
# --------------------------------------------------------------------------
try:
    st.title('📊 Jリーグデータビューア')

    # --- サイドバーで年度を選択できるようにする ---
    with st.sidebar:
        st.header("データ年度選択")
        years = list(range(2020, pd.Timestamp.now().year + 2))
        selected_year = st.selectbox("表示する年度を選択してください:", years, index=years.index(pd.Timestamp.now().year), key='year_selector')
        # Streamlit Session State に選択された年度を保存
        st.session_state.current_year = selected_year


    # --- データの取得 ---
    # 順位表URLは、現在スクレイピングがブロックされているため、
    # 実際にはデータが取得できない可能性が高いことを考慮して構築
    ranking_urls = {
        'J1': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%91%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={st.session_state.current_year}&yearId={st.session_state.current_year}&competitionId=651&competitionSectionId=0&search=search',
        'J2': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%92%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={st.session_state.current_year}&yearId={st.session_state.current_year}&competitionId=655&competitionSectionId=0&search=search',
        'J3': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%93%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={st.session_state.current_year}&yearId={st.session_state.current_year}&competitionId=657&competitionSectionId=0&search=search'
    }
    schedule_url = f'https://data.j-league.or.jp/SFMS01/search?competition_years={st.session_state.current_year}&competition_frame_ids=1&competition_frame_ids=2&competition_frame_ids=3&tv_relay_station_name='

    ranking_dfs_raw = {league: scrape_ranking_data(url) for league, url in ranking_urls.items()}
    
    combined_ranking_df = pd.DataFrame()
    ranking_data_available = False
    
    valid_ranking_dfs = [df for df in ranking_dfs_raw.values() if df is not None]
    if valid_ranking_dfs:
        try:
            for league, df_val in ranking_dfs_raw.items(): # df_valという変数名に変更
                if df_val is not None:
                    df_val['大会'] = normalize_j_name(league) 
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
        
        data_type_options = ["日程表"] # デフォルトで日程表のみ
        if schedule_df is not None and not schedule_df.empty:
            # 日程表データがあれば、その後の集計も可能かもしれないので追加
            data_type_options.extend(["直近5試合", "順位変動グラフ"])
        
        if ranking_data_available and not combined_ranking_df.empty: 
             data_type_options.insert(0, "順位表")
        
        data_type = st.radio("表示するデータを選択してください:", data_type_options)

    # --- メイン画面の表示ロジック ---
    if data_type == "順位表":
        st.header(f"Jリーグ {st.session_state.current_year} 順位表")
        if ranking_data_available and not combined_ranking_df.empty:
            with st.sidebar:
                st.header("順位表オプション")
                league_options = combined_ranking_df['大会'].unique()
                if not list(league_options): # リーグオプションが空の場合のガード
                    st.warning("順位表データに大会情報が見つかりません。")
                    st.stop()
                selected_league = st.selectbox('表示したい大会を選択してください:', league_options, key='ranking_selectbox')
            
            filtered_df = combined_ranking_df[combined_ranking_df['大会'] == selected_league].drop(columns=['大会'])
            st.dataframe(filtered_df)
        else:
            st.error("順位表データが利用できません。")

    elif data_type == "日程表":
        st.header(f"Jリーグ {st.session_state.current_year} 試合日程")
        if schedule_df is not None and not schedule_df.empty:
            with st.sidebar:
                st.header("日程表オプション")
                
                league_options = sorted(schedule_df['大会'].unique())
                if not league_options:
                    st.warning("日程表データから大会情報を取得できませんでした。")
                    st.stop()
                
                selected_league_schedule = st.selectbox('表示したい大会を選択してください:', league_options, key='schedule_league_selectbox')
                filtered_by_league = schedule_df[schedule_df['大会'] == selected_league_schedule]
                
                all_teams_in_league = pd.concat([filtered_by_league['ホーム'], filtered_by_league['アウェイ']]).unique()
                team_options = sorted(all_teams_in_league)
                if not team_options: # チームオプションが空の場合のガード
                    st.warning(f"選択された大会 ({selected_league_schedule}) のチーム情報が見つかりません。")
                    st.stop()

                selected_team = st.selectbox('表示したいチームを選択してください:', team_options, key='schedule_team_selectbox')
            
            team_filter = (schedule_df['ホーム'] == selected_team) | (schedule_df['アウェイ'] == selected_team)
            final_filtered_df = schedule_df[(schedule_df['大会'] == selected_league_schedule) & team_filter]
            st.dataframe(final_filtered_df)
        else:
            st.error("日程表データが正常に取得できませんでした。")

    elif data_type == "直近5試合":
        st.header(f"{st.session_state.current_year} チーム別 直近5試合結果")
        pointaggregate_df = create_point_aggregate_df(schedule_df)
        if not pointaggregate_df.empty:
            with st.sidebar:
                st.header("直近5試合オプション")
                
                league_options_aggregate = sorted(pointaggregate_df['大会'].unique())
                if not league_options_aggregate:
                    st.warning("集計データから大会情報を取得できませんでした。")
                    st.stop()
                    
                selected_league_aggregate = st.selectbox('大会を選択してください:', league_options_aggregate, key='aggregate_league_selectbox')

                filtered_df_aggregate = pointaggregate_df[pointaggregate_df['大会'] == selected_league_aggregate]
                team_options_aggregate = sorted(filtered_df_aggregate['チーム'].unique())
                if not team_options_aggregate: # チームオプションが空の場合のガード
                    st.warning(f"選択された大会 ({selected_league_aggregate}) のチーム情報が見つかりません。")
                    st.stop()
                
                selected_team_aggregate = st.selectbox('チームを選択してください:', team_options_aggregate, key='aggregate_team_selectbox')
            
            team_results = pointaggregate_df[(pointaggregate_df['大会'] == selected_league_aggregate) & (pointaggregate_df['チーム'] == selected_team_aggregate)]
            recent_5_games = team_results.sort_values(by='試合日', ascending=False).head(5)
            recent_5_games = recent_5_games.sort_values(by='試合日', ascending=True)
            
            recent_5_games['試合日'] = recent_5_games['試合日'].dt.strftime('%y%m%d')
            
            st.dataframe(recent_5_games)
        else:
            st.error("日程表データがないため、直近5試合の集計ができませんでした。")

    elif data_type == "順位変動グラフ":
        st.header(f"{st.session_state.current_year} チーム別 順位変動グラフ")
        pointaggregate_df = create_point_aggregate_df(schedule_df)
        if not pointaggregate_df.empty:
            with st.sidebar:
                st.header("順位変動グラフオプション")
                
                league_options_rank = sorted(pointaggregate_df['大会'].unique())
                if not league_options_rank:
                    st.warning("集計データから大会情報を取得できませんでした。")
                    st.stop()
                    
                selected_league_rank = st.selectbox('大会を選択してください:', league_options_rank, key='rank_league_selectbox')

                filtered_df_rank = pointaggregate_df[pointaggregate_df['大会'] == selected_league_rank]
                team_options_rank = sorted(filtered_df_rank['チーム'].unique())
                if not team_options_rank: # チームオプションが空の場合のガード
                    st.warning(f"選択された大会 ({selected_league_rank}) のチーム情報が見つかりません。")
                    st.stop()
                
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
                
                ax.set_title(f'{selected_league_rank} 順位変動 ({st.session_state.current_year}年 毎週月曜日時点)')
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
