#!/usr/bin/env python3
"""
Discord LLM Middleware - Security-hardened filter between Discord and LLM

Features:
- Per-server and per-channel whitelisting
- Input sanitization
- Rate limiting per user
- Prompt injection detection
- Content moderation hooks
- Audit logging
"""

import asyncio
import logging
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("middleware.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("discord-middleware")


@dataclass
class RateLimitConfig:
    """Rate limiting configuration"""
    requests_per_minute: int = 10
    burst_limit: int = 20


@dataclass
class ModerationConfig:
    """Content moderation configuration"""
    api_key: Optional[str] = None
    enabled: bool = False
    block_threshold: float = 0.9
    flag_threshold: float = 0.7


@dataclass
class Config:
    """Main configuration"""
    allowed_servers: list[str] = field(default_factory=list)
    allowed_channels: list[str] = field(default_factory=list)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    block_patterns: list[str] = field(default_factory=list)
    compiled_patterns: list[re.Pattern] = field(default_factory=list, repr=False)
    moderation: ModerationConfig = field(default_factory=ModerationConfig)
    bot_token: str = ""
    llm_endpoint: str = ""
    llm_api_key: str = ""

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """Load config from YAML file"""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        config = cls()
        config.allowed_servers = data.get('allowed_servers', [])
        config.allowed_channels = data.get('allowed_channels', [])
        config.bot_token = data.get('bot_token', '')
        config.llm_endpoint = data.get('llm_endpoint', '')
        config.llm_api_key = data.get('llm_api_key', '')

        # Rate limit config
        rate_data = data.get('rate_limit', {})
        config.rate_limit = RateLimitConfig(
            requests_per_minute=rate_data.get('requests_per_minute', 10),
            burst_limit=rate_data.get('burst_limit', 20)
        )

        # Block patterns - compile for efficiency
        config.block_patterns = data.get('block_patterns', [])
        for pattern in config.block_patterns:
            try:
                config.compiled_patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                logger.warning(f"Invalid regex pattern '{pattern}': {e}")

        # Moderation config
        mod_data = data.get('moderation', {})
        config.moderation = ModerationConfig(
            api_key=mod_data.get('api_key'),
            enabled=mod_data.get('enabled', False),
            block_threshold=mod_data.get('block_threshold', 0.9),
            flag_threshold=mod_data.get('flag_threshold', 0.7)
        )

        logger.info(f"Loaded config: {len(config.allowed_servers)} servers, "
                   f"{len(config.allowed_channels)} channels")
        return config


class RateLimiter:
    """Per-user rate limiting using token bucket algorithm"""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.buckets: dict[str, dict] = defaultdict(self._create_bucket)

    def _create_bucket(self) -> dict:
        return {
            'tokens': self.config.burst_limit,
            'last_update': time.time()
        }

    def is_allowed(self, user_id: str) -> bool:
        """Check if user is allowed to make a request"""
        bucket = self.buckets[user_id]
        now = time.time()
        elapsed = now - bucket['last_update']

        # Refill tokens based on elapsed time
        refill_rate = self.config.requests_per_minute / 60.0
        bucket['tokens'] = min(
            self.config.burst_limit,
            bucket['tokens'] + elapsed * refill_rate
        )
        bucket['last_update'] = now

        if bucket['tokens'] >= 1:
            bucket['tokens'] -= 1
            return True
        return False

    def get_remaining(self, user_id: str) -> int:
        """Get remaining requests for user"""
        return int(self.buckets[user_id].get('tokens', 0))


class PromptInjectionDetector:
    """Detect prompt injection attempts"""

    # Known injection patterns (security research based)
    INJECTION_PATTERNS = [
        # Direct override attempts
        r'^ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?|commands?|context)',
        r'^forget\s+(everything|all|your)\s+(instructions?|rules?|training)',
        r'^disregard\s+(all\s+)?(previous|prior|above)',
        r'^new\s+instructions?:',
        r'^system\s*[:\-]',

        # Role manipulation
        r'^you\s+are\s+(now|no\s+longer|instead\s+of)',
        r'^act\s+as\s+(if|though)\s+(you\s+are|you\'re)',
        r'^pretend\s+(you\s+are|to\s+be)',
        r'^roleplay\s+as',

        # Jailbreak attempts
        r'^ DAN\s',
        r'^developer\s+mode',
        r'^jailbreak',
        r'^bypass\s+(safety|restrictions?|filters?)',

        # Context injection
        r'<\s*system\s*>',
        r'<\s*instruction\s*>',
        r'{{\s*system',
        r'\[INST\]\[INST\]',

        # Output manipulation
        r'^output\s+as\s+(json|code|markdown)',
        r'^respond\s+only\s+with',
        r'^your\s+response\s+should\s+(be|include)',

        # Boundary violations
        r'\x00',  # Null bytes
        r'\x1b\[',  # ANSI escape sequences
    ]

    def __init__(self):
        self.compiled_patterns = [
            re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            for pattern in self.INJECTION_PATTERNS
        ]

        # Token boundary patterns for advanced detection
        self.token_boundary_patterns = [
            re.compile(r'(?:^|\s)system(?:\s|$|:)', re.IGNORECASE),
            re.compile(r'(?:^|\s)assistant(?:\s|$|:)', re.IGNORECASE),
            re.compile(r'(?:^|\s)user(?:\s|$|:)', re.IGNORECASE),
        ]

    def detect(self, text: str) -> tuple[bool, Optional[str]]:
        """
        Detect prompt injection attempts
        Returns: (is_injection, reason)
        """
        if not text:
            return False, None

        # Check compiled patterns
        for i, pattern in enumerate(self.compiled_patterns):
            if pattern.search(text):
                return True, f"Pattern match: {self.INJECTION_PATTERNS[i][:50]}"

        # Check for suspicious token boundaries
        for pattern in self.token_boundary_patterns:
            matches = pattern.findall(text)
            if len(matches) > 2:  # Multiple role switches are suspicious
                return True, f"Multiple role switches detected ({len(matches)})"

        # Check for encoding attempts
        if text != text.strip():
            # Check for unusual whitespace
            if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', text):
                return True, "Control characters detected"

        # Check for very long inputs (potential buffer overflow)
        if len(text) > 10000:
            return True, f"Input too long ({len(text)} chars)"

        return False, None


class InputSanitizer:
    """Sanitize user input"""

    # Characters that could cause issues
    STRIP_PATTERNS = [
        (r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ''),  # Control chars
        (r'\x1b\[[0-9;]*[a-zA-Z]', ''),  # ANSI escape sequences
        (r'[\u200b-\u200f\u2028-\u202f]', ''),  # Zero-width chars
    ]

    @classmethod
    def sanitize(cls, text: str) -> str:
        """Sanitize input text"""
        if not text:
            return ""

        sanitized = text

        # Apply strip patterns
        for pattern, replacement in cls.STRIP_PATTERNS:
            sanitized = re.sub(pattern, replacement, sanitized)

        # Normalize whitespace
        sanitized = ' '.join(sanitized.split())

        # Limit length
        max_length = 8000
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length] + "... [truncated]"

        return sanitized


