import streamlit as st
import pandas as pd
import logging
import requests
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.ticker as ticker
import matplotlib.dates as mdates
import re

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
# 大会名マスタの定義 (修正: キーを半角Jに統一)
# --------------------------------------------------------------------------
# 大会名マスタ: normalize_j_nameでＪ->Jに変換された後の文字列をキーとして定義します。
LEAGUE_NAME_MAPPING = {
    # J1リーグ (キーはすべて半角J)
    '明治安田J1リーグ': 'J1', # <- ＪをJに修正
    '明治安田生命J1リーグ': 'J1', # <- ＪをJに修正
    '明治安田J1': 'J1',
    'J1': 'J1',
    # J2リーグ (キーはすべて半角J)
    '明治安田J2リーグ': 'J2', # <- ＪをJに修正
    '明治安田生命J2リーグ': 'J2', # <- ＪをJに修正
    '明治安田J2': 'J2',
    'J2': 'J2',
    # J3リーグ (キーはすべて半角J)
    '明治安田J3リーグ': 'J3', # <- ＪをJに修正
    '明治安田生命J3リーグ': 'J3', # <- ＪをJに修正
    '明治安田J3': 'J3',
    'J3': 'J3',
    # ルヴァンカップなどその他の大会
    'ルヴァンカップ': 'ルヴァンカップ',
    'JリーグYBCルヴァンカップ': 'ルヴァンカップ', # <- ＪをJに修正
    # その他の略称もカバー（必要に応じて追加）
}

# --------------------------------------------------------------------------
# チーム名マスタの定義と初期化
# --------------------------------------------------------------------------
# チーム名マスタ (略称や表記揺れを正式名称に統一するための辞書)
TEAM_NAME_MAPPING = {
    # J1主要チーム (略称)
    '浦和': '浦和レッズ',
    '鹿島': '鹿島アントラーズ',
    '横浜FM': '横浜F・マリノス',
    'FC東京': 'FC東京',
    'F東京': 'FC東京',
    '柏': '柏レイソル',
    '神戸': 'ヴィッセル神戸',
    'G大阪': 'ガンバ大阪',
    'C大阪': 'セレッソ大阪',
    '名古屋': '名古屋グランパス',
    '札幌': '北海道コンサドーレ札幌',
    '広島': 'サンフレッチェ広島',
    '鳥栖': 'サガン鳥栖',
    '川崎F': '川崎フロンターレ',
    '湘南': '湘南ベルマーレ',
    '新潟': 'アルビレックス新潟',
    '京都': '京都サンガF.C.',
    '磐田': 'ジュビロ磐田',
    '福岡': 'アビスパ福岡',
    '横浜C': '横浜FC',
    # J2/J3などの略称
    '東京V': '東京ヴェルディ',
    '清水': '清水エスパルス',
    '大宮': '大宮アルディージャ',
    '町田': 'FC町田ゼルビア',
    '仙台': 'ベガルタ仙台', 
}

# 既存のチーム名マスタに自己マッピングを保証
for canonical_name in list(TEAM_NAME_MAPPING.values()):
    if canonical_name not in TEAM_NAME_MAPPING:
        TEAM_NAME_MAPPING[canonical_name] = canonical_name

# --------------------------------------------------------------------------
# ヘルパー関数: リーグ名・チーム名を正規化する (LOGIC NO CHANGE, BUT MAPPING KEYS ARE FIXED)
# --------------------------------------------------------------------------
def normalize_j_name(name):
    """Jリーグ名やチーム名を半角に統一し、略称を正式名称にマッピングする"""
    if isinstance(name, str):
        # 1. 文字レベルの正規化 (全角/半角の揺れを吸収)
        # Ｊ, ＦＣ, Ｆ・Ｃ などの全角文字を半角に統一
        normalized = name.replace('Ｊ', 'J').replace('ＦＣ', 'FC').replace('Ｆ・Ｃ', 'FC')
        normalized = normalized.replace('　', ' ').strip() # 全角スペース除去
        
        # 2. 大会名マッピングを優先的に適用
        # 大会名であれば、集計・フィルタリング用のシンプルな名称に「洗い替え」
        # (LEAGUE_NAME_MAPPINGのキーがこのnormalizedの出力と一致するよう修正済み)
        if normalized in LEAGUE_NAME_MAPPING:
            return LEAGUE_NAME_MAPPING[normalized]
        
        # 3. チーム名マッピング（マスタ機能）を適用
        return TEAM_NAME_MAPPING.get(normalized, normalized)
    return name

