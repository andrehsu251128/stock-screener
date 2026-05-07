import yfinance as yf
import pandas as pd
import numpy as np
import twstock
import requests
import json
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

# 忽略不必要的警告
warnings.filterwarnings('ignore')

# ==========================================
# 1. LINE 推播設定
# ==========================================
def send_line_message(message):
    access_token = 'GfhsaBKZEcLNXjg63duCKTQu0Tc9xjUNHDRYS4B7KjvLhuVHGk4uFCnDWFTK8HXUQ1+NvtQFWX75BNKkywTXTA8xA3Sy27tz1yiXnsvdbjqG8OSw6VDhbnhYWMM5EHqxjsAl6rTrwiwTwHeWUUM8CwdB04t89/1O/w1cDnyilFU='
    user_id = 'U01f40fee5abfa116f018a9efb19e8fed'

    url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    data = {
        'to': user_id,
        'messages': [{'type': 'text', 'text': message}]
    }
    
    try:
        requests.post(url, headers=headers, data=json.dumps(data))
    except Exception as e:
        print(f"LINE 推播失敗: {e}")

# ==========================================
# 2. 定義篩選邏輯 (60日線 + KD 50以下)
# ==========================================
def check_turnaround_setup(hist):
    """中期位階 + KD 低檔交叉(<50) + CDP 當沖預測"""
    if len(hist) < 60: return False, {}

    c = hist['Close']; h = hist['High']; l = hist['Low']

    try:
        # 條件一：中期位階 (低於 60 日季線)
        ma60 = c.rolling(window=60).mean()
        if c.iloc[-1] >= ma60.iloc[-1]: return False, {}

        # 條件二：KD 交叉且在 50 以下
        rsv = (c - l.rolling(9).min()) / (h.rolling(9).max() - l.rolling(9).min()) * 100
        k = rsv.ewm(com=2).mean(); d = k.ewm(com=2).mean()
        k_val, d_val = k.iloc[-1], d.iloc[-1]
        
        # 放寬門檻至 50
        if not (k_val < 50 and d_val < 50 and k_val > d_val): return False, {}

        # 計算 CDP 參考價
        prev_h, prev_l, prev_c = h.iloc[-1], l.iloc[-1], c.iloc[-1]
        cdp = (prev_h + prev_l + 2 * prev_c) / 4
        sell_target = 2 * cdp - prev_l
        buy_target = 2 * cdp - prev_h

        data = {
            'Price': round(c.iloc[-1], 2),
            'K': round(k_val, 1),
            'D': round(d_val, 1),
            'Buy': round(buy_target, 2),
            'Sell': round(sell_target, 2)
        }
        return True, data
    except Exception: return False, {}

# ==========================================
# 3. 單檔分析
# ==========================================
def analyze_stock(stock_info):
    code, name, market = stock_info
    suffix = '.TW' if market == '上市' else '.TWO'
    yf_symbol = f"{code}{suffix}"
    
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        stock = yf.Ticker(yf_symbol, session=session)
        hist = stock.history(period="1y", progress=False)
        
        if hist.empty: return None
        
        is_target, data = check_turnaround_setup(hist)
        if is_target: return {'代號': code, '名稱': name, **data}
    except Exception: pass
    return None

# ==========================================
# 4. 主程式
# ==========================================
def main():
    print("====== 🚀 啟動放寬版當沖偵測 (60MA + KD50) ======")
    tw_stocks = [(code, info.name, info.market) for code, info in twstock.codes.items() if info.type == '股票']
    
    found_targets = []
    processed = 0
    
    with ThreadPoolExecutor(max_workers=15) as executor:
        future_to_stock = {executor.submit(analyze_stock, stock): stock for stock in tw_stocks}
        for future in as_completed(future_to_stock):
            processed += 1
            result = future.result()
            if result: found_targets.append(result)
            if processed % 500 == 0: print(f"⏳ 已掃描 {processed} 檔...")

    msg_lines = ["====== 🚀 盤前當沖雷達 (放寬版) ======"]
    
    if found_targets:
        df_result = pd.DataFrame(found_targets)
        # 依 K 值排序取前 5 檔
        df_result = df_result.sort_values(by='K').head(5).reset_index(drop=True)
        
        msg_lines.append(f"偵測到 {len(df_result)} 檔符合條件標的：\n")
        for index, row in df_result.iterrows():
            msg_lines.append(f"🎯 {row['代號']} {row['名稱']} (K:{row['K']})")
            msg_lines.append(f"   🚩 建議買入: {row['Buy']}")
            msg_lines.append(f"   💰 建議賣出: {row['Sell']}")
            msg_lines.append("-" * 15)
    else:
        msg_lines.append("放寬條件後仍無符合標的，盤勢可能極度保守。")
        
    send_line_message("\n".join(msg_lines))
    print("✅ 雲端推播已發送！")

if __name__ == "__main__":
    main()
