import streamlit as st
import pandas as pd
import logging
import requests
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm # font_managerをインポート
import matplotlib.ticker as ticker # tickerをインポート
import matplotlib.dates as mdates # mdatesをインポート

# lxmlはpandas.read_htmlのflavor='lxml'で使用されるため、直接インポートは不要

# --- 日本語フォント設定 ---
# デプロイ環境ではフォント関連でエラーが発生しやすいので、
# ここではエラーでアプリが停止しないように、より慎重な設定をします。

# グローバルスコープでのフォントプロパティの初期化を避け、
# グラフ描画時に必要に応じて設定するようにします。
# 完全にコメントアウトするか、より安全な初期化方法を試みます。

# Streamlit Community Cloudの環境では、通常、特定の日本語フォントが
# インストールされていないことが多いため、汎用的なフォント設定でも
# 文字化けしたり、今回のようなエラーが発生することがあります。

# 今回のエラーは`fm.FontProperties(family='sans-serif')`自体で発生しているため、
# この初期化をグラフ描画関数内に移動するか、もっと安全な形で定義し直す必要があります。
# 一旦、この部分全体をコメントアウトして、matplotlibがデフォルトの英語フォントで
# グラフを描画することを確認しましょう。

# また、`plt.rcParams['font.family'] = 'sans-serif'` も、内部的に同様の
# Fontconfigパターン解決を試みる可能性があり、エラーの原因となるかもしれません。

# === 修正案1: フォント設定全体をコメントアウト (最も安全) ===
# デプロイ環境で日本語フォントの特定の問題を回避し、
# アプリケーションが起動することを最優先する場合。
# plt.rcParams['font.family'] = 'sans-serif' 
# plt.rcParams['axes.unicode_minus'] = False
# font_prop = fm.FontProperties(family='sans-serif')

# === 修正案2: より安全なフォント設定 (グラフ部分のみで影響) ===
# アプリケーションの起動時のエラーを回避し、グラフ描画時のみ影響を与えるようにする
# この場合は、`font_prop` の定義は一旦後回しにします。
# plt.rcParams['axes.unicode_minus'] = False # マイナス記号の表示は維持

# --- ログ設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    # デプロイ環境ではファイルへの出力は不要
    # filename='app.log', 
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

    # ... (中略：サイドバー、順位表、日程表、直近5試合の表示ロジック) ...

    elif data_type == "順位変動グラフ":
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
                # ... (順位算出ロジックは変更なし) ...
                
                fig, ax = plt.subplots(figsize=(12, 8))
                
                all_plotted_rank_data = []
                
                for team in selected_teams_rank:
                    if team in weekly_rank_df_rank.columns:
                        team_rank_data = weekly_rank_df_rank[team].dropna()
                        # ここでは `font_prop` を指定せず、デフォルトのフォントを使用
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
                
                # 日本語タイトルとラベルは、もし文字化けするようなら、一時的に英文化するか、
                # `fontproperties` 引数を削除してデフォルトフォントで表示させる。
                # ここでは `font_prop` を削除します。
                ax.set_title(f'{selected_league_rank} 順位変動 (毎週月曜日時点)') # fontproperties=font_prop を削除
                ax.set_xlabel('試合日 (毎週月曜日)') # fontproperties=font_prop を削除
                ax.set_ylabel('順位') # fontproperties=font_prop を削除
                ax.grid(True)
                
                ax.legend(title="チーム", loc='best') # prop=font_prop を削除
                
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
