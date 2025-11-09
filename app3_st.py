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
# 大会名マスタの定義
# --------------------------------------------------------------------------
LEAGUE_NAME_MAPPING = {
    '明治安田J1リーグ': 'J1',
    '明治安田生命J1リーグ': 'J1',
    '明治安田J1': 'J1',
    'J1': 'J1',
    '明治安田J2リーグ': 'J2',
    '明治安田生命J2リーグ': 'J2',
    '明治安田J2': 'J2',
    'J2': 'J2',
    '明治安田J3リーグ': 'J3',
    '明治安田生命J3リーグ': 'J3',
    '明治安田J3': 'J3',
    'J3': 'J3',
    'ルヴァンカップ': 'ルヴァンカップ',
    'JリーグYBCルヴァンカップ': 'ルヴァンカップ',
}

# --------------------------------------------------------------------------
# チーム名マスタの定義と初期化
# --------------------------------------------------------------------------
TEAM_NAME_MAPPING = {
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
    '東京V': '東京ヴェルディ',
    '清水': '清水エスパルス',
    '大宮': '大宮アルディージャ',
    '町田': 'FC町田ゼルビア',
    '仙台': 'ベガルタ仙台',
    '秋田': 'ブラウブリッツ秋田',
    '山形': 'モンテディオ山形',
    '水戸': '水戸ホーリーホック',
    '栃木': '栃木SC',
    '群馬': 'ザスパ群馬',
    '千葉': 'ジェフユナイテッド千葉',
    '甲府': 'ヴァンフォーレ甲府',
    '金沢': 'ツエーゲン金沢',
    '岡山': 'ファジアーノ岡山',
    '山口': 'レノファ山口FC',
    '徳島': '徳島ヴォルティス',
    '愛媛': '愛媛FC',
    '長崎': 'V・ファーレン長崎',
    '熊本': 'ロアッソ熊本',
    '大分': '大分トリニータ',
    '岩手': 'いわてグルージャ盛岡',
    '福島': '福島ユナイテッドFC',
    'YS横浜': 'Y.S.C.C.横浜',
    '相模原': 'SC相模原',
    '松本': '松本山雅FC',
    '富山': 'カターレ富山',
    '沼津': 'アスルクラロ沼津',
    '岐阜': 'FC岐阜',
    '鳥取': 'ガイナーレ鳥取',
    '讃岐': 'カマタマーレ讃岐',
    '今治': 'FC今治',
    '北九州': 'ギラヴァンツ北九州',
    '琉球': 'FC琉球',
    '宮崎': 'テゲバジャーロ宮崎',
    '鹿児島': '鹿児島ユナイテッドFC',
    '八戸': 'ヴァンラーレ八戸',
    '奈良': '奈良クラブ',
    '長野': 'AC長野パルセイロ',
    '高知': '高知ユナイテッドSC',
    'いわき': 'いわきFC',
    '藤枝': '藤枝MYFC',
    'ザスパクサツ群馬': 'ザスパ群馬',
    '岐阜': 'FC岐阜',
    'カマタマーレサヌキ': 'カマタマーレ讃岐',
    'Y.S.C.C.横浜': 'Y.S.C.C.横浜',
    '栃木C': '栃木シティ',
    '栃木SC': '栃木SC',
}

for canonical_name in list(TEAM_NAME_MAPPING.values()):
    if canonical_name not in TEAM_NAME_MAPPING:
        TEAM_NAME_MAPPING[canonical_name] = canonical_name

# --------------------------------------------------------------------------
# ヘルパー関数: リーグ名・チーム名を正規化する
# --------------------------------------------------------------------------
def normalize_j_name(name):
    """Jリーグ名やチーム名を半角に統一し、略称を正式名称にマッピングする (NFKC強化)"""
    if isinstance(name, str):
        normalized = unicodedata.normalize('NFKC', name)
        normalized = normalized.replace('J', 'J').replace('FC', 'FC').replace('F・C', 'FC')
        normalized = normalized.replace('　', ' ').strip()
        
        if normalized in LEAGUE_NAME_MAPPING:
            return LEAGUE_NAME_MAPPING[normalized]
        
        return TEAM_NAME_MAPPING.get(normalized, normalized)
    return name