# --------------------------------------------------------------------------
# Webスクレイピング関数 (変更なし)
# --------------------------------------------------------------------------
@st.cache_data(ttl=3600) # 1時間キャッシュ
def scrape_ranking_data(url):
    """
    Jリーグ公式サイトから順位表をスクレイピングし、**チーム名と大会名を正規化**する。
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
        
        if '備考' in df.columns:
            df = df.drop(columns=['備考'])
        
        # --- チーム名正規化の適用 (ランキング) ---
        if 'チーム' in df.columns:
            df['チーム'] = df['チーム'].apply(normalize_j_name)
        # ---------------------------------------
            
        return df
    except Exception as e:
        logging.error(f"順位表スクレイピング中に予期せぬエラーが発生: {e}", exc_info=True)
        st.error(f"順位表データ取得エラー: {e}")
        return None

@st.cache_data(ttl=3600) # 1時間キャッシュ
def scrape_schedule_data(url):
    """
    Jリーグ公式サイトから日程表をスクレイピングし、**チーム名と大会名を正規化**する。
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
        
        expected_cols = ['大会', '試合日', 'キックオフ', 'スタジアム', 'ホーム', 'スコア', 'アウェイ', 'テレビ中継']
        cols_to_keep = [col for col in expected_cols if col in df.columns]
        df = df[cols_to_keep]

        # --- 大会名、チーム名正規化の適用 (日程表) ---
        if 'ホーム' in df.columns:
            df['ホーム'] = df['ホーム'].apply(normalize_j_name)
        if 'アウェイ' in df.columns:
            df['アウェイ'] = df['アウェイ'].apply(normalize_j_name)
        if '大会' in df.columns:
            # ここで大会名が正しく J1, J2, J3 などに洗い替えられるはず
            df['大会'] = df['大会'].apply(normalize_j_name)
        # ------------------------------------

        return df
        
    except Exception as e:
        logging.error(f"日程表スクレイピング中に予期せぬエラーが発生: {e}", exc_info=True)
        st.error(f"日程表データ取得エラー: {e}")
        return None

# --------------------------------------------------------------------------
# データ加工関数 (日付パースを堅牢化)
# --------------------------------------------------------------------------
@st.cache_data(ttl=3600) # 1時間キャッシュ
def create_point_aggregate_df(schedule_df, current_year): 
    """日程表データから、チームごとの試合結果を集計するDataFrameを作成"""
    if schedule_df is None or schedule_df.empty:
        logging.info("create_point_aggregate_df: 入力schedule_dfがNoneまたは空です。")
        return pd.DataFrame()

    df = schedule_df.copy()
    
    # スコア形式でフィルタリング
    df = df[df['スコア'].str.contains(r'^\d+-\d+$', na=False)]
    
    if df.empty:
        logging.info("create_point_aggregate_df: スコア形式のデータが見つかりませんでした。")
        return pd.DataFrame()
    
    df[['得点H', '得点A']] = df['スコア'].str.split('-', expand=True).astype(int)

    # 日付のクリーニングとパース (修正: 正規表現を強化し、前後の空白や予期せぬ文字を削除)
    # 例: "10/11(金) " -> "10/11"
    df['試合日'] = df['試合日'].str.replace(r'\s*\(.+\)\s*', '', regex=True).str.strip()
    
    def parse_match_date(date_str, year):
        if pd.isna(date_str) or not isinstance(date_str, str) or not date_str:
            return pd.NaT
        try:
            # YYYY/MM/DD 形式でパースを試みる
            return pd.to_datetime(f'{year}/{date_str.strip()}', format='%Y/%m/%d', errors='coerce') 
        except ValueError:
            return pd.NaT
    
    df['試合日'] = df['試合日'].apply(lambda x: parse_match_date(x, current_year))
    df.dropna(subset=['試合日'], inplace=True) # 日付のパースに失敗した行をここで削除

    if df.empty:
        # 日付パース失敗のログを出力
        logging.info("create_point_aggregate_df: 日付が有効なデータが見つかりませんでした。")
        return pd.DataFrame()

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
# 予測用ヘルパー関数 (変更なし)
# --------------------------------------------------------------------------

