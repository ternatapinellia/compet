# -*- coding: utf-8 -*-
import re, time, json, requests
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Referer": "https://cn.bing.com/translator"}

def new_session():
    s = requests.Session()
    r = s.get("https://cn.bing.com/translator", headers=HEADERS, timeout=20)
    ig = re.search(r'IG:"([A-Za-z0-9]+)"', r.text)
    key = re.search(r'params_AbusePreventionHelper\s*=\s*\[(\d+),"([^"]+)"', r.text)
    return {"s": s, "IG": ig.group(1) if ig else "", "IID": "translator.5024",
            "key": key.group(1) if key else "", "token": key.group(2) if key else ""}

def translate(info, text, frm="zh-Hans", to="en"):
    params = {"isVertical": "1", "IG": info["IG"], "IID": info["IID"]}
    data = [("fromLang", frm), ("text", text), ("to", to), ("token", info["token"]), ("key", info["key"])]
    r = info["s"].post("https://cn.bing.com/ttranslatev3", params=params, data=data, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        return None, "HTTP %s %s" % (r.status_code, r.text[:120])
    payload = r.json()
    if not isinstance(payload, list) or not payload:
        return None, payload
    return payload[0].get("translations", [{}])[0].get("text"), None

info = new_session()
print("token:", "OK" if info["token"] else "FAILED")
paras = ["第一段：主角推开了门，外面下着大雨。", "第二段：他想起了一个人，心里有点难过。", "第三段：远处传来一阵钟声。"]

print("\n[test1] blank-line join")
out, err = translate(info, "\n\n".join(paras))
print("err:", err); print("out:", repr(out))
time.sleep(1)
print("\n[test2] single-newline join")
out2, err2 = translate(info, "\n".join(paras))
print("err:", err2); print("out:", repr(out2))
time.sleep(1)
print("\n[test3] 1500 chars")
long_text = "这是一个用于测试长文本翻译的句子。" * 75
print("in chars:", len(long_text))
out3, err3 = translate(info, long_text)
print("err:", err3); print("out chars:", len(out3) if out3 else None)
print("out head:", repr(out3)[:140] if out3 else None)