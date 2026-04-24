import requests
import time
from datetime import datetime

# ============================================================
# CONFIGURATION
# ============================================================
TELEGRAM_TOKEN = "8489785587:AAGi6Xjv3iHymncUgFhL1yyvX9QbwuBliP8"
TELEGRAM_CHAT_ID = "5621289946"
GEMINI_API_KEY = "AIzaSyC2xok03Zk0xWQ3K61wGZ0M62lGDNqR3yA"
CHECK_INTERVAL = 180
# ============================================================

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/option-chain",
}

def get_nse_option_chain(symbol="NIFTY"):
    session = requests.Session()
    try:
        session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=10)
        time.sleep(1)
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        response = session.get(url, headers=NSE_HEADERS, timeout=10)
        if response.status_code == 200:
            return response.json()
        print(f"NSE Error: {response.status_code}")
        return None
    except Exception as e:
        print(f"Data fetch error: {e}")
        return None

def parse_option_chain(data):
    if not data:
        return None
    records = data.get("records", {})
    spot_price = records.get("underlyingValue", 0)
    expiry_dates = records.get("expiryDates", [])
    nearest_expiry = expiry_dates[0] if expiry_dates else "Unknown"

    strikes_data = []
    total_call_oi = 0
    total_put_oi = 0

    for item in records.get("data", []):
        strike = item.get("strikePrice", 0)
        ce = item.get("CE", {})
        pe = item.get("PE", {})
        call_oi = ce.get("openInterest", 0)
        put_oi = pe.get("openInterest", 0)
        total_call_oi += call_oi
        total_put_oi += put_oi
        strikes_data.append({
            "strike": strike,
            "call_oi": call_oi,
            "put_oi": put_oi,
            "call_price": ce.get("lastPrice", 0),
            "put_price": pe.get("lastPrice", 0),
            "call_change": ce.get("pchangeinOpenInterest", 0),
            "put_change": pe.get("pchangeinOpenInterest", 0),
        })

    if not strikes_data:
        return None

    pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0
    max_pain = max(strikes_data, key=lambda x: x["call_oi"] + x["put_oi"])["strike"]
    atm_strikes = sorted(
        [s for s in strikes_data if abs(s["strike"] - spot_price) <= 500],
        key=lambda x: x["strike"]
    )
    max_call = max(strikes_data, key=lambda x: x["call_oi"])
    max_put = max(strikes_data, key=lambda x: x["put_oi"])

    return {
        "spot": spot_price,
        "expiry": nearest_expiry,
        "pcr": pcr,
        "max_pain": max_pain,
        "resistance": max_call["strike"],
        "support": max_put["strike"],
        "atm_strikes": atm_strikes[-10:],
    }

def analyze_with_gemini(parsed_data):
    strikes_text = "\n".join([
        f"Strike {s['strike']}: CallOI={s['call_oi']:,}, PutOI={s['put_oi']:,}, "
        f"CallPx=Rs{s['call_price']}, PutPx=Rs{s['put_price']}, "
        f"CallChg={s['call_change']}%, PutChg={s['put_change']}%"
        for s in parsed_data["atm_strikes"]
    ])

    prompt = f"""You are an expert NIFTY options trader. Analyze this live data and give SHORT ACTIONABLE signal in Bengali.

Spot: {parsed_data['spot']} | Expiry: {parsed_data['expiry']} | PCR: {parsed_data['pcr']}
Max Pain: {parsed_data['max_pain']} | Resistance: {parsed_data['resistance']} | Support: {parsed_data['support']}

{strikes_text}

Reply ONLY in this format in Bengali:
DIRECTION: [BULLISH/BEARISH/NEUTRAL - একটা কারণ]
STRIKE: [Strike CE/PE]
ENTRY: Rs[range]
TARGET: Rs[price]
SL: Rs[price]
NOTE: [একটা কথা]"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 300, "temperature": 0.3}
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        print(f"Gemini error: {r.status_code}")
        return "AI analysis পাওয়া যায়নি"
    except Exception as e:
        print(f"Gemini error: {e}")
        return "AI analysis পাওয়া যায়নি"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=10)
        if r.status_code == 200:
            print(f"Sent: {datetime.now().strftime('%H:%M:%S')}")
        else:
            print(f"Telegram error: {r.text}")
    except Exception as e:
        print(f"Telegram error: {e}")

def is_market_hours():
    now = datetime.now()
    if now.weekday() > 4:
        return False
    h, m = now.hour, now.minute
    return (h == 9 and m >= 15) or (10 <= h <= 14) or (h == 15 and m <= 30)

def main():
    print("NIFTY Alert System Started!")
    send_telegram(
        "🚀 <b>NIFTY Alert System চালু হয়েছে!</b>\n"
        "প্রতি ৩ মিনিটে analysis আসবে।\n"
        "Market hours: 9:15 AM - 3:30 PM"
    )

    while True:
        try:
            if is_market_hours():
                print(f"{datetime.now().strftime('%H:%M:%S')} — Fetching...")
                raw = get_nse_option_chain("NIFTY")
                if raw:
                    parsed = parse_option_chain(raw)
                    if parsed:
                        analysis = analyze_with_gemini(parsed)
                        msg = (
                            f"🕐 <b>{datetime.now().strftime('%I:%M %p')} — NIFTY Alert</b>\n\n"
                            f"💹 Spot: <b>{parsed['spot']}</b>\n"
                            f"📊 PCR: <b>{parsed['pcr']}</b>\n"
                            f"🔴 Resistance: <b>{parsed['resistance']}</b>\n"
                            f"🟢 Support: <b>{parsed['support']}</b>\n"
                            f"🎯 Max Pain: <b>{parsed['max_pain']}</b>\n"
                            f"📅 Expiry: {parsed['expiry']}\n\n"
                            f"─────────────────\n"
                            f"{analysis}\n"
                            f"─────────────────\n"
                            f"⚠️ <i>Educational only. নিজের বিচারে trade করুন।</i>"
                        )
                        send_telegram(msg)
            else:
                print(f"Market closed — {datetime.now().strftime('%H:%M:%S')}")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            send_telegram("⛔ NIFTY Alert System বন্ধ হয়েছে।")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
