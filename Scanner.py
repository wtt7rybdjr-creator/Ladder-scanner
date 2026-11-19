import json
import urllib.request

# ================= CONFIGURATION =================
ODDS_API_KEY = "b4186d080fa28126c95eda2757db14be"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1572116856108613731/6rq4I5OAfPMB1xRRy1NLRh3a9xSbqXuK"

TARGET_SPORTS = [
    "basketball_nba",
    "americanfootball_nfl",
    "icehockey_nhl",
    "baseball_mlb",
    "basketball_ncaab",
    "americanfootball_ncaaf",
]

MIN_ODDS = -350  # Safest heavy favorite limit
MAX_ODDS = -140  # Expanded limit to catch more spreads, totals & favorites
MIN_EV_PERCENT = 0.5  # Minimum positive expected value (%)
# =================================================


def american_to_implied(odds):
    if odds < 0:
        return abs(odds) / (abs(odds) + 100.0)
    return 100.0 / (odds + 100.0)


def american_to_decimal(odds):
    if odds < 0:
        return 1.0 + (100.0 / abs(odds))
    return 1.0 + (odds / 100.0)


def send_discord(message):
    payload = json.dumps({"content": message}).encode("utf-8")
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "LadderScanner/1.0",
        },
    )
    urllib.request.urlopen(req, timeout=15)


def scan():
    picks = []
    for sport in TARGET_SPORTS:
        url = (
            f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
            f"?apiKey={ODDS_API_KEY}&regions=us,eu&markets=h2h,spreads,totals&oddsFormat=american"
        )
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                games = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"Skipping {sport}: {e}")
            continue

        for game in games:
            books = {b["key"]: b for b in game.get("bookmakers", [])}
            fd = books.get("fanduel")
            sharp = books.get("pinnacle")
            if not fd or not sharp:
                continue

            sharp_markets = {m["key"]: m for m in sharp.get("markets", [])}
            for m in fd.get("markets", []):
                m_key = m["key"]
                s_market = sharp_markets.get(m_key)
                if not s_market:
                    continue

                s_outcomes = s_market.get("outcomes", [])
                if len(s_outcomes) != 2:
                    continue

                imp_total = sum(american_to_implied(o["price"]) for o in s_outcomes)
                if imp_total <= 0:
                    continue

                true_probs = {
                    (o["name"], o.get("point")): american_to_implied(o["price"]) / imp_total
                    for o in s_outcomes
                }

                for o in m.get("outcomes", []):
                    price = o["price"]
                    if not (MIN_ODDS <= price <= MAX_ODDS):
                        continue

                    t_prob = true_probs.get((o["name"], o.get("point")))
                    if not t_prob:
                        continue

                    dec = american_to_decimal(price)
                    ev_pct = ((t_prob * dec) - 1.0) * 100.0
                    if ev_pct >= MIN_EV_PERCENT:
                        point_str = f" {o['point']}" if o.get("point") is not None else ""
                        label = sport.split("_")[-1].upper()
                        picks.append(
                            (
                                ev_pct,
                                f"**[{label}] {game['away_team']} @ {game['home_team']}**\n"
                                f"Pick: `{o['name']}{point_str}` ({m_key.upper()}) | "
                                f"FD: **{price}** | Win Prob: **{t_prob*100:.1f}%** | EV: **+{ev_pct:.2f}%**",
                            )
                        )

    picks.sort(key=lambda x: x[0], reverse=True)
    if picks:
        top_lines = "\n\n".join(p[1] for p in picks[:8])
        send_discord(f"🎯 **Ladder Scanner (+EV Picks: {MIN_ODDS} to {MAX_ODDS})**\n\n{top_lines}")
    else:
        send_discord(
            f"✅ **Ladder Scan Complete:** No +EV picks in the `{MIN_ODDS}` to `{MAX_ODDS}` range right now."
        )


if __name__ == "__main__":
    scan()
