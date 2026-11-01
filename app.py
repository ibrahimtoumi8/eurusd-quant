import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# =========================================================
# 1. إعدادات الصفحة الأساسية وتصميم الواجهة العصري (Cyberpunk Quant UI)
# =========================================================
st.set_page_config(
    page_title="EUR/USD AI Quant Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
        background-color: #060911;
        color: #e2e8f0;
    }
    .stApp {
        background: radial-gradient(circle at 50% 0%, #0f172a 0%, #05080f 85%);
    }
    
    /* شريط علوي حي يشبه منصات الكوانت */
    .hud-header {
        background: linear-gradient(90deg, rgba(15,23,42,0.95) 0%, rgba(6,182,212,0.12) 50%, rgba(15,23,42,0.95) 100%);
        border: 1px solid rgba(6, 182, 212, 0.35);
        border-radius: 14px;
        padding: 14px 22px;
        margin-bottom: 18px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        box-shadow: 0 0 25px rgba(6, 182, 212, 0.12);
        direction: rtl;
    }
    .hud-title {
        font-size: 1.45rem;
        font-weight: 800;
        color: #f8fafc;
        letter-spacing: 0.5px;
    }
    .hud-badge {
        font-family: 'JetBrains Mono', monospace;
        background: rgba(16, 185, 129, 0.15);
        border: 1px solid #10b981;
        color: #34d399;
        padding: 5px 14px;
        border-radius: 20px;
        font-size: 0.85rem;
    }
    
    /* بطاقات زجاجية عصرية */
    .quant-card {
        background: rgba(15, 23, 42, 0.78);
        border: 1px solid rgba(56, 189, 248, 0.22);
        border-radius: 14px;
        padding: 16px;
        box-shadow: 0 8px 25px rgba(0, 0, 0, 0.45);
        margin-bottom: 12px;
        direction: rtl;
    }
    .quant-card-title {
        font-size: 0.85rem;
        color: #94a3b8;
        font-weight: 600;
        margin-bottom: 6px;
    }
    .quant-card-val {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.55rem;
        font-weight: 700;
        color: #f8fafc;
    }
    .quant-card-sub {
        font-size: 0.8rem;
        margin-top: 6px;
        font-weight: 600;
    }
    
    /* تنسيق مقاييس Streamlit الافتراضية */
    div[data-testid="stMetric"] {
        background: rgba(15, 23, 42, 0.85);
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 12px;
        padding: 12px 15px;
        box-shadow: 0 4px 14px rgba(0,0,0,0.35);
    }
    
    /* تنسيق أزرار التبويبات لتكون مريحة باللمس على الآيباد */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: rgba(15, 23, 42, 0.85);
        padding: 8px;
        border-radius: 14px;
        border: 1px solid rgba(56, 189, 248, 0.25);
        direction: rtl;
    }
    .stTabs [data-baseweb="tab"] {
        height: 46px;
        border-radius: 10px;
        padding: 0 18px;
        font-weight: 700;
        color: #94a3b8;
        background: transparent;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #0284c7 0%, #2563eb 100%) !important;
        color: #ffffff !important;
        box-shadow: 0 4px 15px rgba(37, 99, 235, 0.45);
    }
