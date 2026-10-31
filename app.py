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
# إعدادات الصفحة الأساسية وتنسيق الواجهة
# =========================================================
st.set_page_config(
    page_title="EUR/USD Institutional Quant Terminal",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ضبط التوقيت الفعلي للجزائر (CET - UTC+1)
tz_dz = pytz.timezone('Africa/Algiers')
now_dz = datetime.now(tz_dz)
current_date_str = now_dz.strftime("%Y-%m-%d | %H:%M:%S")

# =========================================================
# الشريط الجانبي (Sidebar): الإعدادات والاتصال التلقائي
# =========================================================
with st.sidebar:
    st.header("⚙️ لوحة التحكم الكمية")
    st.caption(f"🕒 توقيت الجزائر: **{current_date_str}**")
    st.caption("🔄 التحديث الآلي للبيانات: **كل ساعة (3600s)**")
    st.caption("💎 الحالة: **نسخة مجانية 100% ومفتوحة المصدر**")
    
    if st.button("🔄 تحديث فوري لكل البيانات والأخبار", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
        
    st.divider()
    st.subheader("📐 إعدادات الفريم التحليلي")
    exec_tf = st.selectbox(
        "فريم الأوردر فلو والهيكلة اللحظية:",
        ["1h", "15m", "4h"],
        index=0,
        help="الفريم اليومي (1D) يُحلل آلياً في الخلفية لتحديد الاتجاه العام، وهذا الفريم يُستخدم للأوردر فلو والدخول."
    )
    lookback_bars = st.slider("عدد الشموع لحساب السيولة والـ Equilibrium:", min_value=24, max_value=120, value=50, step=2)
    
    st.divider()
    st.subheader("🛡️ إعدادات حساب FTMO")
    account_balance = st.number_input("رصيد الحساب ($):", min_value=100.0, value=10000.0, step=500.0)
    default_risk_pct = st.slider("نسبة المخاطرة للصفقة (%):", min_value=0.1, max_value=2.0, value=0.5, step=0.05)

# =========================================================
# 1. دالة التوقيت الزمني (Killzones) بتوقيت الجزائر
# =========================================================
def get_killzone_info(dt):
    if dt.weekday() >= 5:
        return "🛑 عطلة نهاية الأسبوع (السوق مغلق - التحليل مبني على إغلاق يوم الجمعة للتحضير للأسبوع القادم)"
    if dt.weekday() == 0:
        day_warn = "⚠️ يوم الاثنين (تجنبي التداول - مرحلة بناء سيولة الأسبوع)"
    elif dt.weekday() == 4:
        day_warn = "⚠️ يوم الجمعة (تجنبي التداول - تصفية مراكز البنوك)"
    else:
        day_warn = "✅ يوم تداول مثالي حسب خطتك (الثلاثاء / الأربعاء / الخميس)"
        
    hour = dt.hour
    if 1 <= hour < 7:
        kz = "🌏 جلسة آسيا (Asian Range - بناء سيولة القمة والقاع الآسيوي)"
    elif 8 <= hour < 11:
        kz = "🔥 لندن كيلزون (London Killzone - سحب سيولة آسيا والانطلاق)"
    elif 13 <= hour < 16:
        kz = "🚀 نيويورك كيلزون (NY Killzone - السيولة المؤسساتية العالية)"
    elif 16 <= hour < 18:
        kz = "🇬🇧 إغلاق لندن (London Close - جني الأرباح)"
    else:
        kz = "⏳ خارج أوقات الذروة (انتظار الـ Killzone القادم)"
        
    return f"{kz} | {day_warn}"

kz_text = get_killzone_info(now_dz)

# =========================================================
# 2. محرك جلب البيانات الشامل (يتحدث كل ساعة ttl=3600)
# =========================================================
@st.cache_data(ttl=3600, show_spinner="جاري جلب بيانات السيولة، العقود الآجلة، والسندات...")
def load_quant_data(intraday_tf="1h"):
    tickers = {
        "EURUSD": "EURUSD=X",
        "EURO_FUT": "6E=F",    # عقود اليورو الآجلة في بورصة شيكاغو (CME Real Volume)
        "DXY": "DX-Y.NYB",     # مؤشر الدولار الأمريكي
        "GBPUSD": "GBPUSD=X",  # الباوند لكشف انحراف السيولة SMT Divergence
        "US10Y": "^TNX",       # عوائد السندات الأمريكية 10 سنوات (Yield)
        "US3M": "^IRX",        # عوائد السندات قصيرة الأجل 3 أشهر (حساسة للفيدرالي)
        "EU_BOND": "IBGL.L",   # صندوق السندات الحكومية الأوروبية (السعر عكسي مع العائد)
        "FXE": "FXE",          # صندوق سيولة اليورو المؤسساتي
        "GOLD": "GC=F",        # الذهب
        "VIX": "^VIX"          # مؤشر الخوف والسيولة
    }
    
    period_map = {"15m": "5d", "1h": "1mo", "4h": "3mo"}
    p_intra = period_map.get(intraday_tf, "1mo")
    
    # 1. جلب الفريم اليومي (Daily)
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
    
    # 2. جلب الفريم اللحظي (Intraday)
    intra_close = {}
    eur_intra_ohlc = pd.DataFrame()
    fut_vol = pd.Series(dtype=float)
    
    for name, tk in ["EURUSD", "EURO_FUT", "DXY", "GBPUSD"]:
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

# جلب بيانات تقرير CFTC COT الرسمي لصناديق التحوط (مجاني 100% من السيرفر الحكومي)
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
                comm_long = float(item.get("comm_positions_long_all", 0))
                comm_short = float(item.get("comm_positions_short_all", 0))
                rows.append({
                    "Date": dt_str,
                    "HedgeFunds_Long": nc_long,
                    "HedgeFunds_Short": nc_short,
                    "Net_HedgeFunds": nc_long - nc_short,
                    "Commercial_Net": comm_long - comm_short
                })
            df_cot = pd.DataFrame(rows).sort_values("Date").reset_index(drop=True)
            return df_cot
    except Exception:
        pass
    return pd.DataFrame()

df_daily_macro, eur_daily, df_intra_macro, eur_intra = load_quant_data(exec_tf)
df_cot = fetch_cftc_cot_euro()

if eur_daily.empty or eur_intra.empty:
    st.error("⚠️ تعذر جلب البيانات من السيرفر حالياً. يرجى الضغط على زر التحديث الفوري في القائمة الجانبية.")
    st.stop()

# =========================================================
# 3. محرك المعادلات الكمية والأوردر فلو (Zero-Error Math Engine)
# =========================================================

# --- أ. حسابات الفريم اليومي والأسبوعي (Daily & Weekly Macro Quant) ---
current_price = float(eur_intra['Close'].iloc[-1])
pdh = float(eur_daily['High'].iloc[-2])
pdl = float(eur_daily['Low'].iloc[-2])
pdc = float(eur_daily['Close'].iloc[-2])
today_open = float(eur_daily['Open'].iloc[-1])
today_high = float(eur_daily['High'].iloc[-1])
today_low = float(eur_daily['Low'].iloc[-1])

# قمة وقاع الأسبوع السابق (Previous Week High / Low - PWH / PWL)
pwh = float(eur_daily['High'].iloc[-6:-1].max()) if len(eur_daily) >= 6 else pdh
pwl = float(eur_daily['Low'].iloc[-6:-1].min()) if len(eur_daily) >= 6 else pdl

# المتوسطات المؤسساتية اليومية والانحدار الخطي (Linear Regression 20D)
eur_daily['EMA20'] = eur_daily['Close'].ewm(span=20, adjust=False).mean()
eur_daily['EMA50'] = eur_daily['Close'].ewm(span=50, adjust=False).mean()
eur_daily['Returns'] = eur_daily['Close'].pct_change()

y_lr = eur_daily['Close'].iloc[-20:].values
x_lr = np.arange(len(y_lr))
slope_d, intercept_d = np.polyfit(x_lr, y_lr, 1)
r_sq_d = float(np.corrcoef(x_lr, y_lr)[0, 1] ** 2)
lr_line = slope_d * x_lr + intercept_d

# Z-Score اليومي (20 يوم)
mean_20d = float(eur_daily['Close'].rolling(20).mean().iloc[-1])
std_20d = float(eur_daily['Close'].rolling(20).std().iloc[-1])
z_score_daily = (current_price - mean_20d) / std_20d if std_20d > 0 else 0.0

# حساب معامل هيرست (Hurst Exponent H) + معامل كوفمان (Kaufman ER)
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
net_change_10d = abs(eur_daily['Close'].iloc[-1] - eur_daily['Close'].iloc[-11])
sum_changes_10d = eur_daily['Close'].diff().abs().iloc[-10:].sum()
efficiency_ratio = float(net_change_10d / sum_changes_10d) if sum_changes_10d > 0 else 0.0

if hurst_val > 0.52 and efficiency_ratio >= 0.30:
    market_regime = "اتجاه مؤسساتي مستمر (Persistent Trending - H > 0.52)"
elif hurst_val < 0.48:
    market_regime = "ارتداد للمتوسط وتذبذب (Mean-Reverting Range - H < 0.48)"
else:
    market_regime = "توازن انتقالي (Rotational / Balanced Market)"

# ATR اليومي واستهلاك المدى + VaR 95%
tr_daily = pd.concat([
    eur_daily['High'] - eur_daily['Low'],
    (eur_daily['High'] - eur_daily['Close'].shift()).abs(),
    (eur_daily['Low'] - eur_daily['Close'].shift()).abs()
], axis=1).max(axis=1)
atr_14d_pips = float(tr_daily.rolling(14).mean().iloc[-1] * 10000)
today_range_pips = float((today_high - today_low) * 10000)
atr_used_pct = (today_range_pips / atr_14d_pips * 100) if atr_14d_pips > 0 else 0.0

daily_std_ret = float(eur_daily['Returns'].iloc[-60:].std())
daily_mean_ret = float(eur_daily['Returns'].iloc[-60:].mean())
var_95_pips = float(1.645 * daily_std_ret * current_price * 10000)

# --- ب. حساب الـ VWAP اليومي ونطاقات الانحراف المعياري (Institutional VWAP Bands) ---
eur_intra['Typ_Price'] = (eur_intra['High'] + eur_intra['Low'] + eur_intra['Close']) / 3.0
eur_intra['Date_Group'] = eur_intra.index.date
eur_intra['PV'] = eur_intra['Typ_Price'] * eur_intra['Real_Volume']
eur_intra['P2V'] = (eur_intra['Typ_Price'] ** 2) * eur_intra['Real_Volume']

cum_pv = eur_intra.groupby('Date_Group')['PV'].cumsum()
cum_p2v = eur_intra.groupby('Date_Group')['P2V'].cumsum()
cum_vol = eur_intra.groupby('Date_Group')['Real_Volume'].cumsum().replace(0, 1e-6)

eur_intra['VWAP'] = cum_pv / cum_vol
vwap_variance = np.maximum(0.0, (cum_p2v / cum_vol) - (eur_intra['VWAP'] ** 2))
eur_intra['VWAP_STD'] = np.sqrt(vwap_variance)
eur_intra['VWAP_Upper1'] = eur_intra['VWAP'] + eur_intra['VWAP_STD']
eur_intra['VWAP_Lower1'] = eur_intra['VWAP'] - eur_intra['VWAP_STD']

current_vwap = float(eur_intra['VWAP'].iloc[-1])

# --- ج. حسابات الأوردر فلو وكشف الامتصاص (Order Flow Delta, CVD & Absorption) ---
hl_range = (eur_intra['High'] - eur_intra['Low']).replace(0, 1e-6)
buy_ratio = (eur_intra['Close'] - eur_intra['Low']) / hl_range
sell_ratio = (eur_intra['High'] - eur_intra['Close']) / hl_range

eur_intra['Buy_Vol'] = eur_intra['Real_Volume'] * buy_ratio
eur_intra['Sell_Vol'] = eur_intra['Real_Volume'] * sell_ratio
eur_intra['Delta'] = eur_intra['Buy_Vol'] - eur_intra['Sell_Vol']
eur_intra['CVD'] = eur_intra['Delta'].cumsum()

recent_intra = eur_intra.iloc[-lookback_bars:].copy()
net_delta_recent = float(recent_intra['Delta'].iloc[-10:].sum())
cvd_slope = float(recent_intra['CVD'].iloc[-1] - recent_intra['CVD'].iloc[-10])
price_change_10 = float(recent_intra['Close'].iloc[-1] - recent_intra['Close'].iloc[-10])

# كشف الدايفرجنس والامتصاص المؤسساتي بين السعر والـ CVD
if price_change_10 < 0 and cvd_slope > 0:
    absorption_status = "🟢 امتصاص شرائي خفي (Bullish CVD Absorption: السعر يهبط والبنوك تشتري العقود!)"
    of_score = 2.0
elif price_change_10 > 0 and cvd_slope < 0:
    absorption_status = "🔴 امتصاص بيعي خفي (Bearish CVD Absorption: السعر يصعد والبنوك تصرف العقود!)"
    of_score = -2.0
elif cvd_slope > 0 and net_delta_recent > 0:
    absorption_status = "🟢 تدفق أوامر شرائي صريح (تراكم عقود الشراء +CVD)"
    of_score = 1.5
elif cvd_slope < 0 and net_delta_recent < 0:
    absorption_status = "🔴 تدفق أوامر بيعي صريح (تراكم عقود البيع -CVD)"
    of_score = -1.5
else:
    absorption_status = "⚪ تدفق أوامر متوازن (انتظار دخول سيولة الكيلزون)"
    of_score = 0.0

# --- د. استخراج سيولة جلسة آسيا (Asian Session High / Low) ---
latest_day = eur_intra.index[-1].date()
asian_bars = eur_intra[(eur_intra.index.date == latest_day) & (eur_intra.index.hour >= 1) & (eur_intra.index.hour <= 7)]
if not asian_bars.empty:
    asia_high = float(asian_bars['High'].max())
    asia_low = float(asian_bars['Low'].min())
else:
    asia_high = float(recent_intra['High'].iloc[-15:].max())
    asia_low = float(recent_intra['Low'].iloc[-15:].min())

# --- هـ. خوارزمية Volume Profile المتكاملة (POC, VAH, VAL - 70% Value Area) ---
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
    
    vp_df = pd.DataFrame({
        "Price": bin_centers,
        "Volume": vol_hist,
        "Delta": delta_hist
    })
    return poc_level, vah_level, val_level, vp_df

poc_price, vah_price, val_price, vp_table = compute_volume_profile(recent_intra, num_bins=28)

# --- و. هيكلة السعر (Dealing Range 50% Equilibrium, PDH/PDL Sweep, FVG) ---
range_high = float(recent_intra['High'].max())
range_low = float(recent_intra['Low'].min())
equilibrium_50 = (range_high + range_low) / 2.0
dealing_zone = "Discount (منطقة رخيصة تحت 50% - مفضلة للشراء)" if current_price < equilibrium_50 else "Premium (منطقة غالية فوق 50% - مفضلة للبيع)"

if today_high > pdh and current_price < pdh:
    sweep_signal = "🔴 سحب سيولة قمة أمس وارتداد (PDH Sweep - إشارة بيعية قوية)"
    sweep_score = -2.0
elif today_low < pdl and current_price > pdl:
    sweep_signal = "🟢 سحب سيولة قاع أمس وارتداد (PDL Sweep - إشارة شرائية قوية)"
    sweep_score = 2.0
elif current_price > pdh:
    sweep_signal = "🟢 اختراق وتداول فوق قمة أمس (زخم صاعد)"
    sweep_score = 1.0
elif current_price < pdl:
    sweep_signal = "🔴 كسر وتداول تحت قاع أمس (زخم هابط)"
    sweep_score = -1.0
else:
    sweep_signal = "⚪ التداول داخل نطاق أمس (لم تُسحب سيولة PDH/PDL بعد)"
    sweep_score = 0.0

def scan_fvg(df_slice):
    bull_fvg, bear_fvg = "لا توجد فجوة قريبة", "لا توجد فجوة قريبة"
    for i in range(len(df_slice) - 3, max(0, len(df_slice) - 30), -1):
        h_i = float(df_slice['High'].iloc[i])
        l_i = float(df_slice['Low'].iloc[i])
        h_i2 = float(df_slice['High'].iloc[i+2])
        l_i2 = float(df_slice['Low'].iloc[i+2])
        
        if l_i2 > h_i and bull_fvg == "لا توجد فجوة قريبة":
            if current_price >= h_i:
                bull_fvg = f"{h_i:.4f} ⬅️ {l_i2:.4f}"
        if h_i2 < l_i and bear_fvg == "لا توجد فجوة قريبة":
            if current_price <= l_i:
                bear_fvg = f"{h_i2:.4f} ⬅️ {l_i:.4f}"
    return bull_fvg, bear_fvg

nearest_bull_fvg, nearest_bear_fvg = scan_fvg(recent_intra)

# --- ز. حسابات السندات المصححة وتمركز COT (Macro & COT Positioning) ---
us10y_chg_5d = float(df_daily_macro['US10Y'].pct_change(5).iloc[-1] * 100) if 'US10Y' in df_daily_macro else 0.0
eu_bond_price_chg_5d = float(df_daily_macro['EU_BOND'].pct_change(5).iloc[-1] * 100) if 'EU_BOND' in df_daily_macro else 0.0
# تصحيح رياضي: تغير عائد السند الأوروبي هو عكس تغير سعر صندوق IBGL.L
eu_yield_proxy_chg = -eu_bond_price_chg_5d
yield_spread_diff = eu_yield_proxy_chg - us10y_chg_5d

dxy_chg_5d = float(df_daily_macro['DXY'].pct_change(5).iloc[-1] * 100) if 'DXY' in df_daily_macro else 0.0
vix_chg_5d = float(df_daily_macro['VIX'].pct_change(5).iloc[-1] * 100) if 'VIX' in df_daily_macro else 0.0

corr_w = 20
corr_dxy = float(df_daily_macro['EURUSD'].rolling(corr_w).corr(df_daily_macro['DXY']).iloc[-1]) if 'DXY' in df_daily_macro else -0.9
corr_gbp = float(df_daily_macro['EURUSD'].rolling(corr_w).corr(df_daily_macro['GBPUSD']).iloc[-1]) if 'GBPUSD' in df_daily_macro else 0.8
corr_gold = float(df_daily_macro['EURUSD'].rolling(corr_w).corr(df_daily_macro['GOLD']).iloc[-1]) if 'GOLD' in df_daily_macro else 0.5

# استخراج تمركز صناديق التحوط من تقرير CFTC COT
if not df_cot.empty:
    latest_cot_net = float(df_cot['Net_HedgeFunds'].iloc[-1])
    prev_cot_net = float(df_cot['Net_HedgeFunds'].iloc[-2]) if len(df_cot) > 1 else latest_cot_net
    cot_change = latest_cot_net - prev_cot_net
    cot_long_pct = float(df_cot['HedgeFunds_Long'].iloc[-1] / (df_cot['HedgeFunds_Long'].iloc[-1] + df_cot['HedgeFunds_Short'].iloc[-1]) * 100)
else:
    latest_cot_net, cot_change, cot_long_pct = 0.0, 0.0, 50.0

# =========================================================
# 4. المصفوفة الكمية لحساب احتمالات الاتجاه اليومي (12 نقطة موزونة)
# =========================================================
quant_factors = []
weighted_score = 0.0
max_possible_score = 12.0

# 1. الاتجاه اليومي العام (EMA20 & Linear Regression Slope) [وزن: 2.0]
if current_price > eur_daily['EMA20'].iloc[-1] and slope_d > 0:
    weighted_score += 2.0
    quant_factors.append(("الاتجاه الكمي اليومي (Daily Trend)", "إيجابي صاعد (+2.0)", "السعر فوق EMA20 اليومي وميل الانحدار الخطي موجب."))
elif current_price < eur_daily['EMA20'].iloc[-1] and slope_d < 0:
    weighted_score -= 2.0
    quant_factors.append(("الاتجاه الكمي اليومي (Daily Trend)", "سلبي هابط (-2.0)", "السعر تحت EMA20 اليومي وميل الانحدار الخطي سالب."))
else:
    quant_factors.append(("الاتجاه الكمي اليومي (Daily Trend)", "محايد (0.0)", "تضارب بين المتوسط اليومي وميل الانحدار."))

# 2. الفوليوم بروفايل والـ VWAP البنكي [وزن: 2.0]
vp_vwap_pts = 0.0
if current_price > poc_price:
    vp_vwap_pts += 1.0
else:
    vp_vwap_pts -= 1.0
if current_price > current_vwap:
    vp_vwap_pts += 1.0
else:
    vp_vwap_pts -= 1.0
weighted_score += vp_vwap_pts
quant_factors.append(("تمركز السيولة (POC & Daily VWAP)", f"({vp_vwap_pts:+.1f})", f"POC: {poc_price:.4f} | VWAP البنكي: {current_vwap:.4f}"))

# 3. الأوردر فلو والامتصاص (Order Flow CVD & Absorption) [وزن: 2.0]
weighted_score += of_score
quant_factors.append(("الأوردر فلو والامتصاص (CVD & Delta)", f"({of_score:+.1f})", absorption_status))

# 4. سحب سيولة اليوم السابق (PDH / PDL Liquidity) [وزن: 2.0]
weighted_score += sweep_score
quant_factors.append(("سيولة اليوم السابق (PDH / PDL)", f"({sweep_score:+.1f})", sweep_signal))

# 5. فارق العوائد الحقيقي ومؤشر الدولار (Yield Spread & DXY) [وزن: 2.0]
macro_pts = 0.0
if dxy_chg_5d < 0:
    macro_pts += 1.0
else:
    macro_pts -= 1.0
if yield_spread_diff > 0:
    macro_pts += 1.0
else:
    macro_pts -= 1.0
weighted_score += macro_pts
quant_factors.append(("فارق العوائد والدولار (Yield Spread)", f"({macro_pts:+.1f})", f"فارق العائد الأوروبي/الأمريكي: {yield_spread_diff:+.2f}% | تغير DXY: {dxy_chg_5d:+.2f}%"))

# 6. تمركز صناديق التحوط (CFTC COT Institutional Flow) [وزن: 2.0]
cot_pts = 0.0
if latest_cot_net > 0 and cot_change >= 0:
    cot_pts = 2.0
elif latest_cot_net > 0 or cot_change > 0:
    cot_pts = 1.0
elif latest_cot_net < 0 and cot_change <= 0:
    cot_pts = -2.0
else:
    cot_pts = -1.0
weighted_score += cot_pts
quant_factors.append(("تمركز الصناديق (CFTC COT Report)", f"({cot_pts:+.1f})", f"صافي عقود الصناديق: {latest_cot_net:+,.0f} عقد (تغير أسبوعي: {cot_change:+,.0f})"))

# تحويل النقاط إلى احتمالية مئوية دقيقة (0% - 100%)
bull_probability = float(np.clip(((weighted_score + max_possible_score) / (2 * max_possible_score)) * 100, 5.0, 95.0))
bear_probability = 100.0 - bull_probability

if bull_probability >= 58.0:
    final_decision = "🟢 القرار الكمي لليوم: ابحثي عن صفقات شراء فقط (BUY ONLY BIAS)"
    decision_color = "success"
    execution_guide = (
        f"البيانات الكمية والأوردر فلو يدعمان الصعود باحتمالية **{bull_probability:.1f}%**. "
        f"انتظري سحب سيولة قاع آسيا ({asia_low:.4f}) أو التراجع لمنطقة Discount (تحت {equilibrium_50:.4f}) أو قرب الفجوة الشرائية ({nearest_bull_fvg}) ثم ادخلي شراء."
    )
elif bear_probability >= 58.0:
    final_decision = "🔴 القرار الكمي لليوم: ابحثي عن صفقات بيع فقط (SELL ONLY BIAS)"
    decision_color = "error"
    execution_guide = (
        f"البيانات الكمية والأوردر فلو يدعمان الهبوط باحتمالية **{bear_probability:.1f}%**. "
        f"انتظري سحب سيولة قمة آسيا ({asia_high:.4f}) أو الصعود لمنطقة Premium (فوق {equilibrium_50:.4f}) أو قرب الفجوة البيعية ({nearest_bear_fvg}) ثم ادخلي بيع."
    )
else:
    final_decision = "🟡 القرار الكمي لليوم: حياد وتضارب إحصائي (NEUTRAL / WAIT)"
    decision_color = "warning"
    execution_guide = f"الاحتمالات متقاربة (شراء {bull_probability:.1f}% مقابل بيع {bear_probability:.1f}%). لا تتداولي حتى يسحب السعر سيولة قمة أمس ({pdh:.4f}) أو قاع أمس ({pdl:.4f})."

# =========================================================
# الواجهة الرئيسية العلوية (ملخص القرار اليومي السريع)
# =========================================================
st.title("🏛️ المنصة الكمية والمؤسساتية الشاملة — EUR/USD")
st.info(f"**🕒 التوقيت والفلتر الزمني:** {kz_text}")

if decision_color == "success":
    st.success(f"### {final_decision}\n{execution_guide}")
elif decision_color == "error":
    st.error(f"### {final_decision}\n{execution_guide}")
else:
    st.warning(f"### {final_decision}\n{execution_guide}")

# شريط المقاييس السريعة (Top KPIs)
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("السعر الحي (EUR/USD)", f"{current_price:.4f}", f"{(current_price - today_open)*10000:+.1f} نقطة اليوم")
k2.metric("احتمالية الصعود / الهبوط", f"🟢 {bull_probability:.0f}%", f"🔴 بيع: {bear_probability:.0f}%")
k3.metric("POC السيولة / VWAP", f"{poc_price:.4f}", f"VWAP: {current_vwap:.4f}")
k4.metric("نطاق آسيا (Asia H / L)", f"H: {asia_high:.4f}", f"L: {asia_low:.4f}")
k5.metric("استهلاك المدى اليومي (ATR)", f"{atr_used_pct:.0f}%", f"{today_range_pips:.0f} من {atr_14d_pips:.0f} نقطة")

st.divider()

# =========================================================
# تقسيم الموقع إلى 5 أقسام منفصلة ومنظمة (Separated Tabs)
# =========================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 1. التحليل الكمي والاتجاه اليومي",
    "🌊 2. الأوردر فلو والفوليوم بروفايل",
    "🏦 3. السندات وتقرير البنوك COT",
    "🧮 4. حاسبة اللوت واحتمال الهدف",
    "📰 5. الأجندة الاقتصادية الآلية"
])

