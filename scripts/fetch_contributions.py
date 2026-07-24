#!/usr/bin/env python3
"""
Fetch the last year of GitHub contributions for Cyb4819 by scraping the
public contributions calendar page. Writes data/contributions.json with
the same schema that render_heatmap_svg.py expects.
"""
import datetime
import json
import os
import re
import urllib.request

USERNAME = "Cyb4819"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "contributions.json")


def fetch_contributions_html(username):
    """Fetch the contributions calendar HTML from GitHub profile."""
    url = f"https://github.com/users/{username}/contributions"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_contributions(html_text):
    """Parse contribution days from the GitHub contributions calendar HTML."""
    # GitHub renders <td> elements with data-date and data-level attributes
    # Pattern: data-date="2025-07-20" ... data-level="1" ... >N contribution
    pattern = re.compile(
        r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*data-level="(\d)"[^>]*>'
        r'[^<]*?(\d+)\s+contributions?\s',
        re.DOTALL
    )
    # Also match "No contributions" days
    pattern_zero = re.compile(
        r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*data-level="0"[^>]*>'
        r'[^<]*?No contributions',
        re.DOTALL
    )

    days = {}

    for match in pattern.finditer(html_text):
        date_str, level, count = match.group(1), int(match.group(2)), int(match.group(3))
        days[date_str] = {"date": date_str, "count": count, "level": level}

    for match in pattern_zero.finditer(html_text):
        date_str = match.group(1)
        if date_str not in days:
            days[date_str] = {"date": date_str, "count": 0, "level": 0}

    # If regex approach didn't work well, try a simpler approach
    if len(days) < 30:
        # Fallback: look for data-date and count nearby text
        date_pattern = re.compile(r'data-date="(\d{4}-\d{2}-\d{2})"')
        dates_found = date_pattern.findall(html_text)
        
        # For each date, find the contribution count
        for date_str in dates_found:
            if date_str not in days:
                # Look for the count near this date
                idx = html_text.find(f'data-date="{date_str}"')
                if idx >= 0:
                    snippet = html_text[idx:idx+500]
                    count_match = re.search(r'(\d+)\s+contributions?', snippet)
                    if count_match:
                        days[date_str] = {"date": date_str, "count": int(count_match.group(1)), "level": 0}
                    elif "No contributions" in snippet:
                        days[date_str] = {"date": date_str, "count": 0, "level": 0}

    return days


def compute_streaks(sorted_days):
    """Compute current streak and longest streak from sorted day list."""
    today = datetime.date.today()
    
    current_streak = {"length": 0, "start": "", "end": ""}
    longest_streak = {"length": 0, "start": "", "end": ""}
    
    streak_len = 0
    streak_start = None
    
    for d in sorted_days:
        date = datetime.date.fromisoformat(d["date"])
        if d["count"] > 0:
            if streak_len == 0:
                streak_start = date
            streak_len += 1
            streak_end = date
        else:
            if streak_len > longest_streak["length"]:
                longest_streak = {
                    "length": streak_len,
                    "start": streak_start.isoformat() if streak_start else "",
                    "end": streak_end.isoformat() if streak_start else ""
                }
            streak_len = 0
            streak_start = None

    # Check last streak
    if streak_len > longest_streak["length"]:
        longest_streak = {
            "length": streak_len,
            "start": streak_start.isoformat() if streak_start else "",
            "end": streak_end.isoformat() if streak_start else ""
        }
    
    # Current streak: count backwards from today/yesterday
    current_len = 0
    current_start = None
    for d in reversed(sorted_days):
        date = datetime.date.fromisoformat(d["date"])
        if date > today:
            continue
        if d["count"] > 0:
            current_len += 1
            current_start = date
        else:
            if current_len > 0:
                break
            # Allow skipping today if no contributions yet
            if date == today:
                continue
            break
    
    if current_len > 0:
        current_streak = {
            "length": current_len,
            "start": current_start.isoformat(),
            "end": today.isoformat()
        }
    
    return current_streak, longest_streak


def build_output(days_dict):
    """Build the full contributions.json output."""
    sorted_days = sorted(days_dict.values(), key=lambda d: d["date"])
    
    if not sorted_days:
        raise ValueError("No contribution data found!")
    
    total = sum(d["count"] for d in sorted_days)
    active_days = sum(1 for d in sorted_days if d["count"] > 0)
    best_day = max(sorted_days, key=lambda d: d["count"])
    
    current_streak, longest_streak = compute_streaks(sorted_days)
    
    # Monthly totals
    monthly = {}
    for d in sorted_days:
        month_key = d["date"][:7]
        monthly[month_key] = monthly.get(month_key, 0) + d["count"]
    
    monthly_list = [{"month": k, "total": v} for k, v in sorted(monthly.items())]
    
    # Clean days output (just date + count)
    days_out = [{"date": d["date"], "count": d["count"]} for d in sorted_days]
    
    return {
        "username": USERNAME,
        "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "range": {
            "start": sorted_days[0]["date"],
            "end": sorted_days[-1]["date"]
        },
        "total_contributions": total,
        "active_days": active_days,
        "avg_per_active_day": round(total / max(active_days, 1), 1),
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "best_day": {
            "date": best_day["date"],
            "count": best_day["count"]
        },
        "monthly": monthly_list,
        "days": days_out
    }


if __name__ == "__main__":
    print(f"Fetching contributions for {USERNAME}...")
    html_text = fetch_contributions_html(USERNAME)
    print(f"Got {len(html_text)} bytes of HTML")
    
    days = parse_contributions(html_text)
    print(f"Parsed {len(days)} contribution days")
    
    if len(days) == 0:
        print("ERROR: Could not parse any contribution days from HTML!")
        print("Saving raw HTML for debugging...")
        debug_path = os.path.join(HERE, "..", "data", "debug_contributions.html")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(html_text)
        print(f"Saved to {debug_path}")
        exit(1)
    
    data = build_output(days)
    
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    
    print(f"Wrote {OUT}")
    print(f"  Total contributions: {data['total_contributions']}")
    print(f"  Active days: {data['active_days']}")
    print(f"  Best day: {data['best_day']['date']} ({data['best_day']['count']})")
    print(f"  Current streak: {data['current_streak']['length']} days")
    print(f"  Longest streak: {data['longest_streak']['length']} days")
