import pathlib,re
for name in ['remotive.py','arbeitnow.py','adzuna.py','jooble.py','jsearch.py']:
    p=pathlib.Path('/app/app/connectors/'+name)
    t=p.read_text()
    orig=t
    t=re.sub(r"\n        finally:\n            self\._rate_limit_last = time\.time\(\)\n","\n",t)
    t=re.sub(r"\n    def _rate_limit\(self\) -> None:\n(?:        .*\n)+?        self\._rate_limit_last = time\.time\(\)\n","\n    # uses Connector._rate_limit()\n",t)
    if t!=orig:
        p.write_text(t)
        print('patched',name)
