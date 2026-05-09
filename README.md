# Concrete Daily Bot 🤖

Automated daily check-in bot for [Concrete Points](https://points.concrete.xyz), built by **DEGIO**.

Runs every 24 hours — performs wallet login and daily check-in automatically.

---

## Features

- ✅ Daily check-in automation
- ✅ Multi-wallet support
- ✅ Optional proxy support
- ✅ Auto proxy rotation & dead proxy detection
- ✅ Loops every 24 hours automatically

---

## Requirements

- Python 3.8+
- pip packages (see `requirements.txt`)

---

## Installation

```bash
git clone https://github.com/degioz/concrete-daily-bot.git
cd concrete-daily-bot
pip install -r requirements.txt
```

---

## Configuration

### 1. `keys.txt` — Private Keys (required)

One Ethereum private key per line:

```
0xYOUR_PRIVATE_KEY_1
0xYOUR_PRIVATE_KEY_2
```

> ⚠️ **Never share your private keys or commit `keys.txt` to GitHub.** It is already in `.gitignore`.

### 2. `proxy.txt` — Proxies (optional)

One proxy per line:

```
http://user:pass@host:port
socks5://user:pass@host:port
```

Leave the file empty or omit it entirely to run without proxies.

---

## Usage

```bash
python3 bot.py
```

```bash
python bot.py
```

The bot will:
1. Run immediately on start
2. Repeat every 24 hours automatically

---

## Running in Background

**Linux/macOS (screen):**
```bash
screen -S concrete
python3 bot.py
# Detach: Ctrl+A then D
# Reattach: screen -r concrete
```

**Linux (nohup):**
```bash
nohup python3 bot.py > bot.log 2>&1 &
```

---

## File Structure

```
concrete-daily-bot/
├── bot.py               # Main bot script
├── keys.txt             # Private keys (not committed)
├── proxy.txt            # Proxies (not committed, optional)
├── keys.example.txt     # Sample keys format
├── proxy.example.txt    # Sample proxy format
├── requirements.txt
└── README.md
```

---

## Disclaimer

This bot is for educational purposes only. Use at your own risk. The author is not responsible for any loss of funds or account bans. Always keep your private keys safe.

---

## License

MIT License
