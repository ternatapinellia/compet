import io, ast
p = r"D:\Compet-Windows\Compet\generate_articles_bilingual.py"
s = io.open(p, encoding="utf-8").read()
orig = s

s = s.replace(
    '    def __init__(self):\n        self.session = requests.Session()\n',
    '    def __init__(self):\n        self.session = requests.Session()\n        self.session.trust_env = False\n        self.session.proxies = {}\n'
)
s = s.replace('headers=self.headers, timeout=20)',
              'headers=self.headers, timeout=20,\n                                     proxies={"http": None, "https": None})')
s = s.replace('data=data, headers=self.headers, timeout=45)',
              'data=data, headers=self.headers, timeout=45,\n                              proxies={"http": None, "https": None})')
s = s.replace(
    '        print("  [%d/%d] %s" % (counter[0], counter[1], d.name))\n        build_article(',
    '        print("  [%d/%d] %s" % (counter[0], counter[1], d.name))\n        try:\n            build_article('
)
s = s.replace(
    '                      uz, ue, tz, te, nav_zh, nav_en)\n\n        if counter[0] % 10 == 0:',
    '                          uz, ue, tz, te, nav_zh, nav_en)\n        except Exception as e:\n            print("    !! 跳过: %s" % e)\n            time.sleep(2)\n            BING.refresh()\n\n        if counter[0] % 10 == 0:'
)

assert s != orig, "no replacement happened"
ast.parse(s)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched OK")