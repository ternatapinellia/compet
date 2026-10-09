# -*- coding: utf-8 -*-
import re, time, requests
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Referer": "https://cn.bing.com/translator"}

def new_session():
    s = requests.Session()
    r = s.get("https://cn.bing.com/translator", headers=HEADERS, timeout=20)
    ig = re.search(r'IG:"([A-Za-z0-9]+)"', r.text)
    key = re.search(r'params_AbusePreventionHelper\s*=\s*\[(\d+),"([^"]+)"', r.text)
    return {"s": s, "IG": ig.group(1) if ig else "", "IID": "translator.5024",
            "key": key.group(1) if key else "", "token": key.group(2) if key else ""}

def tr(info, text):
    params = {"isVertical": "1", "IG": info["IG"], "IID": info["IID"]}
    data = [("fromLang", "zh-Hans"), ("text", text), ("to", "en"), ("token", info["token"]), ("key", info["key"])]
    r = info["s"].post("https://cn.bing.com/ttranslatev3", params=params, data=data, headers=HEADERS, timeout=40)
    return r.status_code, (r.json() if r.status_code == 200 else r.text[:100])

info = new_session()
print("token:", "OK" if info["token"] else "FAILED")
for n in [2000, 4000, 5000, 6000, 10000]:
    txt = "测试字符长度限制。" * (n // 9)
    code, res = tr(info, txt)
    nparas = 1
    if code == 200 and isinstance(res, list):
        out = res[0].get("translations",[{}])[0].get("text","")
        print("chars=%d code=%d ok out=%d" % (len(txt), code, len(out)))
    else:
        print("chars=%d code=%s res=%s" % (len(txt), code, str(res)[:100]))
    time.sleep(1.2)