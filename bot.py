"""
Concrete Points - Daily Check-in Bot

Setup:
  pip install requests eth-account fake-useragent colorama

Files:
  keys.txt  -> one private key per line
  proxy.txt -> one proxy per line
"""

import os
import re
import gc
import glob
import time
import shutil
import random
import tempfile
import requests
import requests.exceptions
from datetime import datetime, timedelta, timezone
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import to_hex
from fake_useragent import FakeUserAgent
from colorama import Fore, Style, init

init(autoreset=True)

API_1         = "https://points.concrete.xyz/api"
API_3         = "https://gql3.absinthe.network/v1/graphql"
CLIENT_SEASON = "z2zi-tzc2"
RETRY_MAX     = 5
TIMEOUT       = 60

# ── Output ─────────────────────────────────────────────────
def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg):
    print(f"{Fore.CYAN}[ {now()} ]{Style.RESET_ALL} {msg}")

def log_field(label, value, color=None):
    c = color or Fore.WHITE
    print(f"  {Fore.WHITE}{label:<12}{Style.RESET_ALL} : {c}{value}{Style.RESET_ALL}")

def separator(title=""):
    if title:
        print(f"\n{Fore.CYAN}{'─'*10} {title} {'─'*10}{Style.RESET_ALL}")
    else:
        print(f"{Fore.CYAN}{'─'*35}{Style.RESET_ALL}")

# ── Cleanup ────────────────────────────────────────────────
def cleanup():
    cleaned = []
    try:
        for f in glob.glob(os.path.join(tempfile.gettempdir(), "fake_useragent*")):
            try:
                os.remove(f)
                cleaned.append(f)
            except Exception:
                pass
    except Exception:
        pass
    for d in [".cache", "__pycache__"]:
        if os.path.exists(d):
            try:
                shutil.rmtree(d)
                cleaned.append(d)
            except Exception:
                pass
    gc.collect()
    log(f"Cleanup done — {Fore.WHITE}{len(cleaned)} items{Style.RESET_ALL} cleared")

# ── File loaders ───────────────────────────────────────────
def load_keys(path="keys.txt"):
    if not os.path.exists(path):
        log(f"{Fore.RED}keys.txt not found{Style.RESET_ALL}")
        return []
    with open(path) as f:
        keys = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    log(f"Loaded {Fore.WHITE}{len(keys)}{Style.RESET_ALL} accounts")
    return keys

def load_proxies(path="proxy.txt"):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        proxies = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    log(f"Loaded {Fore.WHITE}{len(proxies)}{Style.RESET_ALL} proxies")
    return proxies

def ensure_scheme(proxy):
    if any(proxy.startswith(s) for s in ["http://", "https://", "socks4://", "socks5://"]):
        return proxy
    return f"http://{proxy}"

# ── Proxy manager ──────────────────────────────────────────
class ProxyManager:
    def __init__(self, proxies):
        self.all_proxies  = list(proxies)
        self.dead_proxies = set()

    def mark_dead(self, proxy):
        self.dead_proxies.add(proxy)

    def get_alive(self):
        return [p for p in self.all_proxies if p not in self.dead_proxies]

    def get_for_account(self, idx, exclude=None):
        exclude = exclude or set()
        alive   = [p for p in self.get_alive() if p not in exclude]
        if not alive:
            return None
        return ensure_scheme(alive[idx % len(alive)])

    @property
    def stats(self):
        t = len(self.all_proxies)
        d = len(self.dead_proxies)
        return f"{t-d}/{t}"

# ── Wallet ─────────────────────────────────────────────────
def get_address(pk):
    return Account.from_key(pk).address

def build_siwe(address, nonce, issued_at):
    return (
        f"points.concrete.xyz wants you to sign in with your Ethereum account:\n"
        f"{address}\n\n"
        f"Please sign with your account\n\n"
        f"URI: https://points.concrete.xyz\n"
        f"Version: 1\n"
        f"Chain ID: 1\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued_at}\n"
        f"Resources:\n"
        f"- connector://metaMask"
    )

def sign_siwe(pk, message):
    signed = Account.sign_message(encode_defunct(text=message), private_key=pk)
    return to_hex(signed.signature)

# ── Cookie / headers ───────────────────────────────────────
BASE_COOKIE = (
    f"client-season={CLIENT_SEASON}; "
    f"domain=https%3A%2F%2Fpoints.concrete.xyz; "
    f"__Secure-authjs.callback-url=https%3A%2F%2Fboost.absinthe.network; "
    f"redirect-pathname=%2Fhome"
)