# --------------------------------------------------------------------------
# Webスクレイピング関数
# --------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def scrape_ranking_data(url):
    """Jリーグ公式サイトから順位表をスクレイピングし、**チーム名と大会名を正規化**する。"""
    logging.info(f"scrape_ranking_data: URL {url} からスクレイピング開始。")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        dfs = pd.read_html(StringIO(response.text), flavor='lxml', header=0, match='順位')
        
        if not dfs:
            logging.warning("read_htmlがテーブルを検出できませんでした。URL: %s", url)
            return None
        df = dfs[0]
        
        if '備考' in df.columns:
            df = df.drop(columns=['備考'])
        
        if 'チーム' in df.columns:
            df.loc[:, 'チーム'] = df['チーム'].apply(normalize_j_name)
            
        return df
    except Exception as e:
        logging.error(f"順位表スクレイピング中に予期せぬエラーが発生: {e}", exc_info=True)
        st.error(f"順位表データ取得エラー: {e}")
        return None
        
@st.cache_data(ttl=3600)
def scrape_schedule_data(url):
    """日程表をスクレイピングし、**チーム名と大会名を正規化**する。"""
    logging.info(f"scrape_schedule_data: URL {url} からスクレイピング開始。")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        dfs = pd.read_html(StringIO(response.text), flavor='lxml', header=0, match='試合日')
        
        if not dfs:
            logging.warning("read_htmlがテーブルを検出できませんでした。URL: %s", url)
            return None
            
        df = dfs[0]
        
        expected_cols = ['大会', '試合日', 'キックオフ', 'スタジアム', 'ホーム', 'スコア', 'アウェイ', 'テレビ中継']
        cols_to_keep = [col for col in expected_cols if col in df.columns]
        df = df[cols_to_keep]

        if 'ホーム' in df.columns:
            df.loc[:, 'ホーム'] = df['ホーム'].apply(normalize_j_name)
        if 'アウェイ' in df.columns:
            df.loc[:, 'アウェイ'] = df['アウェイ'].apply(normalize_j_name)
        if '大会' in df.columns:
            df.loc[:, '大会'] = df['大会'].apply(normalize_j_name)

        return df
        
    except Exception as e:
        logging.error(f"日程表スクレイピング中に予期せぬエラーが発生: {e}", exc_info=True)
        st.error(f"日程表データ取得エラー: {e}")
        return None

# --------------------------------------------------------------------------
# データ加工関数
# --------------------------------------------------------------------------
def parse_match_date(date_str, year):
    """
    Jリーグの日程表文字列から、YYYY/MM/DD形式の日付オブジェクトを生成する(堅牢化)
    例: '25/02/23(日・祝)' -> datetime(2025, 2, 23)
    """
    if pd.isna(date_str) or not isinstance(date_str, str) or not date_str:
        return pd.NaT

    cleaned_date_str = re.sub(r'\(.*?\)', '', date_str).strip()
    match = re.search(r'(\d{1,2}/\d{1,2}/\d{1,2})', cleaned_date_str)
    
    if match:
        date_part = match.group(1).strip()
        parse_format = '%y/%m/%d'
        
        try:
            parsed_date = pd.to_datetime(date_part, format=parse_format, errors='coerce')
            
            if pd.isna(parsed_date) or parsed_date.year != year:
                return pd.NaT
            
            return parsed_date
        except Exception:
            return pd.NaT
    
    return pd.NaT