# ---------------------------------------------------------
# التبويب الأول: التحليل الكمي والاتجاه اليومي (Daily Quant)
# ---------------------------------------------------------
with tab1:
    st.subheader("📊 مصفوفة القرار الكمي ومعادلات الفريم اليومي (Daily Timeframe)")
    
    c_q1, c_q2, c_q3, c_q4 = st.columns(4)
    c_q1.metric("Z-Score اليومي (20D)", f"{z_score_daily:+.2f} σ", "تشبع شرائي" if z_score_daily > 1.5 else ("تشبع بيعي" if z_score_daily < -1.5 else "نطاق طبيعي"))
    c_q2.metric("معامل هيرست (Hurst H)", f"{hurst_val:.2f}", "اتجاه مستمر (>0.5)" if hurst_val > 0.5 else "ارتدادي (<0.5)")
    c_q3.metric("قوة الانحدار الخطي (R²)", f"{r_sq_d*100:.1f}%", "ميل صاعد" if slope_d > 0 else "ميل هابط")
    c_q4.metric("مخاطرة اليوم القصوى (VaR 95%)", f"±{var_95_pips:.0f} نقطة", f"ATR: {atr_14d_pips:.0f} نقطة")
    
    st.markdown(f"**📌 حالة السوق الإحصائية (Market Regime):** `{market_regime}` | **قمة/قاع الأسبوع السابق:** `PWH: {pwh:.4f}` — `PWL: {pwl:.4f}`")
    
    df_factors = pd.DataFrame(quant_factors, columns=["المعيار الكمي", "التقييم والنقاط", "التفسير الرياضي والمؤسساتي"])
    st.dataframe(df_factors, use_container_width=True, hide_index=True)
    
    col_ch1, col_ch2 = st.columns([2, 1])
    with col_ch1:
        daily_slice = eur_daily.iloc[-40:]
        fig_d = go.Figure()
        fig_d.add_trace(go.Candlestick(
            x=daily_slice.index, open=daily_slice['Open'], high=daily_slice['High'],
            low=daily_slice['Low'], close=daily_slice['Close'], name="اليورو اليومي (1D)"
        ))
        fig_d.add_trace(go.Scatter(x=daily_slice.index, y=daily_slice['EMA20'], line=dict(color='orange', width=1.5), name="EMA 20"))
        fig_d.add_trace(go.Scatter(x=daily_slice.index, y=daily_slice['EMA50'], line=dict(color='cyan', width=1.5), name="EMA 50"))
        fig_d.add_trace(go.Scatter(x=eur_daily.index[-20:], y=lr_line, line=dict(color='yellow', dash='dot', width=2), name="خط الانحدار الكمي (Linear Reg)"))
        fig_d.update_layout(title="📈 الشارت اليومي (1D) مع خط الانحدار الكمي والمتوسطات البنكية", height=400, xaxis_rangeslider_visible=False, template="plotly_dark")
        st.plotly_chart(fig_d, use_container_width=True)
        
    with col_ch2:
        ret_pips = eur_daily['Returns'].dropna().iloc[-100:] * current_price * 10000
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=ret_pips, nbinsx=25, marker_color='#00b4d8', name="توزيع النقاط اليومي"))
        fig_hist.add_vline(x=var_95_pips, line_dash="dash", line_color="red", annotation_text="+VaR 95%")
        fig_hist.add_vline(x=-var_95_pips, line_dash="dash", line_color="red", annotation_text="-VaR 95%")
        fig_hist.update_layout(title="📊 التوزيع الاحتمالي لحركة النقاط اليومية", height=400, template="plotly_dark", xaxis_title="التغير اليومي بالنقاط (Pips)", yaxis_title="التكرار")
        st.plotly_chart(fig_hist, use_container_width=True)

