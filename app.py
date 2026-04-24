import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import twstock
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import warnings

warnings.filterwarnings('ignore')

# 設定網頁標題與排版
st.set_page_config(page_title="台股極速轉機掃描器", page_icon="🚀", layout="wide")

# ==========================================
# 1. 定義篩選邏輯 (不變)
# ==========================================
def check_turnaround_setup(hist):
    if len(hist) < 120: return False, {}
    c = hist['Close']; h = hist['High']; l = hist['Low']; v = hist['Volume']

    try:
        # 條件一：低位階
        ma120 = c.rolling(window=120).mean()
        if c.iloc[-1] >= ma120.iloc[-1]: return False, {}

        # 條件二：低檔 KD 黃金交叉
        rsv = (c - l.rolling(9).min()) / (h.rolling(9).max() - l.rolling(9).min()) * 100
        k = rsv.ewm(com=2).mean(); d = k.ewm(com=2).mean()
        k_val, d_val = k.iloc[-1], d.iloc[-1]
        if not (k_val < 35 and d_val < 35 and k_val > d_val): return False, {}

        # 條件三：帶量轉折
        obv = (np.sign(c.diff()) * v).fillna(0).cumsum()
        obv_ma20 = obv.rolling(window=20).mean()
        if not (obv.iloc[-1] > obv_ma20.iloc[-1] and obv.diff(5).iloc[-1] > 0): return False, {}

        data = {
            '目前股價': round(c.iloc[-1], 2),
            'K值': round(k_val, 1),
            'D值': round(d_val, 1),
            '距半年線': f"{round((c.iloc[-1] - ma120.iloc[-1]) / ma120.iloc[-1] * 100, 2)}%"
        }
        return True, data
    except Exception: return False, {}

# ==========================================
# 2. 單檔分析 (不變)
# ==========================================
def analyze_stock(stock_info):
    code, name, market = stock_info
    suffix = '.TW' if market == '上市' else '.TWO'
    yf_symbol = f"{code}{suffix}"
    try:
        stock = yf.Ticker(yf_symbol)
        hist = stock.history(period="1y", progress=False)
        if hist.empty: return None
        is_target, data = check_turnaround_setup(hist)
        if is_target: return {'代號': code, '名稱': name, **data}
    except Exception: pass
    return None

# ==========================================
# 3. 網頁介面與主程式
# ==========================================
st.title("🚀 台股極速轉機股掃描器")
st.markdown("🎯 **篩選邏輯**：低位階 (低於半年線) + 低檔 KD 黃金交叉 (<35) + OBV 帶量轉折")
st.markdown("---")

# 建立一個按鈕，按下後才會開始跑
if st.button("🔥 啟動全市場掃描 (約需 2~3 分鐘)", type="primary"):
    
    # 建立網頁上的進度條與狀態文字
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    status_text.info("正在獲取全台股最新代號清單...")
    tw_stocks = [(code, info.name, info.market) for code, info in twstock.codes.items() if info.type == '股票']
    total_stocks = len(tw_stocks)
    
    status_text.info(f"✅ 成功獲取 {total_stocks} 檔上市櫃股票。開始 30 核心多執行緒海選...")
    
    found_targets = []
    processed = 0
    start_time = time.time()

    # 開始多執行緒掃描
    with ThreadPoolExecutor(max_workers=30) as executor:
        future_to_stock = {executor.submit(analyze_stock, stock): stock for stock in tw_stocks}
        
        for future in as_completed(future_to_stock):
            processed += 1
            result = future.result()
            if result: found_targets.append(result)
            
            # 更新網頁進度條
            if processed % 50 == 0 or processed == total_stocks:
                progress_percent = int((processed / total_stocks) * 100)
                progress_bar.progress(progress_percent)
                status_text.text(f"⏳ 掃描進度: {processed} / {total_stocks} 檔...")

    end_time = time.time()
    
    # 掃描完成，顯示結果
    st.success(f"✅ 掃描完成！總耗時: {round(end_time - start_time, 1)} 秒")
    
    if found_targets:
        st.subheader(f"🏆 恭喜！篩選出 {len(found_targets)} 檔潛在轉機股：")
        df_result = pd.DataFrame(found_targets)
        df_result = df_result.sort_values(by='K值').reset_index(drop=True)
        # 顯示漂亮的網頁資料表
        st.dataframe(df_result, use_container_width=True)
    else:
        st.warning("沒有找到符合條件的股票，繼續耐心等待時機！")