@st.cache_data(ttl=3600)
def create_point_aggregate_df(schedule_df, current_year):
    """日程表データから、チームごとの試合結果を集計するDataFrameを作成"""
    if schedule_df is None or schedule_df.empty:
        logging.info("create_point_aggregate_df: 入力schedule_dfがNoneまたは空です。")
        return pd.DataFrame()

    df = schedule_df.copy()
    
    df.loc[:, 'スコア_cleaned'] = df['スコア'].astype(str).str.replace('ー', '-').str.strip()
    df = df[df['スコア_cleaned'].str.contains(r'^\d+-\d+$', na=False)]
    
    if df.empty:
        logging.info("create_point_aggregate_df: スコア形式のデータが見つかりませんでした。")
        return pd.DataFrame()
    
    df[['得点H', '得点A']] = df['スコア_cleaned'].str.split('-', expand=True)
    df['得点H'] = pd.to_numeric(df['得点H'], errors='coerce').fillna(0).astype(int)
    df['得点A'] = pd.to_numeric(df['得点A'], errors='coerce').fillna(0).astype(int)

    df.loc[:, '試合日_parsed'] = df['試合日'].apply(lambda x: parse_match_date(x, current_year))
    df.dropna(subset=['試合日_parsed'], inplace=True)
    df.loc[:, '試合日'] = df['試合日_parsed']
    df = df.drop(columns=['試合日_parsed'])

    if df.empty:
        logging.info("create_point_aggregate_df: 日付が有効なデータが見つかりませんでした。")
        return pd.DataFrame()

    home_df = df.rename(columns={'ホーム': 'チーム', 'アウェイ': '相手', '得点H': '得点', '得点A': '失点'})
    home_df.loc[:, '得失差'] = home_df['得点'] - home_df['失点']
    home_df.loc[:, '勝敗'] = home_df.apply(lambda row: '勝' if row['得点'] > row['失点'] else ('分' if row['得点'] == row['失点'] else '敗'), axis=1)
    home_df.loc[:, '勝点'] = home_df.apply(lambda row: 3 if row['勝敗'] == '勝' else (1 if row['勝敗'] == '分' else 0), axis=1)
    home_df.loc[:, '対戦相手'] = home_df['相手']
    home_df = home_df[['大会', '試合日', 'チーム', '対戦相手', '勝敗', '得点', '失点', '得失差', '勝点']]

    away_df = df.rename(columns={'アウェイ': 'チーム', 'ホーム': '相手', '得点A': '得点', '得点H': '失点'})
    away_df.loc[:, '得失差'] = away_df['得点'] - away_df['失点']
    away_df.loc[:, '勝敗'] = away_df.apply(lambda row: '勝' if row['得点'] > row['失点'] else ('分' if row['得点'] == row['失点'] else '敗'), axis=1)
    away_df.loc[:, '勝点'] = away_df.apply(lambda row: 3 if row['勝敗'] == '勝' else (1 if row['勝敗'] == '分' else 0), axis=1)
    away_df.loc[:, '対戦相手'] = away_df['相手']
    away_df = away_df[['大会', '試合日', 'チーム', '対戦相手', '勝敗', '得点', '失点', '得失差', '勝点']]

    pointaggregate_df = pd.concat([home_df, away_df], ignore_index=True)
    pointaggregate_df.loc[:, '試合日'] = pd.to_datetime(pointaggregate_df['試合日'], errors='coerce')
    pointaggregate_df.dropna(subset=['試合日'], inplace=True)
    pointaggregate_df = pointaggregate_df.sort_values(by=['試合日'], ascending=True)
    
    pointaggregate_df.loc[:, '累積勝点'] = pointaggregate_df.groupby(['チーム'])['勝点'].cumsum()
    pointaggregate_df.loc[:, '累積得失点差'] = pointaggregate_df.groupby(['チーム'])['得失差'].cumsum()
    pointaggregate_df.loc[:, '累積総得点'] = pointaggregate_df.groupby(['チーム'])['得点'].cumsum()

    return pointaggregate_df


# --------------------------------------------------------------------------
# 予測用ヘルパー関数
# --------------------------------------------------------------------------
def get_ranking_data_for_prediction(combined_ranking_df, league):
    """指定されたリーグの順位データを {チーム名: 順位} の辞書形式で返す"""
    if combined_ranking_df.empty: return {}
    league_df = combined_ranking_df[combined_ranking_df['大会'] == league].copy()
    if '順位' in league_df.columns and 'チーム' in league_df.columns:
        league_df.loc[:, '順位'] = pd.to_numeric(league_df['順位'], errors='coerce')
        return league_df.dropna(subset=['順位']).set_index('チーム')['順位'].to_dict()
    return {}

def calculate_recent_form(pointaggregate_df, team, league):
    """直近5試合の獲得勝点を計算する (チーム名、大会名は正規化されている前提)"""
    if pointaggregate_df.empty: return 0
    
    team_results = pointaggregate_df[
        (pointaggregate_df['大会'] == league) &
        (pointaggregate_df['チーム'] == team)
    ]
    recent_5_games = team_results.sort_values(by='試合日', ascending=False).head(5)
    return recent_5_games['勝点'].sum()