class ContentModerator:
    """Content moderation using external API or local checks"""

    def __init__(self, config: ModerationConfig):
        self.config = config
        self._client = None

    async def moderate(self, text: str) -> tuple[bool, float, str]:
        """
        Moderate content
        Returns: (is_safe, score, category)
        """
        if not self.config.enabled:
            return True, 0.0, "disabled"

        # Basic local checks first
        local_result = self._local_check(text)
        if local_result:
            return local_result

        # External API check (placeholder - implement based on provider)
        if self.config.api_key:
            return await self._api_check(text)

        return True, 0.0, "no_api"

    def _local_check(self, text: str) -> Optional[tuple[bool, float, str]]:
        """Basic local content checks"""
        # Check for excessive caps
        if len(text) > 20:
            caps_ratio = sum(1 for c in text if c.isupper()) / len(text)
            if caps_ratio > 0.8:
                return False, 0.85, "excessive_caps"

        # Check for repeated characters
        if re.search(r'(.)\1{5,}', text):
            return False, 0.6, "repeated_chars"

        return None

    async def _api_check(self, text: str) -> tuple[bool, float, str]:
        """External API check - implement based on provider"""
        # Placeholder for API integration (e.g., OpenAI Moderation API)
        # Example:
        # async with aiohttp.ClientSession() as session:
        #     async with session.post(
        #         'https://api.openai.com/v1/moderations',
        #         headers={'Authorization': f'Bearer {self.config.api_key}'},
        #         json={'input': text}
        #     ) as resp:
        #         result = await resp.json()
        #         ...
        return True, 0.0, "not_implemented"


