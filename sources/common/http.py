"""Small stdlib HTTP helper with retries, shared by all country fetchers."""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "truewatt-data/0.1 (+https://github.com/rafa-marq/energy-efficiency)"


def get_json(url, params=None, retries=3, timeout=90):
    if params:
        url = url + "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError) as e:
            # 4xx other than rate limiting won't fix itself; fail fast.
            code = getattr(e, "code", None)
            if code and 400 <= code < 500 and code != 429:
                raise
            if attempt == retries:
                raise
            wait = 2 ** attempt
            print(f"  retry {attempt}/{retries - 1} in {wait}s: {e}", file=sys.stderr)
            time.sleep(wait)
