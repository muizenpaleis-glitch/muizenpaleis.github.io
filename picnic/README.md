# Picnic export → finance cockpit

Pull your Picnic order history (with line items) into a JSON file that the
dashboard's **Picnic grocery breakdown** panel can import. See what you order
most and where the grocery money actually goes.

## Why a script instead of a button in the dashboard?

Picnic has no official API, and the unofficial storefront API (the one the
mobile app uses) is locked to Picnic's own apps via CORS — a website can't call
it from your browser. So the login + fetch has to run outside the browser. This
small script does that locally; the dashboard only ever sees the resulting JSON.

**Your credentials never leave your machine.** The password is MD5-hashed
locally (that's what Picnic's login expects) and only the session token is held
in memory while the script runs. `.env` and `*.json` are git-ignored.

## Run it

Needs Python 3 (no third-party packages — standard library only).

```bash
cd picnic

# option A: environment variables
export PICNIC_USERNAME="you@example.com"
export PICNIC_PASSWORD="your-password"
python3 picnic_export.py

# option B: just run it and answer the prompts (password is hidden)
python3 picnic_export.py
```

This writes `picnic_export.json`. Options:

```bash
python3 picnic_export.py -o ~/Downloads/picnic.json   # output path
python3 picnic_export.py --country nl                  # storefront country
python3 picnic_export.py --api-version 15              # bump if login breaks
python3 picnic_export.py --selftest                    # parser check, no network
```

## Load it

In the dashboard, open **Picnic grocery breakdown → Load Picnic export** and
pick the JSON. It's stored in your browser (localStorage), same as everything
else.

## If something breaks

The unofficial API changes occasionally. If login fails, try a different
`--api-version`. If items come back empty, Picnic likely renamed fields —
the parsing lives in `extract_lines()` in `picnic_export.py` and is easy to
adjust. The `--selftest` flag exercises the parser against a synthetic order
so you can confirm the logic still runs.
