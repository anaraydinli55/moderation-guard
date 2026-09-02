# ModerationGuard

AI-powered content moderation primitive on GenLayer.

## Contract
- `moderateContent(url, content_type)` — View method: web fetch + LLM analysis, returns verdict/severity/reasoning
- `submitModeration(url, content_type, verdict, severity_pct, reasoning, evidence_summary)` — Write method: owner-only with validator logic
- `appealModeration(id, new_url)` — Creator appeal with new evidence (max 3)
- `getModeration(id)`, `getAllModerations()`, `getStats()`

## Deployed
- Network: GenLayer Bradbury Testnet
- Address: `0x6BE9F496b3685E71c4A1aA7F929CDf709f7Bb441`