def make_h1(ua, extra=""):
    return {
        "Accept":          "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type":    "application/json",
        "Origin":          "https://points.concrete.xyz",
        "Referer":         "https://points.concrete.xyz/home",
        "Sec-Fetch-Dest":  "empty",
        "Sec-Fetch-Mode":  "cors",
        "Sec-Fetch-Site":  "same-origin",
        "User-Agent":      ua,
        "Cookie":          BASE_COOKIE + (f"; {extra}" if extra else ""),
    }

def get_set_cookies(r):
    result = []
    try:
        for k, v in r.raw.headers.items():
            if k.lower() == "set-cookie":
                result.append(v)
    except Exception:
        val = r.headers.get("Set-Cookie", "")
        if val:
            result.append(val)
    return result

def parse_cookies(set_cookie_list):
    extra         = ""
    session_token = None
    for ck in set_cookie_list:
        m = re.search(r"^([^=]+)=([^;]*)", ck.strip())
        if m:
            k, v = m.group(1).strip(), m.group(2).strip()
            extra += f"; {k}={v}"
            if "session-token" in k:
                session_token = v
    return session_token, extra.strip("; ")

# ── Auth ───────────────────────────────────────────────────
def get_csrf(ua, proxy=None):
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(
        f"{API_1}/auth/csrf",
        headers=make_h1(ua),
        timeout=TIMEOUT,
        proxies=proxies,
    )
    r.raise_for_status()
    _, extra = parse_cookies(get_set_cookies(r))
    return r.json()["csrfToken"], extra

def do_credentials(ua, pk, address, csrf, extra="", proxy=None):
    issued_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    message   = build_siwe(address, csrf, issued_at)
    signature = sign_siwe(pk, message)
    headers   = {**make_h1(ua, extra), "Content-Type": "application/x-www-form-urlencoded"}
    proxies   = {"http": proxy, "https": proxy} if proxy else None
    r = requests.post(
        f"{API_1}/auth/callback/credentials",
        headers=headers,
        data={
            "message":     message,
            "redirect":    "false",
            "signature":   signature,
            "csrfToken":   csrf,
            "callbackUrl": "https://points.concrete.xyz/home",
        },
        timeout=TIMEOUT,
        proxies=proxies,
        allow_redirects=False,
    )
    return parse_cookies(get_set_cookies(r))

def get_session(ua, extra="", proxy=None):
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.get(
        f"{API_1}/auth/session",
        headers=make_h1(ua, extra),
        timeout=TIMEOUT,
        proxies=proxies,
    )
    r.raise_for_status()
    return r.json()

