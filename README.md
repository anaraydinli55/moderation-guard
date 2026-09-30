# ModerationGuard

Consensus-bound AI content moderation primitive on GenLayer, with an explicit
on-chain policy engine, independent dual-pass evidence aggregation, an open
challenge mechanism, and compounding domain-reputation state.

## Contract (`ModerationGuard.py`)

- `moderateContent(url, content_type)` — write. Validators independently fetch
  the URL and run **two** independently-framed LLM passes (subtle vs. overt
  violations) scoring each of 6 policy categories (hate_speech, harassment,
  violence, misinformation, explicit_content, spam) from 0.0–1.0. The two
  passes' scores are combined by `max()` per category. The final SAFE /
  WARNING / HARMFUL bucket is then derived **in contract code** from fixed
  thresholds (`HARMFUL_THRESHOLD=0.7`, `WARNING_THRESHOLD=0.4`) — the LLM
  never supplies the verdict bucket directly.
- `challengeModeration(mod_id, counter_evidence_url, counter_argument)` —
  write, callable by **any address**, not just the original creator. Puts the
  original evidence and the challenger's counter-evidence before validator
  consensus together, and records an explicit `UPHELD` / `OVERTURNED`
  outcome — it does not silently re-run/overwrite the original evaluation.
  Capped at 3 challenges per moderation.
- Domain reputation: each `HARMFUL` verdict increments a per-domain strike
  counter (`getDomainStrikes`); after 3 strikes the domain is blacklisted
  (`isDomainBlacklisted`) and future `moderateContent` calls for that domain
  short-circuit straight to `HARMFUL` without re-spending consensus — a
  genuine compounding effect across calls, not an independent one-off record.
- `getModeration(id)`, `getAllModerations()`, `getModerationsByVerdict(v)`,
  `getModerationsByType(t)`, `getStats()`

## Testing

```bash
pip install -r requirements.txt
pytest tests/ -v          # 20/20, mocked GenLayer env, no live node needed
python3 scripts/check.py  # syntax + genvm-lint validation
```

## Deployed

- Network: GenLayer Bradbury Testnet
- Address: `TODO — fill in after deploying this exact ModerationGuard.py
  via GenLayer Studio/CLI. The previous address in this file did not match
  what test_eq_principle.mjs actually calls; redeploy and record the real
  Explorer-confirmed address here before resubmitting.`