def predict_match_outcome(home_team, away_team, selected_league, current_year, combined_ranking_df, pointaggregate_df, manual_adjustment=0.0):
    """
    ルールベースで勝敗を予測する
    
    【改修ポイント】
    ① manual_adjustment: 手動調整ウェイト (-10.0 ~ +10.0)
       正の値でホーム勝利へシフト、負の値でアウェイ勝利へシフト
    
    ② DRAW_THRESHOLD: 0.75に縮小
       総合スコアが -0.75 ~ +0.75 の範囲のみを引き分けと判定
    
    ③ 攻守バランス: 得点力と守備力の両面を評価
    """
    
    # データの存在チェック
    if combined_ranking_df.empty or pointaggregate_df.empty:
        if combined_ranking_df.empty:
            return "データ不足", "順位表データが取得できていません。", "#ccc"
        elif pointaggregate_df.empty:
            return "データ不足", "日程表の試合結果(日付とスコア)集計ができていません。データが未更新か、日付パースエラーが続いています。", "#ccc"

    ranking_df_league = combined_ranking_df[combined_ranking_df['大会'] == selected_league]

    if home_team not in ranking_df_league['チーム'].values or away_team not in ranking_df_league['チーム'].values:
        return "情報不足", "選択されたチームの順位情報がまだありません。", "#ccc"
    
    # --- パラメータ設定 (攻守バランス重視) ---
    WEIGHT_RANK = 0.80
    WEIGHT_FORM = 8.50
    WEIGHT_OFFENSE = 0.40  # 得点力の重み
    WEIGHT_DEFENSE = 0.40  # 守備力の重み
    HOME_ADVANTAGE = 1.10
    DRAW_THRESHOLD = 1.50

    # --- 1. 順位スコア ---
    ranking = get_ranking_data_for_prediction(combined_ranking_df, selected_league)
    rank_score_H = (ranking[away_team] - ranking[home_team]) * WEIGHT_RANK
    
    # --- 2. 直近の調子スコア ---
    form_H = calculate_recent_form(pointaggregate_df, home_team, selected_league)
    form_A = calculate_recent_form(pointaggregate_df, away_team, selected_league)
    form_score_H = (form_H - form_A) * WEIGHT_FORM
    
    # --- 3. 得点力スコア (NEW: 攻撃力指標) ---
    # チームの年間総得点を取得し、得点力の差をスコア化
    # Hチームの得点が多いほど、H勝利スコアが上がる
    home_goals_scored = ranking_df_league[ranking_df_league['チーム'] == home_team]['得点'].iloc[0]
    away_goals_scored = ranking_df_league[ranking_df_league['チーム'] == away_team]['得点'].iloc[0]
    offense_score_H = (home_goals_scored - away_goals_scored) * WEIGHT_OFFENSE
    
    # --- 4. 守備力スコア (守備の堅さ指標) ---
    # チームの年間総失点を取得し、守備力の差をスコア化
    # Hチームの失点が少ない(守備が良い)ほど、H勝利スコアが上がる
    home_goals_against = ranking_df_league[ranking_df_league['チーム'] == home_team]['失点'].iloc[0]
    away_goals_against = ranking_df_league[ranking_df_league['チーム'] == away_team]['失点'].iloc[0]
    defense_score_H = (away_goals_against - home_goals_against) * WEIGHT_DEFENSE
    
    # --- 5. ホームアドバンテージ ---
    home_advantage_score = HOME_ADVANTAGE
    
    # --- 6. 手動調整 ---
    # manual_adjustmentは直接、home_win_scoreに加算される
    
    # --- 総合スコア (攻守のバランスを考慮) ---
    home_win_score = rank_score_H + form_score_H + offense_score_H + defense_score_H + home_advantage_score + manual_adjustment
    
    # DEBUGの情報
    st.session_state.last_prediction_debug = {
        'rank_score_H': rank_score_H,
        'form_score_H': form_score_H,
        'offense_score_H': offense_score_H,
        'defense_score_H': defense_score_H,
        'home_advantage_score': home_advantage_score,
        'manual_adjustment': manual_adjustment,
        'home_win_score': home_win_score
    }
    
    # --- 予測結果の判定 ---
    if home_win_score > DRAW_THRESHOLD:
        result = f"🔥 {home_team} の勝利"
        detail = (
            f"予測優位スコア: {home_win_score:.2f}点 ("
            f"順位:{rank_score_H:.2f}点 + 調子:{form_score_H:.2f}点 + "
            f"得点力:{offense_score_H:.2f}点 + 守備:{defense_score_H:.2f}点 + "
            f"Hアドバンテージ:{home_advantage_score:.2f}点 + "
            f"手動調整:{manual_adjustment:.2f}点)"
        )
        color = "#ff4b4b"
    elif home_win_score < -DRAW_THRESHOLD:
        result = f"✈️ {away_team} の勝利"
        detail = (
            f"予測優位スコア: {home_win_score:.2f}点 ("
            f"順位:{rank_score_H:.2f}点 + 調子:{form_score_H:.2f}点 + "
            f"得点力:{offense_score_H:.2f}点 + 守備:{defense_score_H:.2f}点 + "
            f"Hアドバンテージ:{home_advantage_score:.2f}点 + "
            f"手動調整:{manual_adjustment:.2f}点)"
        )
        color = "#4b87ff"
    else:
        result = "🤝 引き分け"
        detail = f"予測優位スコア: {home_win_score:.2f}点 (極めて拮抗しています - 閾値±{DRAW_THRESHOLD}以内)"
        color = "#ffd700"
        
    return result, detail, color