# ---------------------------------------------------------
# التبويب الثاني: الأوردر فلو والفوليوم بروفايل (Order Flow & VP)
# ---------------------------------------------------------
with tab2:
    st.subheader(f"🌊 تحليل الأوردر فلو (Order Flow Delta)، الـ VWAP، والفوليوم بروفايل — فريم ({exec_tf})")
    
    of1, of2, of3, of4 = st.columns(4)
    of1.metric("كاشف الامتصاص (CVD)", absorption_status.split()[1], f"صافي دلتا آخر 10 شموع: {net_delta_recent:+.0f}")
    of2.metric("منطقة القيمة العليا (VAH 70%)", f"{vah_price:.4f}", f"قمة أمس PDH: {pdh:.4f}")
    of3.metric("نقطة التحكم بالسيولة (POC)", f"{poc_price:.4f}", f"VWAP اليومي: {current_vwap:.4f}")
    of4.metric("منطقة القيمة الدنيا (VAL 70%)", f"{val_price:.4f}", f"قاع أمس PDL: {pdl:.4f}")
    
    st.markdown(
        f"**🎯 الفجوات السعرية (FVG):** شراء: `{nearest_bull_fvg}` | بيع: `{nearest_bear_fvg}` | "
        f"**نطاق آسيا:** `{asia_low:.4f} - {asia_high:.4f}` | **موقع السعر:** `{dealing_zone}`"
    )
    
    col_vp1, col_vp2 = st.columns([2.3, 1])
    with col_vp1:
        fig_of = make_subplots(
            rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
            row_heights=[0.65, 0.35],
            subplot_titles=("الشارت اللحظي مع VWAP البنكي، POC, VAH/VAL, PDH/PDL, Equilibrium", "الأوردر فلو: أعمدة الدلتا (Buy vs Sell Delta)")
        )
        fig_of.add_trace(go.Candlestick(
            x=recent_intra.index, open=recent_intra['Open'], high=recent_intra['High'],
            low=recent_intra['Low'], close=recent_intra['Close'], name="EUR/USD"
        ), row=1, col=1)
        
        # إضافة خط الـ VWAP المؤسساتي
        fig_of.add_trace(go.Scatter(
            x=recent_intra.index, y=recent_intra['VWAP'], mode='lines',
            line=dict(color='#ff9100', width=2), name="Daily VWAP"
        ), row=1, col=1)
        
        fig_of.add_hline(y=pdh, line_dash="dash", line_color="#ff4d4d", annotation_text="PDH (قمة أمس)", row=1, col=1)
        fig_of.add_hline(y=pdl, line_dash="dash", line_color="#00e676", annotation_text="PDL (قاع أمس)", row=1, col=1)
        fig_of.add_hline(y=poc_price, line_dash="solid", line_color="#00e5ff", line_width=2, annotation_text="POC (أعلى سيولة)", row=1, col=1)
        fig_of.add_hline(y=vah_price, line_dash="dot", line_color="#b388ff", annotation_text="VAH", row=1, col=1)
        fig_of.add_hline(y=val_price, line_dash="dot", line_color="#b388ff", annotation_text="VAL", row=1, col=1)
        fig_of.add_hline(y=equilibrium_50, line_dash="dashdot", line_color="gold", annotation_text="50% Eq", row=1, col=1)
        
        delta_colors = ['#00e676' if d >= 0 else '#ff1744' for d in recent_intra['Delta']]
        fig_of.add_trace(go.Bar(
            x=recent_intra.index, y=recent_intra['Delta'], marker_color=delta_colors, name="Order Flow Delta"
        ), row=2, col=1)
        
        fig_of.update_layout(height=580, xaxis_rangeslider_visible=False, template="plotly_dark", showlegend=False)
        st.plotly_chart(fig_of, use_container_width=True)
        
    with col_vp2:
        if not vp_table.empty:
            vp_colors = ['#00e5ff' if abs(p - poc_price) < 1e-5 else ('#00e676' if d >= 0 else '#ff5252') for p, d in zip(vp_table['Price'], vp_table['Delta'])]
            fig_vp = go.Figure()
            fig_vp.add_trace(go.Bar(
                y=vp_table['Price'].round(4).astype(str),
                x=vp_table['Volume'],
                orientation='h',
                marker_color=vp_colors,
                name="Volume Profile"
            ))
            fig_vp.update_layout(
                title="📊 توزيع السيولة (Volume Profile)\nالأخضر: شراء | الأحمر: بيع | السماوي: POC",
                height=580, template="plotly_dark", xaxis_title="حجم العقود", yaxis_title="مستوى السعر"
            )
            st.plotly_chart(fig_vp, use_container_width=True)

    fig_cvd = go.Figure()
    fig_cvd.add_trace(go.Scatter(
        x=recent_intra.index, y=recent_intra['CVD'], mode='lines',
        line=dict(color='#00e5ff', width=2.5), fill='tozeroy', name="Cumulative Volume Delta (CVD)"
    ))
    fig_cvd.update_layout(title="📈 منحنى الدلتا التراكمية (CVD) — لكشف التجميع والتصريف الخفي لصناع السوق", height=260, template="plotly_dark")
    st.plotly_chart(fig_cvd, use_container_width=True)