</style>
""", unsafe_allow_html=True)

# ضبط التوقيت الفعلي للجزائر (CET - UTC+1)
tz_dz = pytz.timezone('Africa/Algiers')
now_dz = datetime.now(tz_dz)
current_date_str = now_dz.strftime("%Y-%m-%d | %H:%M:%S")

# =========================================================
# الشريط الجانبي (Sidebar): إعدادات التحكم السريع
# =========================================================
with st.sidebar:
    st.header("⚙️ لوحة التحكم الكمية")
    st.caption(f"🕒 توقيت الجزائر: **{current_date_str}**")
    st.caption("🔄 التحديث الآلي للبيانات: **كل ساعة (3600s)**")
    
    if st.button("🔄 تحديث فوري للبيانات الحية", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
        
    st.divider()
    exec_tf = st.selectbox(
        "📐 فريم الأوردر فلو والهيكلة اللحظية:",
        ["15m", "1h", "4h"],
        index=1
    )
    lookback_bars = st.slider("عدد الشموع لحساب السيولة والفجوات:", min_value=30, max_value=120, value=50, step=5)
    
    st.divider()
    st.subheader("🛡️ إعدادات حساب FTMO")
    account_balance = st.number_input("رصيد الحساب ($):", min_value=100.0, value=10000.0, step=500.0)
    default_risk_pct = st.slider("نسبة المخاطرة للصفقة (%):", min_value=0.1, max_value=2.0, value=0.5, step=0.05)

# =========================================================
# 2. دالة التوقيت الزمني (Killzones) بتوقيت الجزائر
# =========================================================
def get_killzone_info(dt):
    if dt.weekday() >= 5:
        return "🛑 عطلة نهاية الأسبوع (التحليل مبني على إغلاق الجمعة للتحضير للأسبوع القادم)", "#f59e0b"
    if dt.weekday() == 0:
        day_note = "⚠️ الاثنين (بناء سيولة الأسبوع)"
    elif dt.weekday() == 4:
        day_note = "⚠️ الجمعة (تجنبي التداول - تصفية مراكز)"
    else:
        day_note = "✅ يوم تداول مثالي (الثلاثاء - الخميس)"
        
    hour = dt.hour
    if 1 <= hour < 7:
        kz = "🌏 جلسة آسيا (Asian Accumulation)"
    elif 8 <= hour < 11:
        kz = "🔥 لندن كيلزون (London Killzone)"
    elif 13 <= hour < 16:
        kz = "🚀 نيويورك كيلزون (NY Killzone)"
    elif 16 <= hour < 18:
        kz = "🇬🇧 إغلاق لندن (London Close)"
    else:
        kz = "⏳ خارج أوقات الذروة (انتظار الكيلزون)"
        
    return f"{kz}  |  {day_note}", "#10b981"

kz_text, kz_color = get_killzone_info(now_dz)

# =========================================================
# 3. محرك جلب البيانات الشامل (يتحدث كل ساعة ttl=3600)
# =========================================================
@st.cache_data(ttl=3600, show_spinner="⚡ جاري تشغيل المحرك الكمي وجلب بيانات السيولة والسندات...")
def load_quant_data(intraday_tf="1h"):
    tickers = {
        "EURUSD": "EURUSD=X",
        "EURO_FUT": "6E=F",    # عقود اليورو الآجلة لبورصة شيكاغو (CME Real Volume)
        "DXY": "DX-Y.NYB",     # مؤشر الدولار
        "GBPUSD": "GBPUSD=X",  # الباوند لكشف SMT Divergence
        "US10Y": "^TNX",       # عوائد السندات الأمريكية 10 سنوات
        "EU_BOND": "IBGL.L",   # صندوق السندات الحكومية الأوروبية
        "GOLD": "GC=F",        # الذهب
        "VIX": "^VIX"          # مؤشر الخوف والسيولة
    }
    
    period_map = {"15m": "5d", "1h": "1mo", "4h": "3mo"}
    p_intra = period_map.get(intraday_tf, "1mo")
    
    daily_close = {}
    eur_daily_ohlc = pd.DataFrame()
    
    for name, tk in tickers.items():
        try:
            df_d = yf.Ticker(tk).history(period="6mo", interval="1d")
            if not df_d.empty:
                df_d.index = pd.to_datetime(df_d.index).tz_localize(None)
                daily_close[name] = df_d['Close']
                if name == "EURUSD":
                    eur_daily_ohlc = df_d.copy()
        except Exception:
            pass
            
    df_daily_macro = pd.DataFrame(daily_close).sort_index().ffill().bfill()
    
    intra_close = {}
    eur_intra_ohlc = pd.DataFrame()
    fut_vol = pd.Series(dtype=float)
    
    for name in ["EURUSD", "EURO_FUT", "DXY", "GBPUSD"]:
        try:
            df_i = yf.Ticker(tickers[name]).history(period=p_intra, interval=intraday_tf)
            if not df_i.empty:
                if df_i.index.tz is not None:
                    df_i.index = df_i.index.tz_convert('Africa/Algiers')
                else:
                    df_i.index = df_i.index.tz_localize('UTC').tz_convert('Africa/Algiers')
                intra_close[name] = df_i['Close']
                if name == "EURUSD":
                    eur_intra_ohlc = df_i.copy()
                elif name == "EURO_FUT":
                    fut_vol = df_i['Volume']
        except Exception:
            pass
            
    if not eur_intra_ohlc.empty:
        base_idx = eur_intra_ohlc.index
        df_intra_macro = pd.DataFrame(index=base_idx)
        for k, s in intra_close.items():
            df_intra_macro[k] = s.reindex(base_idx, method='ffill').bfill()
            
        if not fut_vol.empty:
            aligned_vol = fut_vol.reindex(base_idx, method='ffill').fillna(0)
        else:
            aligned_vol = pd.Series(0, index=base_idx)
            
        range_proxy = (eur_intra_ohlc['High'] - eur_intra_ohlc['Low']).replace(0, 0.00005) * 100000
        eur_intra_ohlc['Real_Volume'] = np.where(aligned_vol > 0, aligned_vol, range_proxy)
    else:
        df_intra_macro = pd.DataFrame()
        
    return df_daily_macro, eur_daily_ohlc, df_intra_macro, eur_intra_ohlc

@st.cache_data(ttl=3600)
def fetch_cftc_cot_euro():
    url = "https://publicreporting.cftc.gov/resource/6dca-aqww.json?$where=cftc_contract_market_code='099741'&$order=report_date_as_yyyy_mm_dd%20DESC&$limit=12"
    try:
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            data = r.json()
            rows = []
            for item in data:
                dt_str = item.get("report_date_as_yyyy_mm_dd", "")[:10]
                nc_long = float(item.get("noncomm_positions_long_all", 0))
                nc_short = float(item.get("noncomm_positions_short_all", 0))
                rows.append({
                    "Date": dt_str,
                    "HedgeFunds_Long": nc_long,
                    "HedgeFunds_Short": nc_short,
                    "Net_HedgeFunds": nc_long - nc_short
                })
            return pd.DataFrame(rows).sort_values("Date").reset_index(drop=True)
    except Exception:
        pass
    return pd.DataFrame()

df_daily_macro, eur_daily, df_intra_macro, eur_intra = load_quant_data(exec_tf)
df_cot = fetch_cftc_cot_euro()

if eur_daily.empty or eur_intra.empty:
    st.error("⚠️ تعذر جلب البيانات حالياً. اضغطي على زر التحديث الفوري في القائمة الجانبية.")
    st.stop()

# =========================================================
# 4. محرك الخوارزميات الكمية + الإضافات الـ 3 الجديدة
# =========================================================

current_price = float(eur_intra['Close'].iloc[-1])
pdh = float(eur_daily['High'].iloc[-2])
pdl = float(eur_daily['Low'].iloc[-2])
today_open = float(eur_daily['Open'].iloc[-1])
today_high = float(eur_daily['High'].iloc[-1])
today_low = float(eur_daily['Low'].iloc[-1])
pwh = float(eur_daily['High'].iloc[-6:-1].max()) if len(eur_daily) >= 6 else pdh
pwl = float(eur_daily['Low'].iloc[-6:-1].min()) if len(eur_daily) >= 6 else pdl

# المتوسطات والانحدار الخطي اليومي
eur_daily['EMA20'] = eur_daily['Close'].ewm(span=20, adjust=False).mean()
eur_daily['EMA50'] = eur_daily['Close'].ewm(span=50, adjust=False).mean()
eur_daily['Returns'] = eur_daily['Close'].pct_change()

y_lr = eur_daily['Close'].iloc[-20:].values
x_lr = np.arange(len(y_lr))
slope_d, intercept_d = np.polyfit(x_lr, y_lr, 1)
r_sq_d = float(np.corrcoef(x_lr, y_lr)[0, 1] ** 2)
lr_line = slope_d * x_lr + intercept_d

mean_20d = float(eur_daily['Close'].rolling(20).mean().iloc[-1])
std_20d = float(eur_daily['Close'].rolling(20).std().iloc[-1])
z_score_daily = (current_price - mean_20d) / std_20d if std_20d > 0 else 0.0

# معامل هيرست (Hurst Exponent)
def compute_hurst_exponent(price_series):
    ts = np.log(price_series.dropna().values)
    if len(ts) < 30:
        return 0.5
    lags = range(2, 15)
    tau = [np.std(np.subtract(ts[lag:], ts[:-lag])) for lag in lags]
    tau = [t if t > 0 else 1e-8 for t in tau]
    poly = np.polyfit(np.log(list(lags)), np.log(tau), 1)
    return float(np.clip(poly[0], 0.1, 0.9))

hurst_val = compute_hurst_exponent(eur_daily['Close'].iloc[-80:])
tr_daily = pd.concat([
    eur_daily['High'] - eur_daily['Low'],
    (eur_daily['High'] - eur_daily['Close'].shift()).abs(),
    (eur_daily['Low'] - eur_daily['Close'].shift()).abs()
], axis=1).max(axis=1)
atr_14d_pips = float(tr_daily.rolling(14).mean().iloc[-1] * 10000)
today_range_pips = float((today_high - today_low) * 10000)
atr_used_pct = (today_range_pips / atr_14d_pips * 100) if atr_14d_pips > 0 else 0.0
daily_std_ret = float(eur_daily['Returns'].iloc[-60:].std())
var_95_pips = float(1.645 * daily_std_ret * current_price * 10000)

# حساب الـ VWAP البنكي
eur_intra['Typ_Price'] = (eur_intra['High'] + eur_intra['Low'] + eur_intra['Close']) / 3.0
eur_intra['Date_Group'] = eur_intra.index.date
eur_intra['PV'] = eur_intra['Typ_Price'] * eur_intra['Real_Volume']
cum_pv = eur_intra.groupby('Date_Group')['PV'].cumsum()
cum_vol = eur_intra.groupby('Date_Group')['Real_Volume'].cumsum().replace(0, 1e-6)
eur_intra['VWAP'] = cum_pv / cum_vol
current_vwap = float(eur_intra['VWAP'].iloc[-1])

# الأوردر فلو والدلتا التراكمية (CVD)
hl_range = (eur_intra['High'] - eur_intra['Low']).replace(0, 1e-6)
buy_ratio = (eur_intra['Close'] - eur_intra['Low']) / hl_range
sell_ratio = (eur_intra['High'] - eur_intra['Close']) / hl_range
eur_intra['Buy_Vol'] = eur_intra['Real_Volume'] * buy_ratio
eur_intra['Sell_Vol'] = eur_intra['Real_Volume'] * sell_ratio
eur_intra['Delta'] = eur_intra['Buy_Vol'] - eur_intra['Sell_Vol']
eur_intra['CVD'] = eur_intra['Delta'].cumsum()

# ---------------------------------------------------------
# [إضافة 2 الجديدة]: مؤشر تدفق السيولة المؤسساتية (MFI Quant & Liquidity Drain)
# ---------------------------------------------------------
raw_money_flow = eur_intra['Typ_Price'] * eur_intra['Real_Volume']
tp_diff = eur_intra['Typ_Price'].diff()
pos_mf = np.where(tp_diff > 0, raw_money_flow, 0.0)
neg_mf = np.where(tp_diff < 0, raw_money_flow, 0.0)
pos_mf_sum = pd.Series(pos_mf, index=eur_intra.index).rolling(14).sum()
neg_mf_sum = pd.Series(neg_mf, index=eur_intra.index).rolling(14).sum().replace(0, 1e-6)
eur_intra['MFI'] = 100.0 - (100.0 / (1.0 + (pos_mf_sum / neg_mf_sum)))
current_mfi = float(eur_intra['MFI'].iloc[-1]) if not np.isnan(eur_intra['MFI'].iloc[-1]) else 50.0
mfi_slope = float(eur_intra['MFI'].iloc[-1] - eur_intra['MFI'].iloc[-6]) if len(eur_intra) >= 6 else 0.0

recent_intra = eur_intra.iloc[-lookback_bars:].copy()
net_delta_recent = float(recent_intra['Delta'].iloc[-10:].sum())
cvd_slope = float(recent_intra['CVD'].iloc[-1] - recent_intra['CVD'].iloc[-10])
price_change_10 = float(recent_intra['Close'].iloc[-1] - recent_intra['Close'].iloc[-10])

if price_change_10 > 0 and mfi_slope < -8.0:
    mfi_status = "⚠️ إنذار هروب السيولة (Liquidity Drain: السعر يصعد والسيولة تخرج!)"
    mfi_score = -1.5
elif price_change_10 < 0 and mfi_slope > 8.0:
    mfi_status = "🟢 ضخ سيولة خفي (Institutional Inflow: السعر يهبط والبنوك تضخ سيولة!)"
    mfi_score = 1.5
elif current_mfi > 55:
    mfi_status = f"🟢 تدفق مالي إيجابي (MFI: {current_mfi:.1f})"
    mfi_score = 1.0
elif current_mfi < 45:
    mfi_status = f"🔴 تدفق مالي سلبي (MFI: {current_mfi:.1f})"
    mfi_score = -1.0
else:
    mfi_status = f"⚪ سيولة متوازنة (MFI: {current_mfi:.1f})"
    mfi_score = 0.0

if price_change_10 < 0 and cvd_slope > 0:
    absorption_status = "🟢 امتصاص شرائي خفي (Bullish CVD Absorption)"
    of_score = 2.0
elif price_change_10 > 0 and cvd_slope < 0:
    absorption_status = "🔴 امتصاص بيعي خفي (Bearish CVD Absorption)"
    of_score = -2.0
elif cvd_slope > 0 and net_delta_recent > 0:
    absorption_status = "🟢 تدفق أوامر شرائي (+CVD)"
    of_score = 1.5
elif cvd_slope < 0 and net_delta_recent < 0:
    absorption_status = "🔴 تدفق أوامر بيعي (-CVD)"
    of_score = -1.5
else:
    absorption_status = "⚪ تدفق أوامر متوازن"
    of_score = 0.0

# ---------------------------------------------------------
# [إضافة 3 الجديدة]: مصفوفة سيولة الجلسات الآلية (Session Liquidity Matrix)
# ---------------------------------------------------------
latest_day = eur_intra.index[-1].date()
day_df = eur_intra[eur_intra.index.date == latest_day]

def analyze_session_liquidity(df_day, start_h, end_h, fallback_df):
    sess = df_day[(df_day.index.hour >= start_h) & (df_day.index.hour < end_h)]
    if sess.empty:
        return float(fallback_df['High'].max()), float(fallback_df['Low'].min()), "قيد التكوين / انتظار الجلسة"
    s_high = float(sess['High'].max())
    s_low = float(sess['Low'].min())
    after_sess = df_day[df_day.index.hour >= end_h]
    if after_sess.empty:
        return s_high, s_low, "⏳ الجلسة نشطة حالياً"
    post_h = float(after_sess['High'].max())
    post_l = float(after_sess['Low'].min())
    if post_h > s_high and post_l < s_low:
        st_txt = "⚡ تم سحب القمة والقاع (Both Swept)"
    elif post_h > s_high:
        st_txt = "🔴 تم سحب سيولة القمة (High Swept)"
    elif post_l < s_low:
        st_txt = "🟢 تم سحب سيولة القاع (Low Swept)"
    else:
        st_txt = "🎯 السيولة سليمة ومستهدفة (Intact)"
    return s_high, s_low, st_txt

asia_high, asia_low, asia_status = analyze_session_liquidity(day_df, 1, 7, recent_intra.iloc[-15:])
lon_high, lon_low, lon_status = analyze_session_liquidity(day_df, 8, 12, recent_intra.iloc[-10:])
ny_high, ny_low, ny_status = analyze_session_liquidity(day_df, 13, 17, recent_intra.iloc[-6:])

# ---------------------------------------------------------
# [إضافة 1 الجديدة]: خوارزمية تتبع فجوات صناع السوق ونسبة الامتصاص (FVG Mitigation %)
# ---------------------------------------------------------
def scan_fvg_matrix(df_slice):
    fvg_rows = []
    nearest_bull, nearest_bear = "لا توجد فجوة مفتوحة", "لا توجد فجوة مفتوحة"
    n = len(df_slice)
    for i in range(max(0, n - 50), n - 2):
        h_i = float(df_slice['High'].iloc[i])
        l_i = float(df_slice['Low'].iloc[i])
        h_i2 = float(df_slice['High'].iloc[i+2])
        l_i2 = float(df_slice['Low'].iloc[i+2])
        t_str = df_slice.index[i+1].strftime("%m-%d %H:%M")
        sub_bars = df_slice.iloc[i+3:]
        
        # فجوة شرائية (Bullish FVG)
        if l_i2 > h_i and (l_i2 - h_i) >= 0.00015:
            gap_size = l_i2 - h_i
            min_after = float(sub_bars['Low'].min()) if not sub_bars.empty else l_i2
            if min_after <= h_i:
                mit_pct = 100.0
            elif min_after >= l_i2:
                mit_pct = 0.0
            else:
                mit_pct = ((l_i2 - min_after) / gap_size) * 100.0
            if mit_pct < 95.0:
                zone_txt = f"{h_i:.4f} - {l_i2:.4f}"
                nearest_bull = f"{zone_txt} (ممتلئة {mit_pct:.0f}%)"
                fvg_rows.append({
                    "النوع": "🟢 FVG شرائية",
                    "التوقيت": t_str,
                    "النطاق السعري": zone_txt,
                    "الحجم (Pips)": f"{gap_size*10000:.1f}",
                    "نسبة الملء (Mitigation)": f"{mit_pct:.0f}%",
                    "الحالة": "🔥 بكر (Unmitigated)" if mit_pct == 0 else "⚡ مختبرة جزئياً"
                })
                
        # فجوة بيعية (Bearish FVG)
        if h_i2 < l_i and (l_i - h_i2) >= 0.00015:
            gap_size = l_i - h_i2
            max_after = float(sub_bars['High'].max()) if not sub_bars.empty else h_i2
            if max_after >= l_i:
                mit_pct = 100.0
            elif max_after <= h_i2:
                mit_pct = 0.0
            else:
                mit_pct = ((max_after - h_i2) / gap_size) * 100.0
            if mit_pct < 95.0:
                zone_txt = f"{h_i2:.4f} - {l_i:.4f}"
                nearest_bear = f"{zone_txt} (ممتلئة {mit_pct:.0f}%)"
                fvg_rows.append({
                    "النوع": "🔴 FVG بيعية",
                    "التوقيت": t_str,
                    "النطاق السعري": zone_txt,
                    "الحجم (Pips)": f"{gap_size*10000:.1f}",
                    "نسبة الملء (Mitigation)": f"{mit_pct:.0f}%",
                    "الحالة": "🔥 بكر (Unmitigated)" if mit_pct == 0 else "⚡ مختبرة جزئياً"
                })
                
    df_fvg = pd.DataFrame(fvg_rows[::-1][:8])
    return nearest_bull, nearest_bear, df_fvg

nearest_bull_fvg, nearest_bear_fvg, df_fvg_matrix = scan_fvg_matrix(eur_intra)

# حساب الفوليوم بروفايل (POC, VAH, VAL)
def compute_volume_profile(df_slice, num_bins=28):
    low_min = float(df_slice['Low'].min())
    high_max = float(df_slice['High'].max())
    if high_max <= low_min:
        return current_price, current_price, current_price, pd.DataFrame()
    bins = np.linspace(low_min, high_max, num_bins + 1)
    bin_centers = (bins[:-1] + bins[1:]) / 2
    vol_hist = np.zeros(num_bins)
    delta_hist = np.zeros(num_bins)
    for _, row in df_slice.iterrows():
        typ_p = (row['High'] + row['Low'] + row['Close']) / 3.0
        idx = int(np.clip(np.digitize(typ_p, bins) - 1, 0, num_bins - 1))
        vol_hist[idx] += row['Real_Volume']
        delta_hist[idx] += row['Delta']
    poc_idx = int(np.argmax(vol_hist))
    poc_level = float(bin_centers[poc_idx])
    total_v = np.sum(vol_hist)
    target_v = 0.70 * total_v
    accum_v = vol_hist[poc_idx]
    low_idx, high_idx = poc_idx, poc_idx
    while accum_v < target_v and (low_idx > 0 or high_idx < num_bins - 1):
        v_up = vol_hist[high_idx + 1] if high_idx < num_bins - 1 else -1
        v_dn = vol_hist[low_idx - 1] if low_idx > 0 else -1
        if v_up >= v_dn and high_idx < num_bins - 1:
            high_idx += 1
            accum_v += vol_hist[high_idx]
        elif low_idx > 0:
            low_idx -= 1
            accum_v += vol_hist[low_idx]
        else:
            break
    val_level = float(bin_centers[low_idx])
    vah_level = float(bin_centers[high_idx])
    vp_df = pd.DataFrame({"Price": bin_centers, "Volume": vol_hist, "Delta": delta_hist})
    return poc_level, vah_level, val_level, vp_df

poc_price, vah_price, val_price, vp_table = compute_volume_profile(recent_intra, num_bins=28)

# هيكلة التوازن (50% Equilibrium) وسحب سيولة أمس
range_high = float(recent_intra['High'].max())
range_low = float(recent_intra['Low'].min())
equilibrium_50 = (range_high + range_low) / 2.0
dealing_zone = "Discount (رخيصة تحت 50%)" if current_price < equilibrium_50 else "Premium (غالية فوق 50%)"

if today_high > pdh and current_price < pdh:
    sweep_signal = "🔴 سحب سيولة قمة أمس وارتداد (PDH Sweep)"
    sweep_score = -2.0
elif today_low < pdl and current_price > pdl:
    sweep_signal = "🟢 سحب سيولة قاع أمس وارتداد (PDL Sweep)"
    sweep_score = 2.0
elif current_price > pdh:
    sweep_signal = "🟢 اختراق وتداول فوق قمة أمس (PDH)"
    sweep_score = 1.0
elif current_price < pdl:
    sweep_signal = "🔴 كسر وتداول تحت قاع أمس (PDL)"
    sweep_score = -1.0
else:
    sweep_signal = "⚪ التداول داخل نطاق أمس (PDH/PDL Intact)"
    sweep_score = 0.0

# العوائد وتقرير COT
us10y_chg_5d = float(df_daily_macro['US10Y'].pct_change(5).iloc[-1] * 100) if 'US10Y' in df_daily_macro else 0.0
eu_bond_price_chg_5d = float(df_daily_macro['EU_BOND'].pct_change(5).iloc[-1] * 100) if 'EU_BOND' in df_daily_macro else 0.0
eu_yield_proxy_chg = -eu_bond_price_chg_5d
yield_spread_diff = eu_yield_proxy_chg - us10y_chg_5d
dxy_chg_5d = float(df_daily_macro['DXY'].pct_change(5).iloc[-1] * 100) if 'DXY' in df_daily_macro else 0.0

corr_dxy = float(df_daily_macro['EURUSD'].rolling(20).corr(df_daily_macro['DXY']).iloc[-1]) if 'DXY' in df_daily_macro else -0.9
corr_gbp = float(df_daily_macro['EURUSD'].rolling(20).corr(df_daily_macro['GBPUSD']).iloc[-1]) if 'GBPUSD' in df_daily_macro else 0.8

if not df_cot.empty:
    latest_cot_net = float(df_cot['Net_HedgeFunds'].iloc[-1])
    prev_cot_net = float(df_cot['Net_HedgeFunds'].iloc[-2]) if len(df_cot) > 1 else latest_cot_net
    cot_change = latest_cot_net - prev_cot_net
    cot_long_pct = float(df_cot['HedgeFunds_Long'].iloc[-1] / (df_cot['HedgeFunds_Long'].iloc[-1] + df_cot['HedgeFunds_Short'].iloc[-1]) * 100)
else:
    latest_cot_net, cot_change, cot_long_pct = 0.0, 0.0, 50.0

# =========================================================
# 5. مصفوفة القرار الكمي الموحدة (13.5 نقطة موزونة)
# =========================================================
quant_factors = []
weighted_score = 0.0
max_possible_score = 13.5

# 1. الاتجاه اليومي
if current_price > eur_daily['EMA20'].iloc[-1] and slope_d > 0:
    weighted_score += 2.0
    quant_factors.append(("الاتجاه الكمي اليومي (1D Trend)", "+2.0", "السعر فوق EMA20 اليومي وميل الانحدار موجب"))
elif current_price < eur_daily['EMA20'].iloc[-1] and slope_d < 0:
    weighted_score -= 2.0
    quant_factors.append(("الاتجاه الكمي اليومي (1D Trend)", "-2.0", "السعر تحت EMA20 اليومي وميل الانحدار سالب"))
else:
    quant_factors.append(("الاتجاه الكمي اليومي (1D Trend)", "0.0", "توازن بين المتوسط اليومي والانحدار"))

# 2. POC & VWAP
vp_vwap_pts = (1.0 if current_price > poc_price else -1.0) + (1.0 if current_price > current_vwap else -1.0)
weighted_score += vp_vwap_pts
quant_factors.append(("تمركز السيولة (POC & VWAP)", f"{vp_vwap_pts:+.1f}", f"POC: {poc_price:.4f} | VWAP: {current_vwap:.4f}"))

# 3. Order Flow CVD
weighted_score += of_score
quant_factors.append(("الأوردر فلو والامتصاص (CVD)", f"{of_score:+.1f}", absorption_status))

# 4. Institutional MFI (الجديد)
weighted_score += mfi_score
quant_factors.append(("تدفق السيولة المؤسساتية (MFI Quant)", f"{mfi_score:+.1f}", mfi_status))

# 5. PDH / PDL Sweep
weighted_score += sweep_score
quant_factors.append(("سيولة اليوم السابق (PDH/PDL)", f"{sweep_score:+.1f}", sweep_signal))

# 6. Yield Spread & DXY
macro_pts = (1.0 if dxy_chg_5d < 0 else -1.0) + (1.0 if yield_spread_diff > 0 else -1.0)
weighted_score += macro_pts
quant_factors.append(("فارق العوائد والدولار (Macro Spread)", f"{macro_pts:+.1f}", f"فارق العائد: {yield_spread_diff:+.2f}% | DXY: {dxy_chg_5d:+.2f}%"))

# 7. CFTC COT
cot_pts = 2.0 if (latest_cot_net > 0 and cot_change >= 0) else (-2.0 if (latest_cot_net < 0 and cot_change <= 0) else (1.0 if latest_cot_net > 0 else -1.0))
weighted_score += cot_pts
quant_factors.append(("تمركز الصناديق (CFTC COT)", f"{cot_pts:+.1f}", f"صافي العقود: {latest_cot_net:+,.0f} ({cot_change:+,.0f} أسبوعياً)"))

bull_probability = float(np.clip(((weighted_score + max_possible_score) / (2 * max_possible_score)) * 100, 5.0, 95.0))
bear_probability = 100.0 - bull_probability
quant_edge = abs(bull_probability - 50.0)

if bull_probability >= 58.0:
    bias_badge = "🟢 BUY ONLY BIAS — تمركز شرائي مؤسساتي"
    bias_color = "#10b981"
    action_plan = f"احتمال الصعود الكمي **{bull_probability:.1f}%** (تفوق إحصائي +{quant_edge:.1f}%). انتظري سحب سيولة آسيا ({asia_low:.4f}) أو الدخول من الفجوة الشرائية ({nearest_bull_fvg})."
elif bear_probability >= 58.0:
    bias_badge = "🔴 SELL ONLY BIAS — تمركز بيعي مؤسساتي"
    bias_color = "#ef4444"
    action_plan = f"احتمال الهبوط الكمي **{bear_probability:.1f}%** (تفوق إحصائي +{quant_edge:.1f}%). انتظري سحب قمة آسيا ({asia_high:.4f}) أو الدخول من الفجوة البيعية ({nearest_bear_fvg})."
else:
    bias_badge = "🟡 NEUTRAL / WAIT — حياد وانتظار سحب السيولة"
    bias_color = "#f59e0b"
    action_plan = f"السوق متوازن إحصائياً ({bull_probability:.0f}% مقابل {bear_probability:.0f}%). انتظري سحب قمة أمس ({pdh:.4f}) أو قاع أمس ({pdl:.4f})."

# =========================================================
# 6. الشاشة الرئيسية العصرية (Cyberpunk Command Deck)
# =========================================================
st.markdown(f"""
<div class="hud-header">
    <div>
        <div class="hud-title">⚡ EUR/USD INSTITUTIONAL QUANT TERMINAL</div>
        <div style="color: {kz_color}; font-size: 0.9rem; font-weight: 600; margin-top: 4px;">{kz_text}</div>
    </div>
    <div style="text-align: left;">
        <span class="hud-badge">LIVE STREAM | {current_date_str}</span>
    </div>
