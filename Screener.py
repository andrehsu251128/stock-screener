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
# 1. LINE 推播設定 (已填入您的專屬密鑰)
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
# 2. 定義篩選邏輯 (技術面初篩 + CDP 買賣價計算)
# ==========================================
def check_turnaround_setup(hist):
    """低位階 + 低檔KD黃金交叉(<40) + CDP 當沖預測"""
    if len(hist) < 120: return False, {}

    c = hist['Close']; h = hist['High']; l = hist['Low']; v = hist['Volume']

    try:
        # 條件一：低位階 (低於半年線)
        ma120 = c.rolling(window=120).mean()
        if c.iloc[-1] >= ma120.iloc[-1]: return False, {}

        # 條件二：低檔 KD 黃金交叉
        rsv = (c - l.rolling(9).min()) / (h.rolling(9).max() - l.rolling(9).min()) * 100
        k = rsv.ewm(com=2).mean(); d = k.ewm(com=2).mean()
        k_val, d_val = k.iloc[-1], d.iloc[-1]
        if not (k_val < 40 and d_val < 40 and k_val > d_val): return False, {}

        # --- 新增：CDP 逆勢操作系統公式 ---
        prev_h = h.iloc[-1]
        prev_l = l.iloc[-1]
        prev_c = c.iloc[-1]
        
        # CDP 多空值 = (最高 + 最低 + 2*收盤) / 4
        cdp = (prev_h + prev_l + 2 * prev_c) / 4
        # NH 近高值 (建議賣價) = 2*CDP - 最低
        sell_target = 2 * cdp - prev_l
        # NL 近低值 (建議買價) = 2*CDP - 最高
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
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        stock = yf.Ticker(yf_symbol, session=session)
        hist = stock.history(period="1y", progress=False)
        
        if hist.empty: return None
        
        is_target, data = check_turnaround_setup(hist)
        if is_target: return {'代號': code, '名稱': name, **data}
        
    except Exception: pass
    return None

# ==========================================
# 4. 主程式：海選與推播
# ==========================================
def main():
    print("====== 🚀 啟動 CDP 當沖偵測系統 ======")
    tw_stocks = [(code, info.name, info.market) for code, info in twstock.codes.items() if info.type == '股票']
    
    found_targets = []
    processed = 0
    
    # 雲端執行建議維持 15-20 執行緒
    with ThreadPoolExecutor(max_workers=15) as executor:
        future_to_stock = {executor.submit(analyze_stock, stock): stock for stock in tw_stocks}
        for future in as_completed(future_to_stock):
            processed += 1
            result = future.result()
            if result: found_targets.append(result)
            if processed % 500 == 0: print(f"⏳ 已掃描 {processed} 檔...")

    # 準備 LINE 訊息
    msg_lines = ["====== 🚀 盤前當沖雷達 ======"]
    
    if