# --------------------------------------------------------------------------
# アプリケーション本体
# --------------------------------------------------------------------------
try:
    st.title('📊 Jリーグデータビューア & 勝敗予測')

    with st.sidebar:
        st.header("共通設定")
        years = list(range(2020, pd.Timestamp.now().year + 2))
        current_year = st.selectbox("表示・予測する年度を選択してください:", years, index=years.index(pd.Timestamp.now().year), key='year_selector')
        st.session_state.current_year = current_year

        ranking_urls = {
            'J1': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%91%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={st.session_state.current_year}&yearId={st.session_state.current_year}&competitionId=651&competitionSectionId=0&search=search',
            'J2': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%92%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={st.session_state.current_year}&yearId={st.session_state.current_year}&competitionId=655&competitionSectionId=0&search=search',
            'J3': f'https://data.j-league.or.jp/SFRT01/?competitionSectionIdLabel=%E6%9C%80%E6%96%B0%E7%AF%80&competitionIdLabel=%E6%98%8E%E6%B2%BB%E7%94%B0%EF%BC%AA%EF%BC%93%E3%83%AA%E3%83%BC%E3%82%B0&yearIdLabel={st.session_state.current_year}&yearId={st.session_state.current_year}&competitionId=657&competitionSectionId=0&search=search'
        }
        schedule_url = f'https://data.j-league.or.jp/SFMS01/search?competition_years={st.session_state.current_year}&competition_frame_ids=1&competition_frame_ids=2&competition_frame_ids=3&tv_relay_station_name='

        ranking_dfs_raw = {league: scrape_ranking_data(url) for league, url in ranking_urls.items()}
        
        combined_ranking_df = pd.DataFrame()
        ranking_data_available = False
        
        valid_ranking_dfs = [df for df in ranking_dfs_raw.values() if df is not None and not df.empty]
        if valid_ranking_dfs:
            try:
                ranking_dfs_with_league = []
                for league, df_val in ranking_dfs_raw.items():
                    if df_val is not None and not df_val.empty:
                        df_val.loc[:, '大会'] = league
                        ranking_dfs_with_league.append(df_val)
                
                if ranking_dfs_with_league:
                    combined_ranking_df = pd.concat(ranking_dfs_with_league, ignore_index=True)
                    ranking_data_available = True
                else:
                    ranking_data_available = False

            except ValueError as e:
                logging.error(f"順位表データ結合エラー: {e}", exc_info=True)
                st.error("順位表データを結合できませんでした。")
            
            ranking_numeric_cols = [
                '順位', '試合', '勝', '分', '負', '得点', '失点', '得失点差', '勝点'
            ]
            
            for col in ranking_numeric_cols:
                if col in combined_ranking_df.columns:
                    combined_ranking_df[col] = pd.to_numeric(
                        combined_ranking_df[col], errors='coerce'
                    ).fillna(0).astype(int)

        if not ranking_data_available:
            st.warning("現在、順位表データが取得できていないか、データがありません。")
            st.session_state.combined_ranking_df = pd.DataFrame()
            st.session_state.ranking_data_available = False
        else:
            st.session_state.combined_ranking_df = combined_ranking_df
            st.session_state.ranking_data_available = ranking_data_available

        schedule_df = scrape_schedule_data(schedule_url)
        st.session_state.schedule_df = schedule_df
        
        pointaggregate_df = create_point_aggregate_df(schedule_df, st.session_state.current_year)
        st.session_state.pointaggregate_df = pointaggregate_df

        league_options = []
        if 'combined_ranking_df' in st.session_state and not st.session_state.combined_ranking_df.empty:
            league_options.extend(st.session_state.combined_ranking_df['大会'].unique())
        if st.session_state.schedule_df is not None and not st.session_state.schedule_df.empty:
            schedule_league_options = st.session_state.schedule_df['大会'].unique()
            for l in schedule_league_options:
                if l not in league_options:
                    league_options.append(l)
        
        st.session_state.league_options = sorted(list(set(league_options)))

    tab1, tab2 = st.tabs(["📊 データビューア", "🔮 勝敗予測ツール"])

    # ----------------------------------------------------------------------
    # タブ1: データビューア
    # ----------------------------------------------------------------------
    with tab1:
        st.header("データビューア")

        if not st.session_state.league_options:
            st.warning("大会情報が見つかりません。")

        with st.sidebar:
            st.header("データビューア設定")
            league_options_viewer = st.session_state.league_options if st.session_state.league_options else ['データなし']
            selected_league_sidebar_viewer = st.selectbox('表示したい大会を選択してください (ビューア用):', league_options_viewer, key='viewer_league_selectbox')

            team_options = []
            combined_ranking_df = st.session_state.combined_ranking_df
            schedule_df = st.session_state.schedule_df

            if not combined_ranking_df.empty and selected_league_sidebar_viewer in combined_ranking_df['大会'].unique():
                team_options.extend(combined_ranking_df[combined_ranking_df['大会'] == selected_league_sidebar_viewer]['チーム'].unique())
            
            if schedule_df is not None and not schedule_df.empty and selected_league_sidebar_viewer in schedule_df['大会'].unique():
                filtered_by_league_for_teams = schedule_df[schedule_df['大会'] == selected_league_sidebar_viewer]
                team_options.extend(pd.concat([filtered_by_league_for_teams['ホーム'], filtered_by_league_for_teams['アウェイ']]).unique())
                
            team_options = sorted(list(set(team_options)))
            
            if not team_options:
                st.warning(f"選択された大会 ({selected_league_sidebar_viewer}) のチーム情報が見つかりません。")
                selected_team_sidebar_viewer = None
            else:
                selected_team_sidebar_viewer = st.selectbox('表示したいチームを選択してください (ビューア用):', team_options, key='viewer_team_selectbox')

            st.header("表示データ選択")
            
            is_point_aggregate_available = not st.session_state.pointaggregate_df.empty
            
            data_type_options = ["日程表"]
            if is_point_aggregate_available:
                data_type_options.extend(["直近5試合", "順位変動グラフ"])
            if st.session_state.ranking_data_available and not st.session_state.combined_ranking_df.empty:
                data_type_options.insert(0, "順位表")
            
            default_index = data_type_options.index("順位表") if "順位表" in data_type_options else 0
            data_type = st.radio("表示するデータを選択してください:", data_type_options, index=default_index, key='viewer_data_type')

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
            elif not is_point_aggregate_available:
                st.error("日程表データがないか、日付・スコアパースに失敗したため、直近5試合の集計ができませんでした。")
            else:
                st.subheader(f"🏟️ {selected_team_sidebar_viewer} の直近5試合結果")
                pointaggregate_df = st.session_state.pointaggregate_df
                
                team_results = pointaggregate_df[(pointaggregate_df['大会'] == selected_league_sidebar_viewer) & (pointaggregate_df['チーム'] == selected_team_sidebar_viewer)]
                recent_5_games = team_results.sort_values(by='試合日', ascending=False).head(5).sort_values(by='試合日', ascending=True)
                
                if recent_5_games.empty:
                    st.warning(f"大会 **{selected_league_sidebar_viewer}** の **{selected_team_sidebar_viewer}** の試合結果がまだ集計されていません。")
                else:
                    recent_form_points = calculate_recent_form(pointaggregate_df, selected_team_sidebar_viewer, selected_league_sidebar_viewer)
                    
                    display_df = recent_5_games[['試合日', '対戦相手', '勝敗', '得点', '失点', '勝点']].copy()
                    
                    display_df['試合日'] = pd.to_datetime(display_df['試合日'], errors='coerce')
                    display_df.loc[:, '試合日'] = display_df['試合日'].dt.strftime('%m/%d')
                    
                    display_df.rename(columns={'得点': '自チーム得点', '失点': '失点'}, inplace=True)
                    
                    st.info(f"✅ 直近5試合の合計獲得勝点: **{recent_form_points}点** (最高15点)")
                    st.table(display_df.reset_index(drop=True))

        elif data_type == "順位変動グラフ":
            if not selected_team_sidebar_viewer:
                st.warning("チームを選択してください。")
            elif not is_point_aggregate_available:
                st.error("日程表データがないか、日付・スコアパースに失敗したため、順位変動グラフを作成できませんでした。")
            else:
                st.subheader(f"📈 {selected_league_sidebar_viewer} 順位変動グラフ ({st.session_state.current_year}年)")
                pointaggregate_df = st.session_state.pointaggregate_df
                
                filtered_df_rank = pointaggregate_df[pointaggregate_df['大会'] == selected_league_sidebar_viewer].copy()
                all_teams_in_selected_league = filtered_df_rank['チーム'].unique()
                
                selected_teams_rank_for_chart = st.multiselect(
                    'グラフ表示チームを選択してください (複数選択可):',
                    all_teams_in_selected_league,
                    default=[selected_team_sidebar_viewer] if selected_team_sidebar_viewer in all_teams_in_selected_league else all_teams_in_selected_league[:1],
                    key='rank_team_multiselect_viewer'
                )
                
                if not selected_teams_rank_for_chart:
                    st.warning("表示するチームを選択してください。")
                    st.stop()
                
                all_match_dates = filtered_df_rank['試合日'].sort_values().unique()
                all_teams = filtered_df_rank['チーム'].unique()
                
                rank_history_df = pd.DataFrame(index=all_match_dates, columns=all_teams, dtype=np.float64)

                for current_date in all_match_dates:
                    df_upto_date = filtered_df_rank[filtered_df_rank['試合日'] <= current_date]
                    
                    if df_upto_date.empty: continue
                    
                    latest_stats_upto_date = df_upto_date.groupby('チーム')[['累積勝点', '累積得失点差', '累積総得点']].max().reset_index()

                    if not latest_stats_upto_date.empty:
                        latest_stats_upto_date['Weighted_Score'] = (
                            latest_stats_upto_date['累積勝点'] * 1e9 +
                            latest_stats_upto_date['累積得失点差'] * 1e6 +
                            latest_stats_upto_date['累積総得点']
                        )
                        
                        latest_stats_upto_date['Rank'] = (
                            latest_stats_upto_date['Weighted_Score']
                            .rank(method='min', ascending=False)
                            .fillna(0)
                            .astype(int)
                        )
                        
                        for index, row in latest_stats_upto_date.iterrows():
                            rank_history_df.loc[current_date, row['チーム']] = row['Rank']

                rank_history_df = rank_history_df.ffill()
                
                fig, ax = plt.subplots(figsize=(12, 8))
                
                plotted_data_found = False
                for team in selected_teams_rank_for_chart:
                    if team in rank_history_df.columns:
                        team_rank_data = rank_history_df[team].dropna()
                        if not team_rank_data.empty:
                            ax.plot(team_rank_data.index, team_rank_data.values, marker='o', linestyle='-', label=team)
                            plotted_data_found = True

                if not plotted_data_found:
                    st.warning("選択したチームの順位データがありませんでした。")
                    st.stop()

                num_teams_in_league = len(all_teams)
                ax.set_yticks(range(1, num_teams_in_league + 1))
                ax.invert_yaxis()
                ax.set_ylim(num_teams_in_league + 1, 0)
                
                ax.set_title(f'{selected_league_sidebar_viewer} 順位変動 ({st.session_state.current_year}年 試合日時点)')
                ax.set_xlabel('試合日')
                ax.set_ylabel('順位')
                ax.grid(True, linestyle='--')
                
                ax.legend(title="チーム", loc='upper left', bbox_to_anchor=(1.05, 1))
                
                ax.xaxis.set_major_locator(mdates.DayLocator(interval=15))
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
                
                plt.xticks(rotation=45, ha='right')
                plt.tight_layout()
                
                st.pyplot(fig)
                
    # ----------------------------------------------------------------------
    # タブ2: 勝敗予測ツール
    # ----------------------------------------------------------------------
    with tab2:
        st.header("🔮 勝敗予測ツール")
        st.caption("※この予測は順位、直近の成績、得点力、守備力に基づくルールベースモデルであり、試合結果を保証するものではありません。")
        st.info("🆕 **攻守バランスモデル**: 得点力(攻撃)と守備力(守備)の両面を考慮した予測を行います。")

        league_options_predictor = st.session_state.league_options if st.session_state.league_options else ['データなし']
        selected_league_predictor = st.selectbox('予測対象の大会を選択してください:', league_options_predictor, key='predictor_league_selectbox')

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
                initial_away_index = (predictor_team_options.index(home_team) + 1) % len(predictor_team_options) if home_team in predictor_team_options else 1
                away_team = st.selectbox('✈️ アウェイチームを選択:', predictor_team_options, index=initial_away_index, key='predictor_away_team')

            with col_vs:
                st.text("")
                st.markdown("<h2 style='text-align: center; margin-top: 15px;'>VS</h2>", unsafe_allow_html=True)
            
            st.divider()
            
            st.subheader("⚙️ 手動調整機能(定性的要因の反映)")
            st.caption("キーマンの欠場、監督交代、直前の重要試合の疲労など、統計に現れない要因を手動で反映できます。")
            
            manual_adjustment = st.slider(
                "ホーム勝利への手動調整ウェイト",
                min_value=-10.0,
                max_value=10.0,
                value=0.0,
                step=0.5,
                help="正の値: ホームに有利な要因(例: アウェイ主力欠場)\n負の値: アウェイに有利な要因(例: ホーム主力欠場)"
            )
            
            if manual_adjustment != 0:
                if manual_adjustment > 0:
                    st.info(f"💡 **{home_team}** に **+{manual_adjustment:.1f}点** の優位性を付与")
                else:
                    st.info(f"💡 **{away_team}** に **+{abs(manual_adjustment):.1f}点** の優位性を付与")

            st.divider()

            if home_team == away_team:
                st.error("ホームチームとアウェイチームは異なるチームを選択してください。")
            elif st.button('試合結果を予測する', key='predict_button', use_container_width=True):
                st.subheader(f"📅 {home_team} vs {away_team} の予測結果")
                
                result, detail, color = predict_match_outcome(
                    home_team,
                    away_team,
                    selected_league_predictor,
                    st.session_state.current_year,
                    st.session_state.combined_ranking_df,
                    st.session_state.pointaggregate_df,
                    manual_adjustment=manual_adjustment
                )
                
                st.markdown(
                    f"""
                    <div style='background-color: {color}; padding: 20px; border-radius: 10px; color: black; text-align: center;'>
                        <h3 style='margin: 0; color: white;'>{result}</h3>
                    </div>
                    <p style='margin-top: 10px; text-align: center;'>{detail}</p>
                    """,
                    unsafe_allow_html=True
                )
                
                if 'last_prediction_debug' in st.session_state:
                    debug_data = st.session_state.last_prediction_debug
                    st.markdown("#### 🔍 予測スコアの内訳 (デバッグ情報)")
                    st.json({
                        "総合スコア (H勝利優位)": f"{debug_data['home_win_score']:.2f}点",
                        "順位差スコア": f"{debug_data['rank_score_H']:.2f}点",
                        "調子差スコア": f"{debug_data['form_score_H']:.2f}点",
                        "得点力差スコア (NEW)": f"{debug_data['offense_score_H']:.2f}点",
                        "守備力差スコア": f"{debug_data['defense_score_H']:.2f}点",
                        "ホームアドバンテージ": f"{debug_data['home_advantage_score']:.2f}点",
                        "手動調整": f"{debug_data['manual_adjustment']:.2f}点",
                        "DRAW閾値": "±0.75"
                    })
                    
                    st.markdown("#### 📊 攻守バランスの可視化")
                    st.caption("得点力と守備力の両面から、チームの総合的な強さを評価します。")
                    
                    col_offense, col_defense = st.columns(2)
                    with col_offense:
                        offense_indicator = "⚔️ 攻撃有利" if debug_data['offense_score_H'] > 0 else "🛡️ 守備有利" if debug_data['offense_score_H'] < 0 else "⚖️ 互角"
                        st.metric(
                            label="得点力の差",
                            value=f"{debug_data['offense_score_H']:.2f}点",
                            delta=offense_indicator
                        )
                    with col_defense:
                        defense_indicator = "🛡️ 守備有利" if debug_data['defense_score_H'] > 0 else "⚔️ 攻撃有利" if debug_data['defense_score_H'] < 0 else "⚖️ 互角"
                        st.metric(
                            label="守備力の差",
                            value=f"{debug_data['defense_score_H']:.2f}点",
                            delta=defense_indicator
                        )


except Exception as app_e:
    logging.error(f"メインアプリケーションエラー: {app_e}", exc_info=True)
    st.error(f"アプリケーションの実行中にエラーが発生しました: {app_e}")
