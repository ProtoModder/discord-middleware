# Discord LLM Middleware

A security-hardened middleware for Discord that filters messages between Discord and your LLM. Features per-server/channel whitelisting, rate limiting, prompt injection detection, and content moderation.

## Features

- **Per-server/channel whitelisting** - Only process messages from allowed servers and channels
- **Rate limiting** - Token bucket algorithm per user to prevent abuse
- **Prompt injection detection** - Blocks known jailbreak and injection patterns
- **Input sanitization** - Strips control characters, ANSI codes, zero-width chars
- **Content moderation** - Optional API-based moderation (OpenAI compatible)
- **Audit logging** - Full audit trail for security review

## Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install pyyaml discord.py aiohttp
```

## Configuration

1. Copy the example config:
```bash
cp config.yaml.example config.yaml
```

2. Edit `config.yaml` with your settings:

```yaml
# Discord Bot Token (get from https://discord.com/developers/applications)
bot_token: "YOUR_BOT_TOKEN"

# LLM endpoint (Ollama example)
llm_endpoint: "http://localhost:11434/api/generate"

# Server whitelist - Discord server IDs to allow
allowed_servers:
  - "123456789012345678"

# Channel whitelist - Discord channel IDs to allow  
allowed_channels:
  - "111222333444555666"

# Rate limiting
rate_limit:
  requests_per_minute: 10
  burst_limit: 20

# Block patterns (regex)
block_patterns:
  - "(?i)spam-pattern"

# Content moderation (optional)
moderation:
  enabled: false
  api_key: ""
```

### Getting Discord IDs

To get server/channel IDs:
1. Enable Developer Mode in Discord (Settings > Advanced > Developer Mode)
2. Right-click on a server/channel and select "Copy ID"

## How to Connect

### Option 1: Standalone Bot (recommended)

1. Create a Discord bot at https://discord.com/developers
2. Get your bot token
3. Add the token to `config.yaml`
4. Run the middleware
5. Use the OAuth2 URL or invite link to add the bot to your server

### Option 2: Proxy (for existing OpenClaw)

1. Configure OpenClaw to use the middleware endpoint
2. Messages route through middleware first
3. Filtered then back to OpenClaw

### Example Config

```yaml
servers:
  - id: "1477370800972501126"
    enabled: true
    channels:
      - "1478239758064029787"
```

### Running

```bash
pip install -r requirements.txt
cp config.yaml.example config.yaml
# Edit config.yaml with your settings
python middleware.py
```

## Running the Bot

```bash
# Run the bot
python middleware.py
```

Or import and use programmatically:

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

## Security Features

### Prompt Injection Detection

Blocks messages containing:
- Direct override attempts ("ignore all previous instructions")
- Role manipulation ("you are now...")
- Jailbreak attempts ("DAN", "developer mode")
- Context injection (`<system>`, `[INST]`)
- Control characters and ANSI escapes

### Input Sanitization

- Removes control characters (0x00-0x1F)
- Strips ANSI escape sequences
- Removes zero-width characters
- Normalizes whitespace
- Truncates very long inputs

### Rate Limiting

Uses token bucket algorithm:
- Sustained rate: `requests_per_minute`
- Burst limit: `burst_limit` (allows temporary higher usage)

## Logging

- `middleware.log` - General application logs
- `audit.log` - Security audit trail

## Extending

### Custom Moderation

Implement your own moderation in the `ContentModerator` class or override:

```python
class CustomModerator(ContentModerator):
    async def _api_check(self, text: str):
        # Your custom API logic
        pass
```

### Custom LLM Integration

Modify the `llm_callback` to connect to any LLM:

```python
async def llm_callback(prompt, message):
    # OpenAI
    response = await openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Ollama
    # response = await ollama.chat(model="llama2", messages=[...])
    
    return {"type": "success", "content": response.choices[0].message.content}
```

## License

MIT
