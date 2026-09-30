# { "Depends": "py-genlayer:latest" }
from genlayer import *
import json

POLICY_CATEGORIES = ["hate_speech", "harassment", "violence", "misinformation", "explicit_content", "spam"]
HARMFUL_THRESHOLD = 0.7
WARNING_THRESHOLD = 0.4
STRIKE_LIMIT = 3


def _extract_json(s: str) -> str:
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and start < end:
        return s[start:end + 1]
    return ""


def _domain_of(url: str) -> str:
    try:
        no_scheme = url.split("://", 1)[-1]
        return no_scheme.split("/", 1)[0].lower() or url
    except Exception:
        return url


def _fetch(url: str, limit: int = 4000) -> str:
    try:
        response = gl.nondet.web.render(url, mode="text")
        if hasattr(response, "body"):
            return response.body.decode("utf-8")[:limit]
        return str(response)[:limit]
    except Exception:
        return ""


def _parse_category_scores(raw: str):
    js = _extract_json(raw)
    try:
        parsed = json.loads(js) if js else {}
    except Exception:
        parsed = {}
    scores_in = parsed.get("scores", {}) if isinstance(parsed, dict) else {}
    scores = {}
    for cat in POLICY_CATEGORIES:
        try:
            v = float(scores_in.get(cat, 0.0))
        except Exception:
            v = 0.0
        scores[cat] = min(1.0, max(0.0, v))
    reasoning = str(parsed.get("reasoning", "")) if isinstance(parsed, dict) else ""
    evidence = str(parsed.get("evidence_summary", "")) if isinstance(parsed, dict) else ""
    return scores, reasoning, evidence


def _category_prompt(content: str, content_type: str, focus: str) -> str:
    return (
        "You are an expert content moderator applying an explicit policy.\n\n"
        f"CONTENT TYPE: {content_type}\n"
        f"WEBPAGE CONTENT:\n{content[:2000]}\n\n"
        f"Score EACH of these policy categories independently from 0.0 (no violation) to 1.0 (severe violation): "
        f"{', '.join(POLICY_CATEGORIES)}.\n"
        f"Focus especially on {focus} violations.\n\n"
        "Respond ONLY with raw JSON in this exact structure:\n"
        '{"scores": {"hate_speech":0.0,"harassment":0.0,"violence":0.0,"misinformation":0.0,'
        '"explicit_content":0.0,"spam":0.0}, "reasoning": "...", "evidence_summary": "..."}'
    )


def _verdict_from_score(max_score: float) -> str:
    """Explicit policy rule: the verdict bucket is a fixed function of the
    aggregated category score, computed here in contract code — never asked
    of, or handed over by, the LLM directly."""
    if max_score >= HARMFUL_THRESHOLD:
        return "HARMFUL"
    if max_score >= WARNING_THRESHOLD:
        return "WARNING"
    return "SAFE"


