import re, io, sys, glob, os
sys.stdout.reconfigure(encoding="utf-8")
base = r"D:\summer-pinellia"
files = ["index.html","products/index.html"]
for root, dirs, fs in os.walk(base):
    if "articles" in root or "article_source" in root: continue
    for f in fs:
        if f.endswith(".html"):
            rel = os.path.relpath(os.path.join(root,f), base).replace("\\","/")
            if rel not in files: files.append(rel)
out = []
for f in files:
    p = os.path.join(base, f)
    try:
        s = io.open(p, encoding="utf-8-sig").read()
    except Exception as e:
        out.append("=== %s [READ FAIL] %s" % (f, e)); continue
    s = re.sub(r"<script[\s\S]*?</script>", " ", s)
    s = re.sub(r"<style[\s\S]*?</style>", " ", s)
    s = re.sub(r"<!--[\s\S]*?-->", " ", s)
    s = re.sub(r"<[^>]+>", "\n", s)
    lines = [l.strip() for l in s.split("\n") if l.strip()]
    out.append("=== " + f)
    for l in lines:
        out.append("   " + l)
io.open(r"D:\Compet-Windows\Compet\_strings.txt","w",encoding="utf-8").write("\n".join(out))
print("files:", len(files))