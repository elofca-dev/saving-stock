#!/usr/bin/env python3
"""
Altin Takip - fiyat guncelleme script'i.

Bu script:
  1) Altin (gram/ceyrek/yarim/tam/cumhuriyet) ve doviz (USD/EUR) fiyatlarini
     Truncgil Finans API'sinden ceker; o kaynak basarisiz olursa yfinance
     uzerinden hesaplanan yaklasik degerlere duser.
  2) BIST_SYMBOLS listesindeki hisseleri yfinance ile ceker (Yahoo Finance
     BIST hisselerini "KOD.IS" formatinda tutar).
  3) FON_KODLARI listesindeki TEFAS fonlarini tefas.gov.tr'nin herkese acik
     (resmi dokumantasyonu olmayan) uc noktasindan cekmeyi dener; basarisiz
     olursa o fonu atlar.
  4) Sonucu data.json'a yazar (mevcut dosyayla ayni sema, gecmis kirpilir).

Yeni hisse/fon eklemek icin asagidaki BIST_SYMBOLS / FON_KODLARI listelerini
duzenlemen yeterli.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# BURAYI DUZENLE: takip etmek istedigin BIST hisseleri ve TEFAS fon kodlari.
# ---------------------------------------------------------------------------
BIST_SYMBOLS = [
    # "THYAO",
    # "GARAN",
]

FON_KODLARI = [
    # "AFA",
]

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
TR_TZ = timezone(timedelta(hours=3))
MAX_HISTORY = 240  # ~10 gun, saatlik firing varsayimiyla
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AltinTakipBot/1.0)"}


def now_iso():
    return datetime.now(TR_TZ).isoformat(timespec="seconds")


def load_existing():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"updatedAt": None, "source": None, "prices": {}, "history": [], "stocks": {}}


def http_get_json(url, timeout=15):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_tl_number(raw):
    """'6.909,39' gibi TR bicimli sayilari, '$4,442.72' gibi dolar bicimli
    sayilari da float'a cevirir (Truncgil'in Ons alani dolar formatinda gelir)."""
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if s.startswith("$"):
        return float(s[1:].replace(",", ""))
    s = s.replace(".", "").replace(",", ".")
    return float(s)


def fetch_from_truncgil():
    """Truncgil Finans (finans.truncgil.com) uzerinden gram/ceyrek/yarim/tam/
    cumhuriyet altini ve USD/EUR kurlarini ceker. Anahtar isimleri tam olarak
    bilinmedigi icin alt string eslesmesiyle esnek arama yapar."""
    raw = http_get_json("https://finans.truncgil.com/today.json")

    def find_entry(*needles):
        needles_lower = [n.lower() for n in needles]
        for key, val in raw.items():
            key_l = key.lower()
            if all(n in key_l for n in needles_lower):
                if isinstance(val, dict) and "Alış" in val and "Satış" in val:
                    return parse_tl_number(val["Alış"]), parse_tl_number(val["Satış"])
        return None

    gram = find_entry("gram", "altın")
    ceyrek = find_entry("çeyrek", "altın") or find_entry("ceyrek", "altin")
    yarim = find_entry("yarım", "altın") or find_entry("yarim", "altin")
    tam = find_entry("tam", "altın") or find_entry("tam", "altin")
    cumhuriyet = find_entry("cumhuriyet")
    ons = find_entry("ons")
    usd = find_entry("dolar") or find_entry("usd")
    eur = find_entry("euro") or find_entry("eur")

    required = [gram, ceyrek, yarim, tam, cumhuriyet, ons, usd, eur]
    if any(v is None for v in required):
        raise ValueError("Truncgil yanitinda beklenen alanlardan biri bulunamadi")

    return {
        "gram": {"buy": gram[0], "sell": gram[1]},
        "ceyrek": {"buy": ceyrek[0], "sell": ceyrek[1]},
        "yarim": {"buy": yarim[0], "sell": yarim[1]},
        "tam": {"buy": tam[0], "sell": tam[1]},
        "cumhuriyet": {"buy": cumhuriyet[0], "sell": cumhuriyet[1]},
        "ons": {"buy": ons[0], "sell": ons[1], "currency": "USD"},
        "usd": {"buy": usd[0], "sell": usd[1]},
        "eur": {"buy": eur[0], "sell": eur[1]},
    }, "truncgil"


def yf_last_price(symbols):
    """Verilen sembol listesini sirayla dener, ilk basarili son fiyati dondurur.
    Yahoo Finance bazi sembolleri (ornegin XAUUSD=X) zaman zaman 404
    dondurebiliyor; bu yuzden alternatif sembollerle yedekleme yapilir."""
    import yfinance as yf

    last_err = None
    for sym in symbols:
        try:
            price = yf.Ticker(sym).fast_info["last_price"]
            if price:
                return float(price)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"{symbols} icin fiyat alinamadi: {last_err}")


def fetch_from_yfinance_fallback():
    """Truncgil basarisiz olursa yfinance ile yaklasik degerler uretir.
    Ceyrek/yarim/tam/cumhuriyet icin standart agirlik carpanlari kullanilir;
    bu piyasa fiyatlarindaki iscilik primini yansitmaz, sadece yaklasik bir
    tahmindir."""
    usdtry = yf_last_price(["USDTRY=X"])
    eurtry = yf_last_price(["EURTRY=X"])
    # XAUUSD=X bazen 404 donuyor; GC=F (COMEX altin vadeli islem) yedek olarak kullanilir.
    xauusd = yf_last_price(["XAUUSD=X", "GC=F"])

    gram_try = (xauusd / 31.1034768) * usdtry
    # Yaklasik agirlik katsayilari (has altin bazinda kaba tahmin)
    ceyrek_try = gram_try * 1.75
    yarim_try = gram_try * 3.5
    tam_try = gram_try * 7.0
    cumhuriyet_try = gram_try * 7.216

    def pair(v, spread=0.001):
        return {"buy": round(v * (1 - spread), 2), "sell": round(v * (1 + spread), 2)}

    return {
        "gram": pair(gram_try),
        "ceyrek": pair(ceyrek_try),
        "yarim": pair(yarim_try),
        "tam": pair(tam_try),
        "cumhuriyet": pair(cumhuriyet_try),
        "ons": {"buy": round(xauusd * 0.999, 2), "sell": round(xauusd * 1.001, 2), "currency": "USD"},
        "usd": pair(usdtry),
        "eur": pair(eurtry),
    }, "yfinance-approx"


def fetch_stocks(symbols):
    if not symbols:
        return {}
    import yfinance as yf

    result = {}
    for sym in symbols:
        try:
            t = yf.Ticker(sym.upper() + ".IS")
            price = t.fast_info["last_price"]
            if price:
                result[sym.upper()] = round(float(price), 2)
        except Exception as e:
            print(f"[uyari] {sym} icin fiyat alinamadi: {e}", file=sys.stderr)
    return result


def fetch_funds(fon_kodlari):
    if not fon_kodlari:
        return {}
    result = {}
    today = datetime.now(TR_TZ).strftime("%d.%m.%Y")
    for kod in fon_kodlari:
        try:
            payload = (
                f"fontip=YAT&fonkod={kod}&bastarih={today}&bittarih={today}"
            ).encode("utf-8")
            req = urllib.request.Request(
                "https://www.tefas.gov.tr/api/DB/BindHistoryInfo",
                data=payload,
                headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded",
                         "Referer": "https://www.tefas.gov.tr/"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            rows = data.get("data", [])
            if rows:
                result[kod.upper()] = round(float(rows[-1]["FIYAT"]), 6)
        except Exception as e:
            print(f"[uyari] {kod} fonu icin fiyat alinamadi: {e}", file=sys.stderr)
    return result


def main():
    existing = load_existing()

    try:
        prices, source = fetch_from_truncgil()
    except Exception as e:
        print(f"[uyari] Truncgil basarisiz ({e}), yfinance yaklasik degerlerine geciliyor", file=sys.stderr)
        try:
            prices, source = fetch_from_yfinance_fallback()
        except Exception as e2:
            print(f"[hata] Hicbir kaynaktan altin/doviz verisi alinamadi: {e2}", file=sys.stderr)
            prices, source = None, None

    stocks = {}
    try:
        stocks.update(fetch_stocks(BIST_SYMBOLS))
    except Exception as e:
        print(f"[uyari] Hisse fiyatlari alinirken sorun oldu: {e}", file=sys.stderr)
    try:
        stocks.update(fetch_funds(FON_KODLARI))
    except Exception as e:
        print(f"[uyari] Fon fiyatlari alinirken sorun oldu: {e}", file=sys.stderr)

    if prices is None and not stocks:
        print("[hata] Hicbir veri alinamadi, data.json degistirilmedi.", file=sys.stderr)
        sys.exit(1)

    ts = now_iso()
    out = dict(existing)

    if prices is not None:
        out["updatedAt"] = ts
        out["source"] = source
        out["prices"] = prices

        history = existing.get("history", [])
        point = {"t": ts}
        for k, v in prices.items():
            point[k] = v["sell"] if isinstance(v, dict) else v
        history.append(point)
        out["history"] = history[-MAX_HISTORY:]
    else:
        print("[uyari] Altin/doviz verisi guncellenemedi, eski deger korunuyor.", file=sys.stderr)

    if stocks:
        merged_stocks = dict(existing.get("stocks", {}))
        merged_stocks.update(stocks)
        out["stocks"] = merged_stocks
        out["stocksUpdatedAt"] = ts

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Tamam: {DATA_FILE} guncellendi (kaynak: {source}, hisse/fon: {len(stocks)})")


if __name__ == "__main__":
    main()
