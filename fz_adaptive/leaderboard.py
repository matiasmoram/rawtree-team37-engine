import json, sys, urllib.request, time
span = int(sys.argv[1]) if len(sys.argv) > 1 else 3600
now = int(time.time()) // 300 * 300
url = "https://datathon.rawtree.dev/api/state?by=model" + (f"&from={now-span}&to={now}" if span != 3600 else "")
s = json.load(urllib.request.urlopen(url, timeout=40))
T = sorted(s["teams"], key=lambda t: -t["conversion"])
print("baseline", round(s["baseline"]["conversion"], 3), round(s["baseline"]["cold_conversion"], 3), "reference", round(s["reference"]["conversion"], 3), round(s["reference"]["cold_conversion"], 3))
for i, t in enumerate(T[:8]): print(i + 1, t["team_id"], round(t["conversion"], 3), round(t["cold_conversion"], 3), round(t["on_time"], 1), t["requests"])
for i, t in enumerate(T):
    if t["team_id"] == "team_37":
        print("US rank", i + 1, "of", len(T), {k: v for k, v in t.items() if k != "versions"})
        for v in t.get("versions", []): print("   ", v["model_version"], v["requests"], "conv", round(v["conversion"], 3), "cold", round(v["cold_conversion"], 3), "rev", round(v["revenue_per_request"], 3), time.strftime("%H:%M", time.localtime(v["first"])), time.strftime("%H:%M", time.localtime(v["last"])))