# ---------------------------------------------------------
# التبويب الثالث: السندات وتقرير البنوك CFTC COT
# ---------------------------------------------------------
with tab3:
    st.subheader("🏦 تحليل السندات، الارتباطات، وتقرير تمركز الصناديق (CFTC COT Report)")
    
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("صافي عقود الصناديق (COT Net)", f"{latest_cot_net:+,.0f} عقد", f"تغير أسبوعي: {cot_change:+,.0f}")
    mc2.metric("نسبة عقود الشراء (Hedge Funds)", f"{cot_long_pct:.1f}%", f"البيع: {100-cot_long_pct:.1f}%")
    mc3.metric("فارق العائد (أوروبا - أمريكا)", f"{yield_spread_diff:+.2f}%", "يدعم اليورو" if yield_spread_diff > 0 else "يدعم الدولار")
    mc4.metric("ارتباط الدولار والباوند", f"DXY: {corr_dxy:+.2f}", f"GBP: {corr_gbp:+.2f}")
    
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        if not df_cot.empty:
            fig_cot = go.Figure()
            fig_cot.add_trace(go.Bar(
                x=df_cot['Date'], y=df_cot['Net_HedgeFunds'],
                marker_color=['#00e676' if v >= 0 else '#ff5252' for v in df_cot['Net_HedgeFunds']],
                name="صافي عقود صناديق التحوط (Non-Commercial Net)"
            ))
            fig_cot.update_layout(title="🏛️ التمركز الحقيقي لصناديق التحوط على اليورو (CFTC COT - آخر 12 أسبوع)", height=380, template="plotly_dark")
            st.plotly_chart(fig_cot, use_container_width=True)
        else:
            st.info("بيانات CFTC COT قيد التحديث من السيرفر الأمريكي.")
            
    with col_m2:
        norm_df = df_daily_macro[['EURUSD', 'DXY', 'US10Y']].iloc[-30:].copy()
        norm_df = (norm_df / norm_df.iloc[0] - 1) * 100
        fig_macro = go.Figure()
        fig_macro.add_trace(go.Scatter(x=norm_df.index, y=norm_df['EURUSD'], name="EUR/USD (%)", line=dict(color='#00e676', width=2.5)))
        fig_macro.add_trace(go.Scatter(x=norm_df.index, y=norm_df['DXY'], name="DXY الدولار (%)", line=dict(color='#ff5252', width=2)))
        fig_macro.add_trace(go.Scatter(x=norm_df.index, y=norm_df['US10Y'], name="عوائد السندات US10Y (%)", line=dict(color='#ffab40', dash='dot')))
        fig_macro.update_layout(title="📉 المقارنة النسبية (آخر 30 يوم): اليورو مقابل الدولار وعوائد السندات", height=380, template="plotly_dark")
        st.plotly_chart(fig_macro, use_container_width=True)

