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
# 2. 定義篩選邏輯 (技術面初篩)
# ==========================================
def check_turnaround_setup(hist):
    """低位階 + 低檔KD黃金交叉(<40) + OBV帶量轉折"""
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

        # 條件三：帶量轉折
        obv = (np.sign(c.diff()) * v).fillna(0).cumsum()
        obv_ma20 = obv.rolling(window=20).mean()
        if not (obv.iloc[-1] > obv_ma20.iloc[-1] and obv.diff(5).iloc[-1] > 0): return False, {}

        data = {
            'Price': round(c.iloc[-1], 2),
            'K': round(k_val, 1),
            'D': round(d_val, 1)
        }
        return True, data
    except Exception: return False, {}

# ==========================================
# 3. 單檔分析 (加入防封鎖偽裝)
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
    print("====== 🚀 啟動全市場極速掃描與推播系統 ======")
    print("正在獲取全台股最新代號清單...")
    
    tw_stocks = [(code, info.name, info.market) for code, info in twstock.codes.items() if info.type == '股票']
    total_stocks = len(tw_stocks)
    print(f"✅ 成功獲取 {total_stocks} 檔股票。開始掃描 (預計耗時約 3~5 分鐘)...\n")

    found_targets = []
    processed = 0
    start_time = time.time()

    # 本機端使用 15 個執行緒，平衡速度與防封鎖
    with ThreadPoolExecutor(max_workers=15) as executor:
        future_to_stock = {executor.submit(analyze_stock, stock): stock for stock in tw_stocks}
        
        for future in as_completed(future_to_stock):
            processed += 1
            result = future.result()
            if result: 
                found_targets.append(result)
                print(f"🎯 發現獵物: {result['代號']} {result['名稱']}")
                
            if processed % 200 == 0:
                print(f"⏳ 進度: {processed} / {total_stocks} 檔...")

    end_time = time.time()
    print(f"\n✅ 掃描完成！總耗時: {round(end_time - start_time, 1)} 秒")
    
    # 準備 LINE 推播文字
    msg_lines = ["====== 🚀 盤前當沖雷達 ======"]
    
    if found_targets:
        df_result = pd.DataFrame(found_targets)
        # 依 K 值排序，找出最具反彈潛力的前 5 檔
        df_result = df_result.sort_values(by='K').head(5).reset_index(drop=True)
        
        msg_lines.append(f"本日為您篩選出 {len(df_result)} 檔低檔轉機股：\n")
        
        for index, row in df_result.iterrows():
            msg_lines.append(f"🎯 {row['代號']} {row['名稱']}")
            msg_lines.append(f"   股價: {row['Price']} | KD: {row['K']}/{row['D']}")
            
        msg_lines.append("\n💡 技術面初篩已完成，建議放入 Excel 進行 Peter Lynch PEGY 基本面檢驗。")
    else:
        msg_lines.append("本日無符合條件之轉機股，繼續耐心等待時機！")
        
    final_message = "\n".join(msg_lines)
    
    # 發送 LINE 訊息
    print("正在發送 LINE 推播...")
    send_line_message(final_message)
    print("📱 推播完成！請檢查您的手機。")

if __name__ == "__main__":
    main()