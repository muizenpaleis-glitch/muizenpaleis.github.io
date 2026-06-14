#!/usr/bin/env python3
"""Export your Picnic order history to a JSON the finance cockpit can import.

Picnic has no official API. This talks to the same (unofficial) storefront API
the mobile app uses, so treat it as best-effort: if Picnic changes the API,
bump --api-version or adjust the field names in extract_lines().

Nothing is sent anywhere except Picnic itself. Your password is MD5-hashed
locally (that's what the storefront login expects) and only the resulting
auth token is kept in memory for the session. Credentials are read from the
environment (PICNIC_USERNAME / PICNIC_PASSWORD) or prompted for interactively.

Usage:
    export PICNIC_USERNAME="you@example.com"
    export PICNIC_PASSWORD="..."            # or you'll be prompted
    python3 picnic_export.py                 # writes picnic_export.json
    python3 picnic_export.py -o ~/picnic.json --country nl
    python3 picnic_export.py --selftest      # parser self-check, no network

Then load the JSON in the dashboard's "Picnic grocery breakdown" panel.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

DEFAULT_API_VERSION = "15"
CLIENT_ID = 30100  # the storefront client id the app reports


def host_for(country: str) -> str:
    return f"https://storefront-prod.{country.lower()}.picnicinternational.com"


def load_dotenv():
    """Load KEY=VALUE pairs from a .env file next to this script (or the cwd)
    into the environment, without overwriting anything already set. Lets you put
    a complex password in a file you can see and edit, instead of typing it
    blind. The .env file is git-ignored."""
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, ".env"), os.path.join(os.getcwd(), ".env")):
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val



def _request(url, token=None, payload=None, method=None):
    data = None
    headers = {
        "User-Agent": "okhttp/4.9.2",
        "Content-Type": "application/json; charset=UTF-8",
        "x-picnic-agent": f"{CLIENT_ID};1.15.272",
        "x-picnic-did": "PICNIC-FINANCE-COCKPIT",
    }
    if token:
        headers["x-picnic-auth"] = token
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method or ("POST" if data is not None else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8") if resp.length != 0 else ""
            parsed = json.loads(body) if body else {}
            return parsed, dict(resp.headers)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise SystemExit(f"Picnic API error {e.code} on {url}\n{detail}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Network error reaching Picnic: {e.reason}")


def login(base, email, password):
    secret = hashlib.md5(password.encode("utf-8")).hexdigest()
    payload = {"key": email, "secret": secret, "client_id": CLIENT_ID}
    body, headers = _request(f"{base}/user/login", payload=payload)
    token = headers.get("x-picnic-auth") or headers.get("X-Picnic-Auth")
    if not token:
        raise SystemExit("Login failed: no auth token returned. Check credentials "
                         "(or the API version with --api-version).")
    return token


def fetch_deliveries(base, token):
    """Return full delivery objects, with line-item detail filled in."""
    summary, _ = _request(f"{base}/deliveries", token=token, payload=[])
    deliveries = summary if isinstance(summary, list) else summary.get("deliveries", [])
    full = []
    for d in deliveries:
        did = d.get("delivery_id") or d.get("id")
        # The summary often omits line items; fetch detail when it looks empty.
        if did and not _has_lines(d):
            detail, _ = _request(f"{base}/deliveries/{did}", token=token)
            if detail:
                d = detail
            time.sleep(0.3)  # be polite
        full.append(d)
    return full


def _has_lines(delivery):
    for order in delivery.get("orders", []) or []:
        if order.get("items"):
            return True
    return False


def extract_lines(delivery):
    """Yield {name, article_id, unit_quantity, qty, spend_cents, unit_price_cents}
    for every article line in a delivery. Picnic nests articles inside order
    lines, repeating an article once per unit, with prices in cents."""
    for order in delivery.get("orders", []) or []:
        for line in order.get("items", []) or []:
            articles = line.get("items") if isinstance(line.get("items"), list) else None
            if articles:
                first = articles[0]
                qty = len(articles)
                unit_price = first.get("price")
                spend = line.get("display_price")
                if spend is None:
                    spend = line.get("price")
                if spend is None:
                    spend = sum(a.get("price", 0) or 0 for a in articles)
                yield {
                    "name": first.get("name", "Onbekend"),
                    "article_id": first.get("id"),
                    "unit_quantity": first.get("unit_quantity", ""),
                    "qty": qty,
                    "spend_cents": spend or 0,
                    "unit_price_cents": unit_price or 0,
                }
            elif line.get("name") and line.get("price") is not None:
                # Flat order line (no nested article list)
                qty = line.get("count") or line.get("quantity") or 1
                yield {
                    "name": line["name"],
                    "article_id": line.get("id"),
                    "unit_quantity": line.get("unit_quantity", ""),
                    "qty": qty,
                    "spend_cents": line.get("price", 0) or 0,
                    "unit_price_cents": (line.get("price", 0) or 0) // max(qty, 1),
                }


def delivery_date(delivery):
    for key in ("creation_time", "delivery_time"):
        v = delivery.get(key)
        if v:
            return str(v)[:10]
    slot = delivery.get("slot") or {}
    v = slot.get("window_start") or slot.get("date")
    if v:
        return str(v)[:10]
    return ""


def build_export(deliveries):
    items = defaultdict(lambda: {"name": "", "article_id": None, "unit_quantity": "",
                                 "qty": 0, "spend_cents": 0, "orders": 0})
    out_deliveries = []
    total_spend = 0
    for d in deliveries:
        seen_in_delivery = set()
        d_spend = 0
        d_units = 0
        for ln in extract_lines(d):
            key = ln["article_id"] or ln["name"]
            agg = items[key]
            agg["name"] = ln["name"]
            agg["article_id"] = ln["article_id"]
            agg["unit_quantity"] = ln["unit_quantity"]
            agg["qty"] += ln["qty"]
            agg["spend_cents"] += ln["spend_cents"]
            if key not in seen_in_delivery:
                agg["orders"] += 1
                seen_in_delivery.add(key)
            d_spend += ln["spend_cents"]
            d_units += ln["qty"]
        total_spend += d_spend
        out_deliveries.append({
            "date": delivery_date(d),
            "total_eur": round(d_spend / 100, 2),
            "units": d_units,
        })

    item_list = []
    for v in items.values():
        item_list.append({
            "name": v["name"],
            "article_id": v["article_id"],
            "unit_quantity": v["unit_quantity"],
            "qty": v["qty"],
            "spend_eur": round(v["spend_cents"] / 100, 2),
            "orders": v["orders"],
            "avg_unit_price_eur": round((v["spend_cents"] / v["qty"]) / 100, 2) if v["qty"] else 0,
        })
    item_list.sort(key=lambda x: x["spend_eur"], reverse=True)
    out_deliveries.sort(key=lambda x: x["date"])
    dates = [d["date"] for d in out_deliveries if d["date"]]
    return {
        "source": "picnic",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "currency": "EUR",
        "totals": {
            "spend_eur": round(total_spend / 100, 2),
            "deliveries": len(out_deliveries),
            "distinct_items": len(item_list),
            "from": dates[0] if dates else "",
            "to": dates[-1] if dates else "",
        },
        "deliveries": out_deliveries,
        "items": item_list,
    }


def selftest():
    sample = [{
        "delivery_id": "d1", "creation_time": "2026-05-12T18:09:00.000+0200",
        "orders": [{"items": [
            {"display_price": 218, "items": [
                {"id": "s1", "name": "Halfvolle melk", "unit_quantity": "1 L", "price": 109},
                {"id": "s1", "name": "Halfvolle melk", "unit_quantity": "1 L", "price": 109},
            ]},
            {"display_price": 250, "items": [
                {"id": "s2", "name": "Bananen", "unit_quantity": "5 st", "price": 250},
            ]},
        ]}],
    }, {
        "delivery_id": "d2", "creation_time": "2026-05-19T16:39:00.000+0200",
        "orders": [{"items": [
            {"display_price": 109, "items": [
                {"id": "s1", "name": "Halfvolle melk", "unit_quantity": "1 L", "price": 109},
            ]},
        ]}],
    }]
    exp = build_export(sample)
    milk = next(i for i in exp["items"] if i["article_id"] == "s1")
    assert milk["qty"] == 3, milk
    assert milk["spend_eur"] == 3.27, milk
    assert milk["orders"] == 2, milk
    assert exp["totals"]["spend_eur"] == 5.77, exp["totals"]
    assert exp["totals"]["deliveries"] == 2
    assert exp["totals"]["distinct_items"] == 2
    assert exp["items"][0]["article_id"] == "s1"  # sorted by spend
    print("selftest OK:", json.dumps(exp["totals"]))


def main():
    ap = argparse.ArgumentParser(description="Export Picnic order history to JSON.")
    ap.add_argument("-o", "--output", default="picnic_export.json")
    ap.add_argument("--country", default="nl")
    ap.add_argument("--api-version", default=DEFAULT_API_VERSION)
    ap.add_argument("--selftest", action="store_true", help="run parser self-check, no network")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    load_dotenv()
    email = os.environ.get("PICNIC_USERNAME")
    password = os.environ.get("PICNIC_PASSWORD")
    if not email:
        email = input("Picnic email: ").strip()
    if not password:
        import getpass
        password = getpass.getpass("Picnic password: ")

    base = f"{host_for(args.country)}/api/{args.api_version}"
    print("Logging in to Picnic...", file=sys.stderr)
    token = login(base, email, password)
    print("Fetching deliveries...", file=sys.stderr)
    deliveries = fetch_deliveries(base, token)
    export = build_export(deliveries)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)
    t = export["totals"]
    print(f"Wrote {args.output}: {t['deliveries']} deliveries, "
          f"{t['distinct_items']} distinct items, EUR {t['spend_eur']:.2f} "
          f"({t['from']} -> {t['to']}).", file=sys.stderr)


if __name__ == "__main__":
    main()