# ── GQL ────────────────────────────────────────────────────
def gql(ua, jwt, op, query, variables, proxy=None):
    headers = {
        "Accept":          "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Authorization":   f"Bearer {jwt}",
        "Content-Type":    "application/json",
        "Origin":          "https://points.concrete.xyz",
        "Referer":         "https://points.concrete.xyz/",
        "Sec-Fetch-Dest":  "empty",
        "Sec-Fetch-Mode":  "cors",
        "Sec-Fetch-Site":  "cross-site",
        "User-Agent":      ua,
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None
    r = requests.post(
        API_3,
        headers=headers,
        json={"operationName": op, "variables": variables, "query": query},
        timeout=TIMEOUT,
        proxies=proxies,
    )
    r.raise_for_status()
    return r.json()

# ── Queries ────────────────────────────────────────────────
CHECKIN_CONFIG = """
query getDailyCheckinConfig($clientSeason: String!) {
  points_config_point_sources(
    where: {client_season: {_eq: $clientSeason}, source_status: {_eq: LIVE}, source_type: {_eq: daily_checkin}}
  ) { id __typename }
}"""

CHECKIN_MUTATION = """
mutation upsertDailyCheckin($object: DailyCheckinInput!) {
  daily_checkin(point_source_data: $object) { id __typename }
}"""

# ── Functions ──────────────────────────────────────────────
def get_source_id(ua, jwt, proxy=None):
    data    = gql(ua, jwt, "getDailyCheckinConfig",
                  CHECKIN_CONFIG, {"clientSeason": CLIENT_SEASON}, proxy)
    sources = (data.get("data") or {}).get("points_config_point_sources", [])
    return sources[0]["id"] if sources else None

def do_checkin(ua, jwt, user_id, source_id, proxy=None):
    data = gql(ua, jwt, "upsertDailyCheckin", CHECKIN_MUTATION,
               {"object": {
                   "user_id":         user_id,
                   "client_season":   CLIENT_SEASON,
                   "point_source_id": source_id,
                   "status":          "SUCCESS",
               }}, proxy)
    if "errors" in data:
        msg = data["errors"][0].get("message", "error")
        if any(w in msg.lower() for w in ["already", "duplicate", "exist"]):
            return "already"
        return "error"
    return "success"

# ── Single account ─────────────────────────────────────────
def run_account(index, pk, proxy_mgr):
    address = get_address(pk)
    label   = f"{address[:6]}...{address[-4:]}"
    tried   = set()

    separator(f"{index+1}. {label}")

    for attempt in range(1, RETRY_MAX + 1):
        proxy = proxy_mgr.get_for_account(index, exclude=tried)

        try:
            ua = FakeUserAgent().random

            csrf, extra1          = get_csrf(ua, proxy)
            session_token, extra2 = do_credentials(ua, pk, address, csrf, extra1, proxy)

            if not session_token:
                log_field("Login", "Failed", Fore.RED)
                break

            log_field("Login", "Success", Fore.GREEN)

            sess = get_session(ua, extra2, proxy)
            jwt  = sess.get("token")
            uid  = (sess.get("user") or {}).get("id")

            if not jwt or not uid:
                log_field("Session", "Failed", Fore.RED)
                break

            sid = get_source_id(ua, jwt, proxy)
            if not sid:
                log_field("Config", "Failed", Fore.RED)
                break

            result = do_checkin(ua, jwt, uid, sid, proxy)

            if result == "success":
                log_field("Check-in", "Success", Fore.GREEN)
                return True
            elif result == "already":
                log_field("Check-in", "Already checked in", Fore.YELLOW)
                return True
            else:
                log_field("Check-in", "Failed", Fore.RED)
                return False

        except requests.exceptions.ProxyError:
            if proxy:
                proxy_mgr.mark_dead(proxy)
                tried.add(proxy)

        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError):
            if proxy:
                proxy_mgr.mark_dead(proxy)
                tried.add(proxy)

        except Exception as e:
            log_field("Error", str(e)[:60], Fore.RED)
            break

        time.sleep(2)

    return False

# ── Run one cycle ───────────────────────────────────────────
def run_cycle(keys, proxies):
    proxy_mgr = ProxyManager(proxies)
    success   = 0
    fail      = 0

    print(f"{Fore.CYAN}{'═'*35}{Style.RESET_ALL}")
    print(f"  {Fore.WHITE}Start    {Style.RESET_ALL}  {now()}")
    print(f"  {Fore.WHITE}Accounts {Style.RESET_ALL}  {len(keys)}  |  Proxies {proxy_mgr.stats}")
    print(f"{Fore.CYAN}{'═'*35}{Style.RESET_ALL}")

    for i, pk in enumerate(keys):
        ok = run_account(i, pk, proxy_mgr)
        if ok:
            success += 1
        else:
            fail += 1
        if i < len(keys) - 1:
            time.sleep(random.uniform(2, 5))

    cleanup()

    next_run = datetime.now() + timedelta(hours=24)
    print(f"\n{Fore.CYAN}{'═'*35}{Style.RESET_ALL}")
    print(f"  {Fore.WHITE}Done  {Style.RESET_ALL}  OK {Fore.GREEN}{success}{Style.RESET_ALL}  |  Fail {Fore.RED}{fail}{Style.RESET_ALL}")
    print(f"  {Fore.WHITE}Next  {Style.RESET_ALL}  {Fore.CYAN}{next_run.strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'═'*35}{Style.RESET_ALL}\n")

# ── Main (24h loop) ─────────────────────────────────────────
def main():
    print(f"{Fore.CYAN}")
    print("  Concrete Daily Bot By DEGIO")
    print(f"{'─'*35}{Style.RESET_ALL}\n")

    keys = load_keys("keys.txt")
    if not keys:
        return

    proxies = load_proxies("proxy.txt")

    while True:
        run_cycle(keys, proxies)
        nxt = datetime.now() + timedelta(hours=24)
        secs = 24 * 3600
        print(f"  {Style.DIM}Next run: {nxt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Sleeping 24h 0m. . .{Style.RESET_ALL}\n")
        time.sleep(secs)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}Stopped{Style.RESET_ALL}")