def get_ranking_data_for_prediction(combined_ranking_df, league):
    """指定されたリーグの順位データを {チーム名: 順位} の辞書形式で返す"""
    if combined_ranking_df.empty: return {}
    league_df = combined_ranking_df[combined_ranking_df['大会'] == league]
    if '順位' in league_df.columns and 'チーム' in league_df.columns:
        league_df['順位'] = pd.to_numeric(league_df['順位'], errors='coerce')
        return league_df.dropna(subset=['順位']).set_index('チーム')['順位'].to_dict()
    return {}

def calculate_recent_form(pointaggregate_df, team, league):
    """直近5試合の獲得勝点を計算する (チーム名、大会名は正規化されている前提)"""
    if pointaggregate_df.empty: return 0
    
    # 選択された正規名称（例: J1）で集計DFをフィルタリング
    team_results = pointaggregate_df[
        (pointaggregate_df['大会'] == league) & 
        (pointaggregate_df['チーム'] == team)
    ]
    # 最新の5試合を取得し、勝点を合計
    recent_5_games = team_results.sort_values(by='試合日', ascending=False).head(5)
    return recent_5_games['勝点'].sum()

def predict_match_outcome(home_team, away_team, selected_league, current_year, combined_ranking_df, pointaggregate_df):
    """ルールベースで勝敗を予測する (順位差、調子、ホームアドバンテージを使用)"""
    # データの存在チェック
    if combined_ranking_df.empty or pointaggregate_df.empty:
        return "データ不足", "順位表または日程表データが取得できていないため予測できません。", "#ccc"

    # 順位データ取得
    ranking = get_ranking_data_for_prediction(combined_ranking_df, selected_league)
    
    # 順位情報がないチームがいる場合は予測不可
    if home_team not in ranking or away_team not in ranking:
         return "情報不足", "選択されたチームの順位情報がまだありません。", "#ccc"
    
    # --- パラメータ設定 (影響度) ---
    WEIGHT_RANK = 1.5   
    WEIGHT_FORM = 1.0   
    HOME_ADVANTAGE = 1.5 
    DRAW_THRESHOLD = 3  

    # --- 1. 順位スコア ---
    rank_score_H = (ranking[away_team] - ranking[home_team]) * WEIGHT_RANK
    
    # --- 2. 直近の調子スコア ---
    form_H = calculate_recent_form(pointaggregate_df, home_team, selected_league)
    form_A = calculate_recent_form(pointaggregate_df, away_team, selected_league)
    form_score_H = (form_H - form_A) * WEIGHT_FORM 
    
    # --- 3. ホームアドバンテージ ---
    home_advantage_score = HOME_ADVANTAGE
    
    # --- 総合スコア ---
    home_win_score = rank_score_H + form_score_H + home_advantage_score
    
    # --- 予測結果の判定 ---
    if home_win_score > DRAW_THRESHOLD:
        result = f"🔥 {home_team} の勝利"
        detail = f"予測優位スコア: {home_win_score:.1f}点 (順位:{rank_score_H:.1f}点 + 調子:{form_score_H:.1f}点 + Hアドバンテージ:{home_advantage_score:.1f}点)"
        color = "#ff4b4b" 
    elif home_win_score < -DRAW_THRESHOLD:
        result = f"✈️ {away_team} の勝利"
        detail = f"予測優位スコア: {home_win_score:.1f}点 (順位:{rank_score_H:.1f}点 + 調子:{form_score_H:.1f}点 + Hアドバンテージ:{home_advantage_score:.1f}点)"
        color = "#4b87ff" 
    else:
        result = "🤝 引き分け"
        detail = f"予測優位スコア: {home_win_score:.1f}点 (極めて拮抗しています)"
        color = "#ffd700" 
        
    return result, detail, color

