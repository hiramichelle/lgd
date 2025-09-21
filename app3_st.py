import streamlit as st
import pandas as pd
import logging
import requests
# lxmlはpandas.read_htmlのflavor='lxml'で使用されるため、直接インポートは不要ですが、
# 依存関係としてrequirements.txtには記載が必要です。
# from lxml import html # 直接使用しないためコメントアウト

# --- 日本語フォント設定 ---
# デプロイ環境ではフォントパスが異なるため、コメントアウトを推奨します。
# もし日本語グラフをデプロイ環境で表示したい場合は、別途対策が必要です。
# 例: Streamlitのconfig.tomlでテーマ設定をするか、パッケージとしてフォントをインストールする。
# try:
#     # ローカル環境に合わせてパスを調整してください。
#     # font_path = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc' # ローカル環境用
#     # font_prop = fm.FontProperties(fname=font_path)
#     # plt.rcParams['font.family'] = font_prop.get_name()
#     # plt.rcParams['axes.unicode_minus'] = False
#     pass # フォント設定をスキップ
# except FileNotFoundError:
#     st.error("日本語フォントファイルが見つかりません。デプロイ環境ではフォントの扱いに注意が必要です。")
#     st.info("デフォルトのフォントで表示を続行します。文字化けする可能性があります。")
#     # st.stop() # デプロイを妨げないようにコメントアウト

# --- ログ設定 ---
# Streamlit Community Cloudでは、loggingの出力はアプリのログとして自動的に収集されます。
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    # デプロイ環境ではファイルに書き出すよりも標準出力/標準エラー出力にログを出すのが一般的です。
    # Streamlitはこれを自動的にキャッチします。
    # filename='app.log', # ファイルへの出力はコメントアウト
    # filemode='w'
)

logging.info("--- アプリケーション開始 ---")

# --------------------------------------------------------------------------
# Webスクレイピング関数
# --------------------------------------------------------------------------
@st.cache_data
def scrape_ranking_data(url):
    """
    Jリーグ公式サイトから順位表をスクレイピングする関数。
    """
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
        # st.errorはStreamlitのUIに表示されるため、デプロイ時にユーザーに見せるべきです。
        st.error(f"順位表データ取得エラー: {e}")
        return None

@st.cache_data
def scrape_schedule_data(url):
    """
    Jリーグ公式サイトから日程表をスクレイピングする関数。
    """
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
# アプリケーション本体
# --------------------------------------------------------------------------
try:
    st.title('📊 Jリーグデータビューア')

    # --- データの取得と結合 ---
    # !!! 2025年シーズンデータがまだ少ない場合は、以下を2024年に変更して試してください !!!
    ranking_urls = {
        'J1': 'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E5%AE%89%E7%94%B0%EF%BC%AA%EF%BC%91%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel=2025&yearId=2025&competitionId=651&competitionSectionId=0&search=search',
        'J2': 'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E5%AE%89%E7%94%B0%EF%BC%AA%EF%BC%92%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel=2025&yearId=2025&competitionId=655&competitionSectionId=0&search=search',
        'J3': 'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E5%AE%89%E7%94%B0%EF%BC%AA%EF%BC%93%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel=2025&yearId=2025&competitionId=657&competitionSectionId=0&search=search'
    }
    # !!! ここまで !!!
    ranking_dfs = {}
    for league, url in ranking_urls.items():
        ranking_dfs[league] = scrape_ranking_data(url)
        if ranking_dfs[league] is not None:
            ranking_dfs[league]['大会'] = league
    combined_ranking_df = pd.concat([df for df in ranking_dfs.values() if df is not None], ignore_index=True)

    # 日程表データ
    schedule_url = 'https://data.j-league.or.jp/SFMS01/search?competition_years=2025&competition_frame_ids=1&competition_frame_ids=2&competition_frame_ids=3&tv_relay_station_name='
    schedule_df = scrape_schedule_data(schedule_url)

    # --- サイドバーに選択肢を配置 ---
    with st.sidebar:
        st.header("表示データ選択")
        data_type = st.radio("表示するデータを選択してください:", ("順位表", "日程表"))

    # --- メイン画面の表示ロジック ---
    if data_type == "順位表":
        st.header("Jリーグ 順位表")
        if not combined_ranking_df.empty:
            with st.sidebar:
                st.header("順位表オプション")
                league_options = combined_ranking_df['大会'].unique()
                selected_league = st.selectbox(
                    'League Cathegory選択:',
                    league_options,
                    key='ranking_selectbox' 
                )
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
                selected_league_schedule = st.selectbox(
                    'League Cathegory選択:',
                    league_options,
                    key='schedule_league_selectbox'
                )
                
                filtered_by_league = schedule_df[schedule_df['大会'] == selected_league_schedule]
                all_teams_in_league = pd.concat([filtered_by_league['ホーム'], filtered_by_league['アウェイ']]).unique()
                team_options = sorted(all_teams_in_league)
                
                selected_team = st.selectbox(
                    '表示したいチームを選択してください:',
                    team_options,
                    key='schedule_team_selectbox'
                )
            
            team_filter = (schedule_df['ホーム'] == selected_team) | (schedule_df['アウェイ'] == selected_team)
            final_filtered_df = schedule_df[(schedule_df['大会'] == selected_league_schedule) & team_filter]
            
            st.dataframe(final_filtered_df)
        else:
            st.error("日程表データが正常に取得できませんでした。")

except Exception as e:
    logging.critical(f"--- アプリケーションの未補足の致命的エラー: {e} ---", exc_info=True)
    st.error(f"予期せぬエラーが発生しました: {e}")