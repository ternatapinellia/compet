# -*- coding: utf-8 -*-
"""修正后的诊断：以文件系统实际能否找到为准"""
import io, os, json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME=os.path.expanduser("~")
BASES=[("用户", os.path.join(HOME,".morningmeal_Compet","skins")),
       ("内置", r"D:\Compet-Windows\Compet\_internal\skins")]

def refs(c):
    out=[]
    if c.get("idle_image"): out.append(c["idle_image"])
    for v in (c.get("tap_images") or []):
        if v: out.append(v)
    for v in (c.get("key_mappings") or {}).values():
        if v: out.append(v)
    return list(dict.fromkeys(out))

def exists_ci(d, name):
    if not name: return True
    if os.path.isfile(os.path.join(d,name)): return True
    low=name.lower()
    return any(f.lower()==low for f in os.listdir(d))

total=0
problems=[]
for tag, base in BASES:
    if not os.path.isdir(base): continue
    print("=" * 64)
    print("%s  %s" % (tag, base))
    for name in sorted(os.listdir(base)):
        d=os.path.join(base,name)
        if not os.path.isdir(d): continue
        cfg=os.path.join(d,"config.json")
        files=os.listdir(d)
        if not os.path.isfile(cfg):
            print("  ⚠ %-18s 没有 config.json" % name)
            problems.append((tag,name,"no-config",[]))
            continue
        try: c=json.loads(io.open(cfg,encoding="utf-8").read())
        except Exception as e:
            print("  ⚠ %-18s config 读取失败: %s" % (name,e)); continue
        miss=[w for w in refs(c) if not exists_ci(d,w)]
        imgs=[f for f in files if f.lower().endswith((".png",".gif",".webp",".jpg",".jpeg",".bmp"))]
        if miss:
            print("  ✗ %-18s 真缺 %d 张: %s" % (name,len(miss),", ".join(miss)))
            problems.append((tag,name,"missing",miss))
        elif not imgs:
            print("  ✗ %-18s 无图片" % name)
            problems.append((tag,name,"no-image",[]))
        else:
            print("  ✓ %-18s 正常（%d 张图）" % (name,len(imgs)))
print()
print("=" * 64)
print("真正有问题的: %d 个" % len(problems))
for tag,name,kind,miss in problems:
    print("   [%s] %s  (%s)" % (tag,name,kind))
    for m in miss: print("        - %s" % m)