# --------------------------------------------------------------------------
# アプリケーション本体
# --------------------------------------------------------------------------
try:
    st.title('📊 Jリーグデータビューア & 勝敗予測')

    # --- サイドバーでのデータ取得・共通コンポーネントの処理 ---
    
    with st.sidebar:
        st.header("共通設定")
        years = list(range(2020, pd.Timestamp.now().year + 2))
        current_year = st.selectbox("表示・予測する年度を選択してください:", years, index=years.index(pd.Timestamp.now().year), key='year_selector')
        st.session_state.current_year = current_year 

        # --- データの取得 (キャッシュを利用) ---
        # NOTE: ranking_urlsのキー ('J1', 'J2', 'J3') が、集計・フィルタリングの際の正規名称となる
        ranking_urls = {
            'J1': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%91%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={st.session_state.current_year}&yearId={st.session_state.current_year}&competitionId=651&competitionSectionId=0&search=search',
            'J2': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%92%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={st.session_state.current_year}&yearId={st.session_state.current_year}&competitionId=655&competitionSectionId=0&search=search',
            'J3': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%93%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={st.session_state.current_year}&yearId={st.session_state.current_year}&competitionId=657&competitionSectionId=0&search=search'
        }
        schedule_url = f'https://data.j-league.or.jp/SFMS01/search?competition_years={st.session_state.current_year}&competition_frame_ids=1&competition_frame_ids=2&competition_frame_ids=3&tv_relay_station_name='

        # 順位表データの取得と正規化
        ranking_dfs_raw = {league: scrape_ranking_data(url) for league, url in ranking_urls.items()}
        
        combined_ranking_df = pd.DataFrame()
        ranking_data_available = False
        
        valid_ranking_dfs = [df for df in ranking_dfs_raw.values() if df is not None and not df.empty]
        if valid_ranking_dfs:
            try:
                for league, df_val in ranking_dfs_raw.items():
                    if df_val is not None:
                        # ここでは手動で正規名称(J1, J2など)を設定（URLキーを使用）
                        df_val['大会'] = league
                combined_ranking_df = pd.concat(valid_ranking_dfs, ignore_index=True)
                ranking_data_available = True
            except ValueError as e:
                logging.error(f"順位表データ結合エラー: {e}", exc_info=True)
                st.error("順位表データを結合できませんでした。")
        
        if not ranking_data_available:
            st.warning("現在、順位表データが取得できていないか、データがありません。")
            st.session_state.combined_ranking_df = pd.DataFrame()
            st.session_state.ranking_data_available = False
        else:
            st.session_state.combined_ranking_df = combined_ranking_df
            st.session_state.ranking_data_available = ranking_data_available

        # 日程表データの取得と正規化
        schedule_df = scrape_schedule_data(schedule_url)
        st.session_state.schedule_df = schedule_df
        
        # 集計DFの生成 (正規化されたチーム名と大会名を使って集計)
        # 大会名と日付のパースが修正されたため、ここでデータが入るはず
        pointaggregate_df = create_point_aggregate_df(schedule_df, st.session_state.current_year)
        st.session_state.pointaggregate_df = pointaggregate_df

        # リーグオプションの生成
        league_options = []
        # ランキングデータ（J1, J2, J3）
        if 'combined_ranking_df' in st.session_state and not st.session_state.combined_ranking_df.empty:
            league_options.extend(st.session_state.combined_ranking_df['大会'].unique())
        # 日程表データ（これも正規化後のJ1, J2, J3など）
        if st.session_state.schedule_df is not None and not st.session_state.schedule_df.empty:
            schedule_league_options = st.session_state.schedule_df['大会'].unique()
            for l in schedule_league_options:
                if l not in league_options:
                    league_options.append(l)
        
        st.session_state.league_options = sorted(list(set(league_options)))


    # --- メインコンテンツをタブで分割 ---
    
    tab1, tab2 = st.tabs(["📊 データビューア", "🔮 勝敗予測ツール"])

    # ----------------------------------------------------------------------
    # タブ1: データビューア
    # ----------------------------------------------------------------------
    with tab1:
        st.header("データビューア")

        if not st.session_state.league_options:
            st.warning("大会情報が見つかりません。")
            st.stop()
            
        # サイドバーのデータビューア用選択肢
        with st.sidebar:
            st.header("データビューア設定")
            # リーグ名が正規化されているため、プルダウンには統一名称（J1, J2など）のみが表示される
            selected_league_sidebar_viewer = st.selectbox('表示したい大会を選択してください (ビューア用):', st.session_state.league_options, key='viewer_league_selectbox')

            # チーム選択プルダウン (正規化済みリストから生成されるため表記揺れは解消)
            team_options = []
            combined_ranking_df = st.session_state.combined_ranking_df
            schedule_df = st.session_state.schedule_df

            # チームリストの取得を強化（ランキングか日程表のどちらかがあればチーム名を取得）
            if not combined_ranking_df.empty and selected_league_sidebar_viewer in combined_ranking_df['大会'].unique():
                team_options.extend(combined_ranking_df[combined_ranking_df['大会'] == selected_league_sidebar_viewer]['チーム'].unique())
            
            if schedule_df is not None and not schedule_df.empty and selected_league_sidebar_viewer in schedule_df['大会'].unique():
                filtered_by_league_for_teams = schedule_df[schedule_df['大会'] == selected_league_sidebar_viewer]
                team_options.extend(pd.concat([filtered_by_league_for_teams['ホーム'], filtered_by_league_for_teams['アウェイ']]).unique())
                
            team_options = sorted(list(set(team_options)))
            
            if not team_options:
                st.warning(f"選択された大会 ({selected_league_sidebar_viewer}) のチーム情報が見つかりません。")
                # ストップせずに、チームオプションがないことを警告して処理を進めます (後続の処理でエラーハンドリングされるため)
                selected_team_sidebar_viewer = None
            else:
                selected_team_sidebar_viewer = st.selectbox('表示したいチームを選択してください (ビューア用):', team_options, key='viewer_team_selectbox')


            # 表示データ選択ラジオボタン
            st.header("表示データ選択")
            
            data_type_options = ["日程表"] 
            if not st.session_state.pointaggregate_df.empty: 
                # 集計DFが空でなくなった場合のみ、直近5試合とグラフのオプションを表示
                data_type_options.extend(["直近5試合", "順位変動グラフ"])
            if st.session_state.ranking_data_available and not st.session_state.combined_ranking_df.empty: 
                 data_type_options.insert(0, "順位表")
            
            # デフォルトで「順位表」を選択できるようにする
            default_index = data_type_options.index("順位表") if "順位表" in data_type_options else 0
            data_type = st.radio("表示するデータを選択してください:", data_type_options, index=default_index, key='viewer_data_type')

        # --- メイン画面の表示ロジック (ビューア) ---
        if data_type == "順位表":
            st.subheader(f"{selected_league_sidebar_viewer} {st.session_state.current_year} 順位表")
            if st.session_state.ranking_data_available and not st.session_state.combined_ranking_df.empty:
                filtered_df = st.session_state.combined_ranking_df[st.session_state.combined_ranking_df['大会'] == selected_league_sidebar_viewer].drop(columns=['大会'])
                st.dataframe(filtered_df)
            else:
                st.error("順位表データが利用できません。")

        elif data_type == "日程表":
            st.subheader(f"{selected_league_sidebar_viewer} {st.session_state.current_year} 試合日程 ({selected_team_sidebar_viewer if selected_team_sidebar_viewer else '全試合'})")
            schedule_df = st.session_state.schedule_df
            if schedule_df is not None and not schedule_df.empty:
                # フィルタリングに正規化済みの大会名とチーム名を使用
                league_filter = schedule_df['大会'] == selected_league_sidebar_viewer
                if selected_team_sidebar_viewer:
                    team_filter = (schedule_df['ホーム'] == selected_team_sidebar_viewer) | (schedule_df['アウェイ'] == selected_team_sidebar_viewer)
                    final_filtered_df = schedule_df[league_filter & team_filter]
                else:
                     final_filtered_df = schedule_df[league_filter]

                st.dataframe(final_filtered_df)
            else:
                st.error("日程表データが正常に取得できませんでした。")

        elif data_type == "直近5試合":
            if not selected_team_sidebar_viewer:
                 st.warning("チームを選択してください。")
            else:
                st.subheader(f"{selected_team_sidebar_viewer} 直近5試合結果")
                pointaggregate_df = st.session_state.pointaggregate_df
                if not pointaggregate_df.empty:
                    # 集計DFの大会名も正規化されているため、フィルタリングが成功するはず
                    team_results = pointaggregate_df[(pointaggregate_df['大会'] == selected_league_sidebar_viewer) & (pointaggregate_df['チーム'] == selected_team_sidebar_viewer)]
                    recent_5_games = team_results.sort_values(by='試合日', ascending=False).head(5)
                    recent_5_games = recent_5_games.sort_values(by='試合日', ascending=True)
                    
                    if recent_5_games.empty:
                        st.warning(f"大会 {selected_league_sidebar_viewer} の試合結果がまだ集計されていません。")

                    recent_5_games['試合日'] = recent_5_games['試合日'].dt.strftime('%y/%m/%d')
                    
                    recent_form_points = calculate_recent_form(pointaggregate_df, selected_team_sidebar_viewer, selected_league_sidebar_viewer)
                    st.info(f"✅ 直近5試合の合計獲得勝点: **{recent_form_points}点** (最高15点)")

                    st.dataframe(recent_5_games[['試合日', '対戦相手', '勝敗', '得点', '失点', '勝点']])
                else:
                    st.error("日程表データがないか、日付パースに失敗したため、直近5試合の集計ができませんでした。")

        elif data_type == "順位変動グラフ":
            if not selected_team_sidebar_viewer:
                 st.warning("チームを選択してください。")
            else:
                st.subheader(f"{selected_league_sidebar_viewer} 順位変動グラフ ({st.session_state.current_year}年)")
                pointaggregate_df = st.session_state.pointaggregate_df
                if not pointaggregate_df.empty:
                    all_teams_in_selected_league = pointaggregate_df[pointaggregate_df['大会'] == selected_league_sidebar_viewer]['チーム'].unique()
                    
                    selected_teams_rank_for_chart = st.multiselect(
                        'グラフ表示チームを選択してください (複数選択可):', 
                        all_teams_in_selected_league, 
                        default=[selected_team_sidebar_viewer] if selected_team_sidebar_viewer in all_teams_in_selected_league else all_teams_in_selected_league[:1], 
                        key='rank_team_multiselect_viewer'
                    )
                    
                    if not selected_teams_rank_for_chart:
                        st.warning("表示するチームを選択してください。")
                    else:
                        filtered_df_rank = pointaggregate_df[pointaggregate_df['大会'] == selected_league_sidebar_viewer]
                        min_date = filtered_df_rank['試合日'].min()
                        max_date = filtered_df_rank['試合日'].max()
                        
                        start_monday_candidate = min_date - pd.to_timedelta(min_date.weekday(), unit='D')
                        start_monday = start_monday_candidate if start_monday_candidate <= min_date else start_monday_candidate + pd.to_timedelta(7, unit='D')
                        
                        weekly_mondays = pd.date_range(start=start_monday, end=max_date + pd.to_timedelta(7, unit='D'), freq='W-MON')
                        
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
                        
                        for team in selected_teams_rank_for_chart:
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
                        
                        ax.set_title(f'{selected_league_sidebar_viewer} 順位変動 ({st.session_state.current_year}年 毎週月曜日時点)')
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


    # ----------------------------------------------------------------------
    # タブ2: 勝敗予測ツール
    # ----------------------------------------------------------------------
    with tab2:
        st.header("🔮 勝敗予測ツール")
        st.caption("※この予測は順位と直近5試合の成績に基づくシンプルなルールベースモデルであり、試合結果を保証するものではありません。")

        if not st.session_state.league_options:
            st.warning("予測に必要なデータ（大会情報）が取得できていません。年度を確認してください。")
            st.stop()

        # 予測対象の大会選択
        selected_league_predictor = st.selectbox('予測対象の大会を選択してください:', st.session_state.league_options, key='predictor_league_selectbox')

        # 予測対象のチームリストを生成 (正規化されたチーム名が入っている)
        predictor_team_options = []
        if not st.session_state.combined_ranking_df.empty and selected_league_predictor in st.session_state.combined_ranking_df['大会'].unique():
            predictor_team_options.extend(st.session_state.combined_ranking_df[st.session_state.combined_ranking_df['大会'] == selected_league_predictor]['チーム'].unique())
        
        predictor_team_options = sorted(list(set(predictor_team_options)))

        if len(predictor_team_options) < 2:
            st.warning(f"大会 **{selected_league_predictor}** のチーム情報が不足しています。予測には最低2チーム必要です。")
        else:
            col_home, col_vs, col_away = st.columns([5, 1, 5])

            with col_home:
                home_team = st.selectbox('🏠 ホームチームを選択:', predictor_team_options, index=0, key='predictor_home_team')
            
            with col_away:
                initial_away_index = 1 if len(predictor_team_options) > 1 and home_team == predictor_team_options[0] else 0
                if home_team == predictor_team_options[initial_away_index] and len(predictor_team_options) > 1:
                    initial_away_index = (initial_away_index + 1) % len(predictor_team_options)

                away_team = st.selectbox('✈️ アウェイチームを選択:', predictor_team_options, index=initial_away_index, key='predictor_away_team')

            with col_vs:
                st.text("")
                st.markdown("<h2 style='text-align: center; margin-top: 15px;'>VS</h2>", unsafe_allow_html=True)
            
            st.divider()

            if home_team == away_team:
                st.error("ホームチームとアウェイチームは異なるチームを選択してください。")
            elif st.button('試合結果を予測する', key='predict_button', use_container_width=True):
                st.subheader(f"📅 {home_team} vs {away_team} の予測結果")
                
                # 予測実行
                result, detail, color = predict_match_outcome(
                    home_team, 
                    away_team, 
                    selected_league_predictor, 
                    st.session_state.current_year, 
                    st.session_state.combined_ranking_df, 
                    st.session_state.pointaggregate_df
                )
                
                # 結果表示
                st.markdown(f"""
                <div style='border: 2px solid {color}; padding: 20px; border-radius: 10px; background-color: #f0f2f6; text-align: center;'>
                    <h1 style='color: {color}; margin-top: 0;'>{result}</h1>
                    <p style='color: #333; font-size: 1.1em;'>{detail}</p>
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown("---")

                # 予測根拠の可視化
                st.subheader("📊 予測根拠（ルールベース）")
                
                ranking = get_ranking_data_for_prediction(st.session_state.combined_ranking_df, selected_league_predictor)
                
                st.markdown(f"**1. 順位情報**")
                st.write(f"- **{home_team}** の順位: **{ranking.get(home_team, 'N/A')}位**")
                st.write(f"- **{away_team}** の順位: **{ranking.get(away_team, 'N/A')}位**")
                
                st.markdown(f"**2. 直近の調子（直近5試合の勝点）**")
                form_H = calculate_recent_form(st.session_state.pointaggregate_df, home_team, selected_league_predictor)
                form_A = calculate_recent_form(st.session_state.pointaggregate_df, away_team, selected_league_predictor)
                st.write(f"- **{home_team}** の直近5試合勝点: **{form_H}点**")
                st.write(f"- **{away_team}** の直近5試合勝点: **{form_A}点**")
                st.write(f"*(満点は15点。直近の勝点が高いほど、調子が良いと判断されます。)*")


        
except Exception as e:
    logging.critical(f"--- アプリケーションの未補足の致命的エラー: {e} ---", exc_info=True)
    st.error(f"予期せぬエラーが発生しました: {e}")
