import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import twstock
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import warnings

warnings.filterwarnings('ignore')

st.set_page_config(page_title="台股轉機掃描器", page_icon="🚀", layout="wide")

# ==========================================
# 1. 定義篩選邏輯
# ==========================================
def check_turnaround_setup(hist):
    if len(hist) < 120: return False, {}
    c = hist['Close']; h = hist['High']; l = hist['Low']; v = hist['Volume']

    try:
        # 條件一：低位階
        ma120 = c.rolling(window=120).mean()
        if c.iloc[-1] >= ma120.iloc[-1]: return False, {}

        # 條件二：低檔 KD 黃金交叉 (放寬至 40)
        rsv = (c - l.rolling(9).min()) / (h.rolling(9).max() - l.rolling(9).min()) * 100
        k = rsv.ewm(com=2).mean(); d = k.ewm(com=2).mean()
        k_val, d_val = k.iloc[-1], d.iloc[-1]
        if not (k_val < 40 and d_val < 40 and k_val > d_val): return False, {}

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
# 2. 單檔分析 (加入防封鎖與回報機制)
# ==========================================
def analyze_stock(stock_info):
    code, name, market = stock_info
    suffix = '.TW' if market == '上市' else '.TWO'
    yf_symbol = f"{code}{suffix}"
    
    try:
        # 微小延遲，避免瞬間併發被鎖 IP
        time.sleep(0.1) 
        stock = yf.Ticker(yf_symbol)
        hist = stock.history(period="1y", progress=False)
        
        if hist.empty: return "EMPTY" # 抓不到資料
        
        is_target, data = check_turnaround_setup(hist)
        if is_target: return {'代號': code, '名稱': name, **data}
        return "NO_MATCH"
        
    except Exception: return "ERROR"

# ==========================================
# 3. 網頁介面與主程式
# ==========================================
st.title("🚀 台股極速轉機股掃描器")
st.markdown("🎯 **篩選邏輯**：低位階(低於半年線) + 低檔KD黃金交叉(<40) + OBV帶量轉折")
st.markdown("---")

if st.button("🔥 啟動全市場掃描 (約需 2~4 分鐘)", type="primary"):
    
    status_text = st.empty()
    progress_bar = st.progress(0)
    detail_text = st.empty()
    
    status_text.info("正在獲取全台股最新代號清單...")
    tw_stocks = [(code, info.name, info.market) for code, info in twstock.codes.items() if info.type == '股票']
    total_stocks = len(tw_stocks)
    
    status_text.info(f"✅ 成功獲取 {total_stocks} 檔股票。開始掃描 (已啟用安全速限)...")
    
    found_targets = []
    processed = 0
    failed_count = 0
    start_time = time.time()

    # 將執行緒降低至 10，避免攻擊行為被 Yahoo 封鎖
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_stock = {executor.submit(analyze_stock, stock): stock for stock in tw_stocks}
        
        for future in as_completed(future_to_stock):
            processed += 1
            result = future.result()
            
            if isinstance(result, dict):
                found_targets.append(result)
            elif result in ["EMPTY", "ERROR"]:
                failed_count += 1
            
            if processed % 20 == 0 or processed == total_stocks:
                progress_bar.progress(int((processed / total_stocks) * 100))
                detail_text.text(f"⏳ 進度: {processed} / {total_stocks} 檔 | ⚠️ 抓取失敗: {failed_count} 檔")

    end_time = time.time()
    
    st.success(f"✅ 掃描完成！總耗時: {round(end_time - start_time, 1)} 秒")
    
    # 智慧警告機制
    if failed_count > total_stocks * 0.5:
        st.error(f"⚠️ 警告：有 {failed_count} 檔股票抓不到資料！雲端主機可能暫時被 Yahoo 限制連線 (Rate Limit)。建議稍後再試。")
    
    if found_targets:
        st.subheader(f"🏆 篩選出 {len(found_targets)} 檔潛在轉機股：")
        df_result = pd.DataFrame(found_targets)
        df_result = df_result.sort_values(by='K值').reset_index(drop=True)
        st.dataframe(df_result, use_container_width=True)
    else:
        st.warning("沒有找到符合條件的股票，繼續耐心等待時機！")
