# -*- coding: utf-8 -*-
"""只做安全的同形字符归一，不做模糊匹配"""
import io, os, json, sys, shutil
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME=os.path.expanduser("~")
BASES=[os.path.join(HOME,".morningmeal_Compet","skins"),
       r"D:\Compet-Windows\Compet\_internal\skins"]

def canon(s):
    out=[]
    for ch in s.lower():
        o=ord(ch)
        if 0x2010<=o<=0x2015 or o in (0x2212,0x30FC,0xFF0D): out.append("-")
        elif o in (0x2026,0x22EF,0x22EE): out.append(".")
        else: out.append(ch)
    return "".join(out)

def keys(c):
    out=[]
    if c.get("idle_image"): out.append(("idle", c["idle_image"]))
    for i,v in enumerate(c.get("tap_images") or []):
        if v: out.append(("tap%d"%i, v))
    for k,v in (c.get("key_mappings") or {}).items():
        if v: out.append(("map:"+k, v))
    return out

def setk(c,tag,real):
    if tag=="idle": c["idle_image"]=real
    elif tag.startswith("tap"): c["tap_images"][int(tag[3:])]=real
    elif tag.startswith("map:"): c["key_mappings"][tag[4:]]=real

total=0
for base in BASES:
    if not os.path.isdir(base): continue
    for name in sorted(os.listdir(base)):
        d=os.path.join(base,name); cfg=os.path.join(d,"config.json")
        if not (os.path.isdir(d) and os.path.isfile(cfg)): continue
        try: c=json.loads(io.open(cfg,encoding="utf-8").read())
        except Exception: continue
        cmap={canon(f): f for f in os.listdir(d)}
        fixes=[]
        for tag,val in keys(c):
            if not val or os.path.isfile(os.path.join(d,val)): continue
            cv=canon(val)
            # 只有当 canon 后唯一命中时才修
            if cv in cmap: fixes.append((tag,val,cmap[cv]))
        if not fixes: continue
        shutil.copyfile(cfg, cfg+".bak7")
        for tag,old,real in fixes:
            setk(c,tag,real)
            print("  [%s] %s: %r -> %r" % (os.path.basename(base), name, old, real))
            total+=1
        io.open(cfg,"w",encoding="utf-8").write(json.dumps(c,indent=4,ensure_ascii=False))
print()
print("安全修正 %d 处" % total)