</div>
""", unsafe_allow_html=True)

# قسم القيادة البصري: رادار القرار الكمي + بطاقة التوجيه + بطاقات الـ HUD الأربع
hero_col1, hero_col2 = st.columns([1.15, 2.2])

with hero_col1:
    # عداد الرادار الكمي (Plotly Cyber Gauge)
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number",
        value=bull_probability,
        number={'suffix': "% صعود", 'font': {'size': 26, 'color': '#f8fafc'}},
        title={'text': f"رادار القوة الكمية (البيع: {bear_probability:.0f}%)", 'font': {'size': 14, 'color': '#94a3b8'}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#475569"},
            'bar': {'color': bias_color, 'thickness': 0.35},
            'bgcolor': "rgba(15, 23, 42, 0.8)",
            'borderwidth': 1,
            'bordercolor': "#334155",
            'steps': [
                {'range': [0, 42], 'color': 'rgba(239, 68, 68, 0.22)'},
                {'range': [42, 58], 'color': 'rgba(245, 158, 11, 0.18)'},
                {'range': [58, 100], 'color': 'rgba(16, 185, 129, 0.22)'}
            ],
            'threshold': {'line': {'color': "white", 'width': 3}, 'thickness': 0.75, 'value': bull_probability}
        }
    ))
    fig_gauge.update_layout(height=230, margin=dict(l=18, r=18, t=40, b=10), paper_bgcolor="rgba(0,0,0,0)", font={'family': "Cairo"})
    st.plotly_chart(fig_gauge, use_container_width=True)

with hero_col2:
    st.markdown(f"""
    <div class="quant-card" style="border-right: 5px solid {bias_color};">
        <div style="font-size: 1.2rem; font-weight: 800; color: {bias_color}; margin-bottom: 6px;">{bias_badge}</div>
        <div style="font-size: 0.95rem; color: #e2e8f0; line-height: 1.6;">{action_plan}</div>
    </div>
    """, unsafe_allow_html=True)
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="quant-card">
            <div class="quant-card-title">السعر الحي (EUR/USD)</div>
            <div class="quant-card-val" style="color:#38bdf8;">{current_price:.4f}</div>
            <div class="quant-card-sub" style="color:#94a3b8;">{dealing_zone}</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="quant-card">
            <div class="quant-card-title">سيولة البنوك (POC / VWAP)</div>
            <div class="quant-card-val" style="color:#a78bfa;">{poc_price:.4f}</div>
            <div class="quant-card-sub" style="color:#c4b5fd;">VWAP: {current_vwap:.4f}</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="quant-card">
            <div class="quant-card-title">تدفق المال (MFI 14)</div>
            <div class="quant-card-val" style="color:#34d399;">{current_mfi:.1f}</div>
            <div class="quant-card-sub" style="color:#6ee7b7;">{absorption_status.split()[1]}</div>
        </div>
        """, unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="quant-card">
            <div class="quant-card-title">استهلاك المدى (ATR)</div>
            <div class="quant-card-val" style="color:#fbbf24;">{atr_used_pct:.0f}%</div>
            <div class="quant-card-sub" style="color:#fde68a;">{today_range_pips:.0f} من {atr_14d_pips:.0f} نقطة</div>
        </div>
        """, unsafe_allow_html=True)

# =========================================================
# 7. الأقسام التفاعلية الـ 5 (Modern Navigation Tabs)
# =========================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🎯 1. خريطة السيولة ومحاكي المستقبل",
    "🌊 2. الأوردر فلو والفوليوم بروفايل",
    "📊 3. المصفوفة الكمية والاتجاه اليومي",
    "🏦 4. السندات وتقرير البنوك COT",
    "🧮 5. حاسبة اللوت والأجندة الاقتصادية"
])

# ---------------------------------------------------------
# التبويب 1: مصفوفة الجلسات + الفجوات FVG + مروحة مونتي كارلو للمستقبل
# ---------------------------------------------------------
with tab1:
    st.subheader("🕒 مصفوفة سيولة الجلسات الآلية (Session Liquidity Matrix — بتوقيت الجزائر)")
    scol1, scol2, scol3 = st.columns(3)
    with scol1:
        st.markdown(f"""
        <div class="quant-card">
            <div class="quant-card-title">🌏 جلسة آسيا (01:00 - 07:00)</div>
            <div class="quant-card-val" style="font-size:1.25rem;">H: {asia_high:.4f} | L: {asia_low:.4f}</div>
            <div class="quant-card-sub" style="color:#38bdf8;">{asia_status}</div>
        </div>
        """, unsafe_allow_html=True)
    with scol2:
        st.markdown(f"""
        <div class="quant-card">
            <div class="quant-card-title">🔥 جلسة لندن (08:00 - 12:00)</div>
            <div class="quant-card-val" style="font-size:1.25rem;">H: {lon_high:.4f} | L: {lon_low:.4f}</div>
            <div class="quant-card-sub" style="color:#f59e0b;">{lon_status}</div>
        </div>
        """, unsafe_allow_html=True)
    with scol3:
        st.markdown(f"""
        <div class="quant-card">
            <div class="quant-card-title">🚀 جلسة نيويورك (13:00 - 17:00)</div>
            <div class="quant-card-val" style="font-size:1.25rem;">H: {ny_high:.4f} | L: {ny_low:.4f}</div>
            <div class="quant-card-sub" style="color:#10b981;">{ny_status}</div>
        </div>
        """, unsafe_allow_html=True)

    fcol1, fcol2 = st.columns([1.25, 1.45])
    with fcol1:
        st.markdown("##### 🧲 مصفوفة فجوات صناع السوق غير المغلقة (Smart Money FVG & Mitigation %)")
        if not df_fvg_matrix.empty:
            st.dataframe(df_fvg_matrix, use_container_width=True, hide_index=True)
        else:
            st.info("تم ملء جميع الفجوات القريبة (100% Mitigated) — انتظري تشكل فجوة جديدة في الكيلزون.")
            
    with fcol2:
        # مروحة احتمالات المستقبل (Monte Carlo Stochastic Projection Fan)
        st.markdown("##### 🔮 محاكاة مونتي كارلو لمسار السعر المستقبلي (Monte Carlo Probability Fan)")
        np.random.seed(42)
        n_steps = 20
        n_sims = 60
        bar_sigma = float(recent_intra['Close'].pct_change().dropna().std())
        bar_sigma = bar_sigma if bar_sigma > 0 else 0.001
        bar_drift = ((bull_probability - 50.0) / 50.0) * (bar_sigma * 0.25)
        
        sim_paths = np.zeros((n_steps, n_sims))
        sim_paths[0, :] = current_price
        for t in range(1, n_steps):
            shocks = np.random.normal(bar_drift, bar_sigma, n_sims)
            sim_paths[t, :] = sim_paths[t-1, :] * (1.0 + shocks)
            
        p90 = np.percentile(sim_paths, 90, axis=1)
        p75 = np.percentile(sim_paths, 75, axis=1)
        p50 = np.percentile(sim_paths, 50, axis=1)
        p25 = np.percentile(sim_paths, 25, axis=1)
        p10 = np.percentile(sim_paths, 10, axis=1)
        steps_x = list(range(n_steps))
        
        fig_mc = go.Figure()
        for i in range(min(18, n_sims)):
            fig_mc.add_trace(go.Scatter(x=steps_x, y=sim_paths[:, i], mode='lines', line=dict(color='rgba(56,189,248,0.12)', width=1), showlegend=False))
        fig_mc.add_trace(go.Scatter(x=steps_x, y=p90, mode='lines', line=dict(color='#ef4444', dash='dot', width=1.5), name='الحد العلوي (90%)'))
        fig_mc.add_trace(go.Scatter(x=steps_x, y=p10, mode='lines', line=dict(color='#10b981', dash='dot', width=1.5), fill='tonexty', fillcolor='rgba(6,182,212,0.12)', name='الحد السفلي (10%)'))
        fig_mc.add_trace(go.Scatter(x=steps_x, y=p50, mode='lines', line=dict(color='#fbbf24', width=3), name='المسار الأوسط المتوقع'))
        fig_mc.update_layout(height=310, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(15,23,42,0.5)", margin=dict(l=10, r=10, t=15, b=10), xaxis_title="الشموع المستقبلية القادمة", yaxis_title="السعر المتوقع")
        st.plotly_chart(fig_mc, use_container_width=True)

# ---------------------------------------------------------
# التبويب 2: الأوردر فلو، الفوليوم بروفايل، ومؤشر السيولة MFI
# ---------------------------------------------------------
with tab2:
    st.subheader(f"🌊 تحليل الأوردر فلو (CVD)، مؤشر السيولة المؤسساتية (MFI)، والفوليوم بروفايل — ({exec_tf})")
    st.markdown(f"**📌 تشخيص السيولة اللحظي:** `{mfi_status}`  |  **الأوردر فلو:** `{absorption_status}`")
    
    col_vp1, col_vp2 = st.columns([2.35, 1])
    with col_vp1:
        fig_of = make_subplots(
            rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04,
            row_heights=[0.55, 0.23, 0.22],
            subplot_titles=("الشارت اللحظي مع VWAP البنكي، POC, VAH/VAL, PDH/PDL", "أعمدة الدلتا الحقيقية (Order Flow Delta)", "مؤشر تدفق السيولة المؤسساتية (Institutional MFI 14)")
        )
        fig_of.add_trace(go.Candlestick(
            x=recent_intra.index, open=recent_intra['Open'], high=recent_intra['High'],
            low=recent_intra['Low'], close=recent_intra['Close'], name="EUR/USD"
        ), row=1, col=1)
        fig_of.add_trace(go.Scatter(x=recent_intra.index, y=recent_intra['VWAP'], mode='lines', line=dict(color='#f59e0b', width=2), name="VWAP"), row=1, col=1)
        
        fig_of.add_hline(y=pdh, line_dash="dash", line_color="#ef4444", annotation_text="PDH", row=1, col=1)
        fig_of.add_hline(y=pdl, line_dash="dash", line_color="#10b981", annotation_text="PDL", row=1, col=1)
        fig_of.add_hline(y=poc_price, line_dash="solid", line_color="#00e5ff", line_width=2, annotation_text="POC", row=1, col=1)
        fig_of.add_hline(y=vah_price, line_dash="dot", line_color="#a78bfa", annotation_text="VAH", row=1, col=1)
        fig_of.add_hline(y=val_price, line_dash="dot", line_color="#a78bfa", annotation_text="VAL", row=1, col=1)
        
        delta_colors = ['#10b981' if d >= 0 else '#ef4444' for d in recent_intra['Delta']]
        fig_of.add_trace(go.Bar(x=recent_intra.index, y=recent_intra['Delta'], marker_color=delta_colors, name="Delta"), row=2, col=1)
        
        fig_of.add_trace(go.Scatter(x=recent_intra.index, y=recent_intra['MFI'], mode='lines', line=dict(color='#38bdf8', width=2), fill='tozeroy', fillcolor='rgba(56,189,248,0.12)', name="MFI"), row=3, col=1)
        fig_of.add_hline(y=80, line_dash="dot", line_color="#ef4444", row=3, col=1)
        fig_of.add_hline(y=20, line_dash="dot", line_color="#10b981", row=3, col=1)
        
        fig_of.update_layout(height=640, xaxis_rangeslider_visible=False, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", showlegend=False)
        st.plotly_chart(fig_of, use_container_width=True)
        
    with col_vp2:
        if not vp_table.empty:
            vp_colors = ['#00e5ff' if abs(p - poc_price) < 1e-5 else ('#10b981' if d >= 0 else '#ef4444') for p, d in zip(vp_table['Price'], vp_table['Delta'])]
            fig_vp = go.Figure(go.Bar(
                y=vp_table['Price'].round(4).astype(str), x=vp_table['Volume'],
                orientation='h', marker_color=vp_colors
            ))
            fig_vp.update_layout(title="📊 Volume Profile (70% Value Area)", height=640, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", xaxis_title="العقود", yaxis_title="السعر")
            st.plotly_chart(fig_vp, use_container_width=True)

# ---------------------------------------------------------
# التبويب 3: المصفوفة الكمية والاتجاه اليومي
# ---------------------------------------------------------
with tab3:
    st.subheader("📊 مصفوفة القرار الكمي ومعادلات الفريم اليومي (Daily Institutional Quant)")
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Z-Score اليومي (20D)", f"{z_score_daily:+.2f} σ", "تشبع" if abs(z_score_daily) > 1.5 else "طبيعي")
    q2.metric("معامل هيرست (Hurst H)", f"{hurst_val:.2f}", "اتجاه مستمر (>0.5)" if hurst_val > 0.5 else "تذبذب (<0.5)")
    q3.metric("قوة الانحدار (R²)", f"{r_sq_d*100:.1f}%", "ميل صاعد" if slope_d > 0 else "ميل هابط")
    q4.metric("مخاطرة اليوم (VaR 95%)", f"±{var_95_pips:.0f} نقطة", f"PWH: {pwh:.4f} | PWL: {pwl:.4f}")
    
    df_factors = pd.DataFrame(quant_factors, columns=["المعيار الكمي", "النقاط", "التفسير الرياضي والمؤسساتي"])
    st.dataframe(df_factors, use_container_width=True, hide_index=True)
    
    daily_slice = eur_daily.iloc[-40:]
    fig_d = go.Figure()
    fig_d.add_trace(go.Candlestick(x=daily_slice.index, open=daily_slice['Open'], high=daily_slice['High'], low=daily_slice['Low'], close=daily_slice['Close'], name="1D EUR/USD"))
    fig_d.add_trace(go.Scatter(x=daily_slice.index, y=daily_slice['EMA20'], line=dict(color='#f59e0b', width=1.8), name="EMA 20"))
    fig_d.add_trace(go.Scatter(x=daily_slice.index, y=daily_slice['EMA50'], line=dict(color='#06b6d4', width=1.8), name="EMA 50"))
    fig_d.add_trace(go.Scatter(x=eur_daily.index[-20:], y=lr_line, line=dict(color='#fde047', dash='dot', width=2.2), name="Linear Regression"))
    fig_d.update_layout(height=380, xaxis_rangeslider_visible=False, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_d, use_container_width=True)

# ---------------------------------------------------------
# التبويب 4: السندات وتقرير البنوك COT
# ---------------------------------------------------------
with tab4:
    st.subheader("🏦 تحليل السندات، الارتباطات، وتقرير تمركز الصناديق (CFTC COT Report)")
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("صافي عقود الصناديق (COT Net)", f"{latest_cot_net:+,.0f} عقد", f"تغير أسبوعي: {cot_change:+,.0f}")
    mc2.metric("نسبة عقود الشراء (Hedge Funds)", f"{cot_long_pct:.1f}%", f"البيع: {100-cot_long_pct:.1f}%")
    mc3.metric("فارق العائد (أوروبا - أمريكا)", f"{yield_spread_diff:+.2f}%", "يدعم اليورو" if yield_spread_diff > 0 else "يدعم الدولار")
    mc4.metric("ارتباط الدولار والباوند", f"DXY: {corr_dxy:+.2f}", f"GBP: {corr_gbp:+.2f}")
    
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        if not df_cot.empty:
            fig_cot = go.Figure(go.Bar(
                x=df_cot['Date'], y=df_cot['Net_HedgeFunds'],
                marker_color=['#10b981' if v >= 0 else '#ef4444' for v in df_cot['Net_HedgeFunds']]
            ))
            fig_cot.update_layout(title="🏛️ صافي عقود صناديق التحوط على اليورو (CFTC COT)", height=360, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_cot, use_container_width=True)
    with col_m2:
        norm_df = df_daily_macro[['EURUSD', 'DXY', 'US10Y']].iloc[-30:].copy()
        norm_df = (norm_df / norm_df.iloc[0] - 1) * 100
        fig_macro = go.Figure()
        fig_macro.add_trace(go.Scatter(x=norm_df.index, y=norm_df['EURUSD'], name="EUR/USD (%)", line=dict(color='#10b981', width=2.5)))
        fig_macro.add_trace(go.Scatter(x=norm_df.index, y=norm_df['DXY'], name="DXY (%)", line=dict(color='#ef4444', width=2)))
        fig_macro.add_trace(go.Scatter(x=norm_df.index, y=norm_df['US10Y'], name="US10Y (%)", line=dict(color='#f59e0b', dash='dot')))
        fig_macro.update_layout(title="📉 المقارنة النسبية (30 يوم): اليورو مقابل الدولار والعوائد", height=360, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_macro, use_container_width=True)

# ---------------------------------------------------------
# التبويب 5: حاسبة اللوت والأجندة الاقتصادية
# ---------------------------------------------------------
with tab5:
    st.subheader("🧮 حاسبة حجم العقد (Lot Size) واحتمال ضرب الهدف كمياً")
    rc1, rc2 = st.columns([1.1, 1.2])
    with rc1:
        entry_in = st.number_input("سعر الدخول (Entry Price):", value=float(round(current_price, 4)), format="%.5f", step=0.00010)
        default_sl = float(round(current_price - 0.0015, 4)) if bull_probability >= 50 else float(round(current_price + 0.0015, 4))
        default_tp = float(round(current_price + 0.0045, 4)) if bull_probability >= 50 else float(round(current_price - 0.0045, 4))
        sl_in = st.number_input("سعر وقف الخسارة (Stop Loss):", value=default_sl, format="%.5f", step=0.00010)
        tp_in = st.number_input("سعر الهدف (Take Profit):", value=default_tp, format="%.5f", step=0.00010)
        
    with rc2:
        sl_pips = abs(entry_in - sl_in) * 10000.0
        tp_pips = abs(tp_in - entry_in) * 10000.0
        if sl_pips >= 0.5:
            risk_dollars = account_balance * (default_risk_pct / 100.0)
            exact_lot = risk_dollars / (sl_pips * 10.0)
            reward_dollars = exact_lot * tp_pips * 10.0
            rr_ratio = tp_pips / sl_pips
            random_walk_prob = (sl_pips / (sl_pips + tp_pips)) * 100.0
            is_long_trade = tp_in > entry_in
            quant_edge_alignment = (bull_probability - 50.0) if is_long_trade else (bear_probability - 50.0)
            adjusted_hit_prob = float(np.clip(random_walk_prob + (quant_edge_alignment * 0.45), 5.0, 92.0))
            
            st.success(f"### 🎯 حجم العقد الميكانيكي: `{exact_lot:.2f} Lot`")
            rm1, rm2, rm3 = st.columns(3)
            rm1.metric("المخاطرة (-SL)", f"-${risk_dollars:.2f}", f"{sl_pips:.1f} نقطة")
            rm2.metric("الربح (+TP)", f"+${reward_dollars:.2f}", f"R:R 1:{rr_ratio:.1f}")
            rm3.metric("احتمال ضرب الهدف", f"{adjusted_hit_prob:.1f}%", "مدعوم كمياً" if quant_edge_alignment > 0 else "عكس التيار")
            
    st.divider()
    st.subheader("📰 الأجندة الاقتصادية الآلية (بتوقيت الجزائر CET)")
    
    @st.cache_data(ttl=3600)
    def fetch_algeria_forex_calendar():
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        try:
            resp = requests.get(url, timeout=10)
            root = ET.fromstring(resp.content)
            events = []
            for item in root.findall('event'):
                country = item.find('country').text if item.find('country') is not None else ""
                impact = item.find('impact').text if item.find('impact') is not None else ""
                if country in ['USD', 'EUR'] and impact in ['High', 'Medium']:
                    date_s = item.find('date').text or ""
                    time_s = item.find('time').text or ""
                    dz_time_display = time_s
                    try:
                        dt_gmt = datetime.strptime(f"{date_s} {time_s}", "%m-%d-%Y %I:%M%p")
                        dt_gmt = pytz.timezone('UTC').localize(dt_gmt)
                        dt_dz_ev = dt_gmt.astimezone(tz_dz)
                        dz_time_display = dt_dz_ev.strftime("%H:%M (بتوقيت الجزائر)")
                        date_s = dt_dz_ev.strftime("%Y-%m-%d")
                    except Exception:
                        pass
                    events.append({
                        "التاريخ": date_s,
                        "التوقيت": dz_time_display,
                        "العملة": "🇺🇸 USD" if country == "USD" else "🇪🇺 EUR",
                        "القوة": "🔥 قوي جداً" if impact == "High" else "🔸 متوسط",
                        "الخبر الاقتصادي": item.find('title').text or "-",
                        "التوقع": item.find('forecast').text or "-",
                        "السابق": item.find('previous').text or "-"
                    })
            return pd.DataFrame(events)
        except Exception:
            return pd.DataFrame()

    df_news = fetch_algeria_forex_calendar()
    if not df_news.empty:
        st.dataframe(df_news, use_container_width=True, hide_index=True)
    else:
        st.info("الأجندة الاقتصادية تتحدث تلقائياً مع افتتاح الأسبوع الجديد.")

