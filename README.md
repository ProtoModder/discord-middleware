# Discord LLM Middleware

A security-hardened middleware for Discord that filters messages between Discord and your LLM. Features per-server/channel whitelisting, rate limiting, prompt injection detection, and content moderation.

## ⚠️ Current Architecture

**Important:** This middleware does NOT directly connect to OpenClaw (yet). It currently connects to:

1. **Ollama** (local AI) - via the brain server
2. **Custom brain endpoint** - you can point to any HTTP API

The intended architecture is:
```
Discord ↔ Middleware ↔ Nyx Brain ↔ OpenClaw
```

Currently: `Discord ↔ Middleware ↔ Ollama`

---

## Features

- **Per-server/channel whitelisting** - Only process messages from allowed servers and channels
- **Rate limiting** - Token bucket algorithm per user to prevent abuse
- **Prompt injection detection** - Blocks known jailbreak and injection patterns
- **Input sanitization** - Strips control characters, ANSI codes, zero-width chars
- **Content moderation** - Optional API-based moderation (OpenAI compatible)
- **Audit logging** - Full audit trail for security review

---

## 🚀 Quick Start

```bash
# 1. Clone and setup
cp config.yaml.example config.yaml

# 2. Configure (see sections below)

# 3. Run the brain server (in one terminal)
python nyx-brain.py

# 4. Run the middleware (in another terminal)
python middleware.py --config config.yaml
```

---

## 📋 Configuration

### 1. Copy the config file

```bash
cp config.yaml.example config.yaml
```

### 2. Edit `config.yaml` with your settings

See the sections below for each configuration option.

---

## 💬 How to Connect Discord

### Step 1: Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** and give it a name
3. Go to **Bot** in the sidebar
4. Click **Reset Token** to get your bot token
5. Copy the token to `config.yaml` as `bot_token`

### Step 2: Add Bot to Your Server

1. In Developer Portal, go to **OAuth2** → **URL Generator**
2. Select scope: `bot`
3. Select permissions: `Read Messages/View Channels`, `Send Messages`
4. Copy the generated URL and open it in your browser
5. Select your server and authorize the bot

### Step 3: Get Your Server & Channel IDs

**Enable Developer Mode:**
- Discord → User Settings → Advanced → Developer Mode: ON

**Copy IDs:**
- Right-click server name → Copy ID → Server ID
- Right-click channel name → Copy ID → Channel ID

Add these to `config.yaml`:
```yaml
allowed_servers:
  - "123456789012345678"

allowed_channels:
  - "111222333444555666"
```

---

## 🧠 How the Brain Works

The middleware connects to a brain server that provides AI responses. Two options:

### Option A: Use the Built-in Brain Server (Ollama)

```bash
# Terminal 1: Start the brain
python nyx-brain.py

# Terminal 2: Start middleware
python middleware.py --config config.yaml
```

The brain connects to Ollama by default (localhost:11434).

### Option B: Custom Brain Endpoint

Edit `middleware.py` to change the `llm_callback` function to point to your own endpoint:

```python
async def llm_callback(prompt: str, message: dict) -> dict:
    import aiohttp
    async with aiohttp.ClientSession() as session:
        payload = {"message": prompt}
        async with session.post("http://your-endpoint:port/chat", json=payload) as resp:
            data = await resp.json()
            return {'type': 'success', 'content': data.get('response')}
```

### Option C: Ollama Direct (No Brain Server)

You can also bypass the brain server and connect directly to Ollama in middleware.py:

```python
async def llm_callback(prompt: str, message: dict) -> dict:
    # Direct Ollama call here
    ...
```

---

## 🔐 Security Features

### Prompt Injection Detection

The middleware includes 152 security patterns to block:
- Direct override attempts ("ignore all previous instructions")
- Role manipulation ("you are now...")
- Jailbreak attempts ("DAN", "developer mode")
- Context injection (`<system>`, `[INST]`)
- Control characters and ANSI escapes
- And many more...

**To load default security patterns:**
```bash
# The middleware will auto-load when you run it
python middleware.py --load-defaults
```

### Rate Limiting

Uses token bucket algorithm:
- `requests_per_minute` - Sustained rate
- `burst_limit` - Allows temporary higher usage

### Input Sanitization

- Removes control characters (0x00-0x1F)
- Strips ANSI escape sequences
- Removes zero-width characters
- Normalizes whitespace
- Truncates very long inputs

---

## ⚙️ Advanced Configuration

### Rate Limiting

```yaml
rate_limit:
  requests_per_minute: 10
  burst_limit: 20
```

### Content Moderation (Optional)

```yaml
moderation:
  enabled: true
  api_key: "your-moderation-api-key"
  block_threshold: 0.9
  flag_threshold: 0.7
```

### Custom Block Patterns

```yaml
block_patterns:
  - "(?i)spam-pattern"
  - "^ignore\\s+all\\s+previous"
```

---

## 📦 Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install pyyaml discord.py aiohttp

# Copy and edit config
cp config.yaml.example config.yaml
# Edit config.yaml with your settings

# Run brain server (one terminal)
python nyx-brain.py

# Run middleware (another terminal)
python middleware.py --config config.yaml
```

---

## 📝 Logging

- `middleware.log` - General application logs
- `audit.log` - Security audit trail
- `nyx-brain.log` - Brain server logs (if using brain server)

---

## 🔧 Programmatic Usage

```python
from middleware import DiscordMiddleware

# Initialize
middleware = DiscordMiddleware("config.yaml")

# Set your LLM callback
async def my_llm(prompt, message):
    # Call your LLM here
    return {"type": "success", "content": "Response"}

middleware.set_llm_callback(my_llm)

# Process messages
result = await middleware.process_message({
    "author": {"id": "123"},
    "channel_id": "456",
    "guild_id": "789",
    "content": "Hello!"
})
```

---

## 🔄 OpenClaw Integration (Future)

The goal is to connect this middleware directly to OpenClaw. When that's working, the architecture will be:

```
Discord ↔ Middleware ↔ OpenClaw
```

Currently, you can use Ollama as a placeholder. The brain server (`nyx-brain.py`) can be modified to call OpenClaw's API when available.

---

## License

MIT
