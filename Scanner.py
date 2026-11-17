import json
import urllib.request

# ================= CONFIGURATION =================
ODDS_API_KEY = "PASTE_YOUR_ODDS_API_KEY_HERE"
DISCORD_WEBHOOK_URL = "PASTE_YOUR_DISCORD_WEBHOOK_URL_HERE"

TARGET_SPORTS = [
    "basketball_nba",
    "americanfootball_nfl",
    "icehockey_nhl",
    "baseball_mlb",
    "basketball_ncaab",
    "americanfootball_ncaaf",
]

MIN_ODDS = -350  # Safest heavy favorite limit
MAX_ODDS = -200  # Minimum favorite limit
# =================================================


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def american_to_implied_prob(odds: int) -> float:
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def send_to_discord(message: str):
    payload = json.dumps({"content": message}).encode("utf-8")
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status


def get_active_sports() -> list[str]:
    """Checks which sports are currently in-season (costs 0 API credits)."""
    url = f"https://api.the-odds-api.com/v4/sports/?apiKey={ODDS_API_KEY}"
    active_data = fetch_json(url)
    active_keys = {item["key"] for item in active_data}
    return [sport for sport in TARGET_SPORTS if sport in active_keys]


def scan_all_sports():
    opportunities = []
    active_sports = get_active_sports()

    for sport in active_sports:
        url = (
            f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
            f"?apiKey={ODDS_API_KEY}&regions=us,eu&markets=h2h,spreads,totals&oddsFormat=american"
        )
        games = fetch_json(url)

        for game in games:
            matchup = f"{game['away_team']} @ {game['home_team']}"
            bookmakers = {b["key"]: b for b in game.get("bookmakers", [])}

            if "fanduel" not in bookmakers or "pinnacle" not in bookmakers:
                continue

            fd_markets = {
                m["key"]: m["outcomes"] for m in bookmakers["fanduel"]["markets"]
            }
            pin_markets = {
                m["key"]: m["outcomes"] for m in bookmakers["pinnacle"]["markets"]
            }

            for market_key in fd_markets:
                if market_key not in pin_markets:
                    continue

                pin_outcomes = pin_markets[market_key]
                fd_outcomes = fd_markets[market_key]
                total_pin_prob = sum(
                    american_to_implied_prob(o["price"]) for o in pin_outcomes
                )

                for fd_out in fd_outcomes:
                    fd_price = fd_out["price"]

                    # Filter strictly for -350 to -200 heavy favorites
                    if not (MIN_ODDS <= fd_price <= MAX_ODDS):
                        continue

                    matching_pin = next(
                        (
                            p
                            for p in pin_outcomes
                            if p["name"] == fd_out["name"]
                            and p.get("point") == fd_out.get("point")
                        ),
                        None,
                    )
                    if not matching_pin:
                        continue

                    true_prob = (
                        american_to_implied_prob(matching_pin["price"])
                        / total_pin_prob
                    )
                    decimal_odds = (100 / abs(fd_price)) + 1
                    ev_percent = ((true_prob * decimal_odds) - 1) * 100

                    # Only alert if FanDuel's odds beat the sharp true probability (+EV)
                    if ev_percent > 0:
                        point_str = f" {fd_out['point']}" if "point" in fd_out else ""
                        opportunities.append({
                            "sport": sport.split("_")[-1].upper(),
                            "matchup": matchup,
                            "market": market_key.upper(),
                            "pick": f"{fd_out['name']}{point_str}",
                            "odds": fd_price,
                            "win_prob": round(true_prob * 100, 1),
                            "ev": round(ev_percent, 2),
                        })

    opportunities.sort(key=lambda x: x["ev"], reverse=True)
    return opportunities


if __name__ == "__main__":
    picks = scan_all_sports()
    if not picks:
        print("No +EV picks in the -350 to -200 range right now.")
    else:
        lines = ["**🎯 Daily FanDuel Ladder Locks (-350 to -200 +EV)**\n"]
        for p in picks[:10]:
            lines.append(
                f"• **[{p['sport']}] {p['matchup']}**\n"
                f"  Pick: `{p['pick']}` ({p['market']}) | FD: **{p['odds']}** | "
                f"Win Prob: **{p['win_prob']}%** | EV: **+{p['ev']}%**"
            )
        report = "\n".join(lines)
        print(report)
        send_to_discord(report)
        print("Sent to Discord!")