class AuditLogger:
    """Audit logging for security events"""

    def __init__(self, log_file: str = "audit.log"):
        self.log_file = log_file
        self._setup_logger()

    def _setup_logger(self):
        self.audit_logger = logging.getLogger("audit")
        self.audit_logger.setLevel(logging.INFO)

        # File handler
        handler = logging.FileHandler(self.log_file)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(message)s")
        )
        self.audit_logger.addHandler(handler)

    def log(self, event_type: str, **kwargs):
        """Log an audit event"""
        details = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        self.audit_logger.info(f"{event_type} | {details}")

    def log_message(self, user_id: str, channel_id: str, server_id: str,
                    action: str, details: str = ""):
        self.log("MESSAGE", user_id=user_id, channel_id=channel_id,
                server_id=server_id, action=action, details=details)

    def log_block(self, user_id: str, reason: str, content_preview: str = ""):
        self.log("BLOCK", user_id=user_id, reason=reason,
                content=content_preview[:100])

    def log_rate_limit(self, user_id: str, remaining: int):
        self.log("RATE_LIMIT", user_id=user_id, remaining=remaining)

    def log_injection(self, user_id: str, pattern: str):
        self.log("INJECTION", user_id=user_id, pattern=pattern[:50])


class DiscordMiddleware:
    """Main middleware class"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config = Config.from_yaml(config_path)
        self.rate_limiter = RateLimiter(self.config.rate_limit)
        self.injection_detector = PromptInjectionDetector()
        self.sanitizer = InputSanitizer()
        self.moderator = ContentModerator(self.config.moderation)
        self.audit_logger = AuditLogger()

        # Callback for LLM processing
        self.llm_callback: Optional[Callable] = None

    def set_llm_callback(self, callback: Callable[[str], Any]):
        """Set the LLM processing callback"""
        self.llm_callback = callback

    def is_allowed_server(self, server_id: str) -> bool:
        """Check if server is allowed"""
        if not self.config.allowed_servers:
            return True  # Allow all if no whitelist
        return server_id in self.config.allowed_servers

    def is_allowed_channel(self, channel_id: str) -> bool:
        """Check if channel is allowed"""
        if not self.config.allowed_channels:
            return True  # Allow all if no whitelist
        return channel_id in self.config.allowed_channels

    async def process_message(self, message: dict) -> Optional[dict]:
        """
        Process a Discord message through the middleware
        Returns: Response dict or None if blocked
        """
        user_id = str(message.get('author', {}).get('id', ''))
        channel_id = str(message.get('channel_id', ''))
        server_id = str(message.get('guild_id', ''))
        content = message.get('content', '')

        # 1. Check server whitelist
        if not self.is_allowed_server(server_id):
            self.audit_logger.log_message(user_id, channel_id, server_id,
                                          "BLOCKED", "Server not allowed")
            return None

        # 2. Check channel whitelist
        if not self.is_allowed_channel(channel_id):
            self.audit_logger.log_message(user_id, channel_id, server_id,
                                          "BLOCKED", "Channel not allowed")
            return None

        # 3. Rate limiting
        if not self.rate_limiter.is_allowed(user_id):
            remaining = self.rate_limiter.get_remaining(user_id)
            self.audit_logger.log_rate_limit(user_id, remaining)
            return {
                'type': 'rate_limited',
                'message': f"Rate limit exceeded. Try again later. ({remaining} remaining)"
            }

        # 4. Sanitize input
        sanitized_content = self.sanitizer.sanitize(content)

        # 5. Prompt injection detection
        is_injection, injection_reason = self.injection_detector.detect(sanitized_content)
        if is_injection:
            self.audit_logger.log_injection(user_id, injection_reason)
            return {
                'type': 'blocked',
                'message': "Message blocked by security filters."
            }

        # 6. Block pattern matching
        for pattern in self.config.compiled_patterns:
            if pattern.search(sanitized_content):
                self.audit_logger.log_block(user_id, "Pattern match",
                                            sanitized_content)
                return {
                    'type': 'blocked',
                    'message': "Message blocked by content filters."
                }

        # 7. Content moderation
        is_safe, score, category = await self.moderator.moderate(sanitized_content)
        if not is_safe:
            self.audit_logger.log_block(user_id, f"Moderation: {category}",
                                        sanitized_content)
            return {
                'type': 'flagged',
                'message': "Message flagged for review."
            }

        # 8. Pass to LLM if callback is set
        response = None
        if self.llm_callback:
            try:
                response = await self.llm_callback(sanitized_content, message)
            except Exception as e:
                logger.error(f"LLM callback error: {e}")
                return {
                    'type': 'error',
                    'message': "Error processing request."
                }

        # 9. Moderate LLM response
        if response and isinstance(response, dict):
            response_content = response.get('content', '')
            is_safe, score, category = await self.moderator.moderate(response_content)
            if not is_safe:
                self.audit_logger.log_block("LLM", f"Response: {category}",
                                            response_content)
                return {
                    'type': 'flagged',
                    'message': "Response flagged for review."
                }

        self.audit_logger.log_message(user_id, channel_id, server_id,
                                      "ALLOWED", f"Length: {len(sanitized_content)}")

        return response or {
            'type': 'success',
            'content': sanitized_content
        }


# Example usage with discord.py
async def run_bot_example():
    """Example of running the middleware with discord.py"""
    import discord
    from discord import app_commands

    # Initialize middleware
    middleware = DiscordMiddleware("config.yaml")

    # Set up LLM callback
    async def llm_callback(prompt: str, message: dict) -> dict:
        # Call your LLM here
        # response = await call_your_llm(prompt)
        return {
            'type': 'success',
            'content': f"Echo: {prompt}"
        }

    middleware.set_llm_callback(llm_callback)

    # Create bot
    intents = discord.Intents.default()
    intents.message_content = True
    bot = discord.Client(intents=intents)
    tree = app_commands.CommandTree(bot)

    @bot.event
    async def on_message(message: discord.Message):
        # Ignore bot messages
        if message.author.bot:
            return

        # Build message dict
        msg_dict = {
            'author': {'id': str(message.author.id)},
            'channel_id': str(message.channel.id),
            'guild_id': str(message.guild.id) if message.guild else '',
            'content': message.content
        }

        # Process through middleware
        result = await middleware.process_message(msg_dict)

        if result:
            if result['type'] == 'success':
                # Send LLM response
                await message.reply(result.get('content', ''))
            elif result['type'] == 'rate_limited':
                await message.reply(result['message'], ephemeral=True)
            elif result['type'] in ('blocked', 'flagged'):
                await message.reply(result['message'], ephemeral=True)

    @bot.event
    async def on_ready():
        await tree.sync()
        logger.info(f"Bot ready as {bot.user}")

    # Run bot
    await bot.start(middleware.config.bot_token)


if __name__ == "__main__":
    # Run example
    asyncio.run(run_bot_example())