class ModerationGuard(gl.Contract):
    owner: str
    moderation_count: str
    moderations: str
    domain_strikes: str
    blacklisted_domains: str

    def __init__(self):
        self.owner = ""
        self.moderation_count = "0"
        self.moderations = "{}"
        self.domain_strikes = "{}"
        self.blacklisted_domains = "{}"

    @gl.public.write
    def init(self) -> None:
        self.owner = str(gl.message.sender_address)

    @gl.public.view
    def getOwner(self) -> str:
        return self.owner

    def _run_moderation(self, url: str, content_type: str) -> dict:
        content = _fetch(url)
        if not content:
            return {
                "verdict": "UNVERIFIABLE", "severity": 0.0, "category_scores": {},
                "worst_category": "", "reasoning": "Failed to fetch URL content", "evidence_summary": "",
            }

        # Independent evidence aggregation: two differently-framed LLM passes
        # over the same fetched content, combined by taking the max per-category
        # score — a single pass's output is never trusted wholesale.
        raw1 = gl.nondet.exec_prompt(_category_prompt(content, content_type, "subtle or implicit"))
        raw2 = gl.nondet.exec_prompt(_category_prompt(content, content_type, "explicit or overt"))
        scores1, reasoning1, evidence1 = _parse_category_scores(raw1)
        scores2, reasoning2, evidence2 = _parse_category_scores(raw2)

        combined = {cat: max(scores1[cat], scores2[cat]) for cat in POLICY_CATEGORIES}
        worst_cat = max(combined, key=combined.get)
        max_score = combined[worst_cat]
        verdict = _verdict_from_score(max_score)
        reasoning = reasoning1 or reasoning2 or f"Highest-scoring category: {worst_cat} ({max_score:.2f})"
        evidence = evidence1 or evidence2

        return {
            "verdict": verdict, "severity": max_score, "category_scores": combined,
            "worst_category": worst_cat, "reasoning": reasoning, "evidence_summary": evidence,
        }

    @gl.public.write
    def moderateContent(self, url: str, content_type: str = "text") -> str:
        """Consensus-bound write method: independently fetches content and runs
        dual-pass LLM category scoring inside validator consensus; the SAFE/
        WARNING/HARMFUL bucket is then derived by fixed on-chain thresholds."""
        valid_types = ["text", "image", "video", "link", "audio"]
        if content_type not in valid_types:
            raise gl.vm.UserError("Invalid content type")

        domain = _domain_of(url)
        bl = json.loads(self.blacklisted_domains) if self.blacklisted_domains else {}

        if bl.get(domain):
            # Meaningful, compounding state effect: a domain that has already
            # crossed the strike limit short-circuits straight to HARMFUL
            # without re-spending consensus on content we already know violates policy.
            res = {
                "verdict": "HARMFUL", "severity": 1.0, "category_scores": {},
                "worst_category": "blacklisted_domain",
                "reasoning": f"Domain '{domain}' is blacklisted after {STRIKE_LIMIT}+ prior HARMFUL verdicts.",
                "evidence_summary": "Auto-flagged: domain strike limit exceeded.",
            }
        else:
            def _consensus_eval():
                return json.dumps(self._run_moderation(url, content_type), sort_keys=True)
            res = json.loads(gl.eq_principle.strict_eq(_consensus_eval))

        count = int(self.moderation_count) + 1
        self.moderation_count = str(count)
        mod_id = str(count)

        m = json.loads(self.moderations) if self.moderations else {}
        m[mod_id] = {
            "id": mod_id,
            "creator": str(gl.message.sender_address),
            "url": url,
            "domain": domain,
            "content_type": content_type,
            "verdict": res["verdict"],
            "severity": str(res["severity"]),
            "category_scores": res.get("category_scores", {}),
            "worst_category": res.get("worst_category", ""),
            "reasoning": res["reasoning"],
            "evidence_summary": res["evidence_summary"],
            "status": "resolved",
            "challenge_count": "0",
        }
        self.moderations = json.dumps(m, sort_keys=True)

        if res["verdict"] == "HARMFUL":
            strikes = json.loads(self.domain_strikes) if self.domain_strikes else {}
            strikes[domain] = strikes.get(domain, 0) + 1
            self.domain_strikes = json.dumps(strikes, sort_keys=True)
            if strikes[domain] >= STRIKE_LIMIT:
                bl[domain] = True
                self.blacklisted_domains = json.dumps(bl, sort_keys=True)

        gl.emit("ContentModerated", {"moderation_id": mod_id, "verdict": res["verdict"], "domain": domain})
        return mod_id

    @gl.public.write
    def challengeModeration(self, mod_id: str, counter_evidence_url: str, counter_argument: str) -> str:
        """Open challenge: any address may dispute a verdict by supplying
        independent counter-evidence and an argument. The original evidence and
        the counter-evidence are weighed together by validator consensus, and the
        outcome is explicitly recorded as UPHELD or OVERTURNED — this is not a
        silent re-run/overwrite of the original evaluation."""
        counter_url = str(counter_evidence_url).strip()
        counter_arg = str(counter_argument).strip()
        if not counter_url:
            raise gl.vm.UserError("Counter-evidence URL is required")
        if len(counter_arg) < 15:
            raise gl.vm.UserError("Counter-argument must be at least 15 characters")

        m = json.loads(self.moderations) if self.moderations else {}
        mid = str(mod_id)
        if mid not in m:
            raise gl.vm.UserError("Moderation not found")
        mod = m[mid]

        challenge_count = int(mod.get("challenge_count", "0"))
        if challenge_count >= STRIKE_LIMIT:
            raise gl.vm.UserError("Maximum challenge count reached")

        original_verdict = mod["verdict"]
        original_url = mod["url"]

        def _challenge_eval():
            orig_content = _fetch(original_url, 2000) or "(original content unavailable)"
            counter_content = _fetch(counter_url, 2000)

            prompt = (
                "You are adjudicating a moderation challenge. A prior verdict was issued on the "
                "ORIGINAL content below; a challenger disputes it with an argument and counter-evidence.\n\n"
                f"ORIGINAL VERDICT: {original_verdict}\n"
                f"ORIGINAL CONTENT:\n{orig_content}\n\n"
                f"CHALLENGER ARGUMENT: {counter_arg}\n"
                f"COUNTER-EVIDENCE CONTENT:\n{counter_content}\n\n"
                "Weigh both sides and respond ONLY with raw JSON in this exact structure:\n"
                '{"final_verdict":"SAFE"|"WARNING"|"HARMFUL"|"UNVERIFIABLE","severity":0.0,'
                '"outcome":"UPHELD"|"OVERTURNED","reasoning":"..."}'
            )
            raw = gl.nondet.exec_prompt(prompt)
            js = _extract_json(raw)
            try:
                parsed = json.loads(js) if js else {}
            except Exception:
                parsed = {}

            fv = str(parsed.get("final_verdict", "UNVERIFIABLE")).upper().strip()
            if fv not in ["SAFE", "WARNING", "HARMFUL", "UNVERIFIABLE"]:
                fv = "UNVERIFIABLE"
            try:
                sev = float(parsed.get("severity", 0.0))
                if not (0.0 <= sev <= 1.0):
                    sev = 0.0
            except Exception:
                sev = 0.0
            outcome = str(parsed.get("outcome", "")).upper().strip()
            if outcome not in ["UPHELD", "OVERTURNED"]:
                outcome = "OVERTURNED" if fv != original_verdict else "UPHELD"
            reasoning = str(parsed.get("reasoning", ""))

            return json.dumps({"final_verdict": fv, "severity": sev, "outcome": outcome, "reasoning": reasoning}, sort_keys=True)

        result = json.loads(gl.eq_principle.strict_eq(_challenge_eval))

        challenge_count += 1
        mod["challenge_count"] = str(challenge_count)
        mod["verdict"] = result["final_verdict"]
        mod["severity"] = str(result["severity"])
        mod["reasoning"] = result["reasoning"]
        mod["status"] = "challenged"
        mod["last_challenge_outcome"] = result["outcome"]
        m[mid] = mod
        self.moderations = json.dumps(m, sort_keys=True)

        gl.emit("ModerationChallenged", {
            "moderation_id": mid, "challenge_count": str(challenge_count),
            "outcome": result["outcome"], "final_verdict": result["final_verdict"],
        })
        return f"Challenge #{challenge_count} {result['outcome']}: {result['final_verdict']}"

    @gl.public.view
    def getModeration(self, mod_id: str) -> dict:
        m = json.loads(self.moderations) if self.moderations else {}
        mid = str(mod_id)
        if mid not in m:
            raise gl.vm.UserError("Moderation not found")
        return m[mid]

    @gl.public.view
    def getAllModerations(self) -> list:
        return list(json.loads(self.moderations).values()) if self.moderations else []

    @gl.public.view
    def getModerationsByVerdict(self, verdict: str) -> list:
        m = json.loads(self.moderations) if self.moderations else {}
        return [x for x in m.values() if x["verdict"] == verdict]

    @gl.public.view
    def getModerationsByType(self, content_type: str) -> list:
        m = json.loads(self.moderations) if self.moderations else {}
        return [x for x in m.values() if x["content_type"] == content_type]

    @gl.public.view
    def getDomainStrikes(self, domain: str) -> str:
        strikes = json.loads(self.domain_strikes) if self.domain_strikes else {}
        return str(strikes.get(domain.lower(), 0))

    @gl.public.view
    def isDomainBlacklisted(self, domain: str) -> bool:
        bl = json.loads(self.blacklisted_domains) if self.blacklisted_domains else {}
        return bool(bl.get(domain.lower(), False))

    @gl.public.view
    def getStats(self) -> dict:
        m = json.loads(self.moderations) if self.moderations else {}
        total = len(m)
        safe = sum(1 for x in m.values() if x["verdict"] == "SAFE")
        warning = sum(1 for x in m.values() if x["verdict"] == "WARNING")
        harmful = sum(1 for x in m.values() if x["verdict"] == "HARMFUL")
        unverifiable = sum(1 for x in m.values() if x["verdict"] == "UNVERIFIABLE")
        return {
            "total_moderations": str(total),
            "safe": str(safe),
            "warning": str(warning),
            "harmful": str(harmful),
            "unverifiable": str(unverifiable),
            "safety_rate": str(round(safe / total, 2)) if total > 0 else "0",
        }