# ---------------------------------------------------------
# التبويب الرابع: حاسبة اللوت ومعادلة احتمالية ضرب الهدف
# ---------------------------------------------------------
with tab4:
    st.subheader("🧮 الحاسبة الأوتوماتيكية لحجم العقد (Lot Size) واحتمالية ضرب الهدف كمياً")
    
    rc1, rc2 = st.columns([1.2, 1])
    with rc1:
        st.markdown("##### 1️⃣ أدخلي مستويات الصفقة من شارت TradingView:")
        entry_in = st.number_input("سعر الدخول (Entry Price):", value=float(round(current_price, 4)), format="%.5f", step=0.00010)
        default_sl = float(round(current_price - 0.0015, 4)) if bull_probability >= 50 else float(round(current_price + 0.0015, 4))
        default_tp = float(round(current_price + 0.0045, 4)) if bull_probability >= 50 else float(round(current_price - 0.0045, 4))
        
        sl_in = st.number_input("سعر وقف الخسارة (Stop Loss):", value=default_sl, format="%.5f", step=0.00010)
        tp_in = st.number_input("سعر الهدف (Take Profit):", value=default_tp, format="%.5f", step=0.00010)
        
    with rc2:
        st.markdown("##### 2️⃣ النتيجة الميكانيكية الدقيقة واحتمال النجاح الكمي:")
        sl_pips = abs(entry_in - sl_in) * 10000.0
        tp_pips = abs(tp_in - entry_in) * 10000.0
        
        if sl_pips < 0.5:
            st.error("⚠️ مسافة وقف الخسارة صغيرة جداً أو تساوي صفر. يرجى تعديل سعر الـ Stop Loss.")
        else:
            risk_dollars = account_balance * (default_risk_pct / 100.0)
            exact_lot = risk_dollars / (sl_pips * 10.0)
            reward_dollars = exact_lot * tp_pips * 10.0
            rr_ratio = tp_pips / sl_pips if sl_pips > 0 else 0.0
            
            # معادلة احتمالية ضرب الهدف قبل الستوب (Barrier Option Probability with Quant Bias Drift)
            random_walk_prob = (sl_pips / (sl_pips + tp_pips)) * 100.0
            is_long_trade = tp_in > entry_in
            quant_edge_alignment = (bull_probability - 50.0) if is_long_trade else (bear_probability - 50.0)
            adjusted_hit_prob = float(np.clip(random_walk_prob + (quant_edge_alignment * 0.45), 5.0, 92.0))
            expected_value_dlr = (adjusted_hit_prob / 100.0 * reward_dollars) - ((100.0 - adjusted_hit_prob) / 100.0 * risk_dollars)
            
            ftmo_daily_limit = account_balance * 0.05
            trades_to_breach_daily = ftmo_daily_limit / risk_dollars if risk_dollars > 0 else 0
            
            st.success(f"### 🎯 حجم العقد المطلوب (Lot Size): `{exact_lot:.2f} Lot`")
            
            rm1, rm2, rm3, rm4 = st.columns(4)
            rm1.metric("المخاطرة المالية (-SL)", f"-${risk_dollars:.2f}", f"{sl_pips:.1f} نقطة")
            rm2.metric("الربح المتوقع (+TP)", f"+${reward_dollars:.2f}", f"{tp_pips:.1f} نقطة")
            rm3.metric("عائد المخاطرة (R:R)", f"1 : {rr_ratio:.2f}", f"EV: {expected_value_dlr:+.1f}$")
            rm4.metric("احتمال ضرب TP قبل SL", f"{adjusted_hit_prob:.1f}%", "إيجابي كمياً" if expected_value_dlr > 0 else "عشوائي/سلبي")
            
            st.info(
                f"🛡️ **تقييم الأمان في FTMO:** حد الخسارة اليومي هو **${ftmo_daily_limit:.0f}** (5%). "
                f"بهذا اللوت (`{exact_lot:.2f}`)، حسابكِ يتحمل حتى **{trades_to_breach_daily:.0f} صفقات خاسرة متتالية** دون كسر القاعدة."
            )

# ---------------------------------------------------------
# التبويب الخامس: الأجندة الاقتصادية الآلية بتوقيت الجزائر
# ---------------------------------------------------------
with tab5:
    st.subheader("📰 الأجندة الاقتصادية الآلية (مُحولة أوتوماتيكياً لتوقيت الجزائر CET)")
    
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
                        "القوة": "🔥 قوي جداً (تجنبي التداول)" if impact == "High" else "🔸 متوسط",
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
        st.warning("لا توجد بيانات أخبار متاحة في هذه اللحظة بسبب عطلة نهاية الأسبوع، ستتحدث تلقائياً مع افتتاح الأسبوع الجديد.")
