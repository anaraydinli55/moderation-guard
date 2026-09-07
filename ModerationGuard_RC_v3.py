# { "Depends": "py-genlayer:latest" }
from genlayer import *
import json

def _extract_json(s: str) -> str:
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and start < end:
        return s[start:end + 1]
    return ""

class ModerationGuard(gl.Contract):
    owner: str = ""
    moderation_count: str = "0"
    moderations: str = "{}"

    def __init__(self):
        self.owner = str(gl.message.sender_address)
        self.moderation_count = "0"
        self.moderations = "{}"

    @gl.public.write
    def init(self) -> None:
        self.owner = str(gl.message.sender_address)

    @gl.public.view
    def getOwner(self) -> str:
        return self.owner

    @gl.public.write
    def moderateContent(self, url: str, content_type: str = "text") -> str:
        """Intelligent Contract write method: Fetches web content and executes LLM moderation inside validator consensus (eq_principle)."""
        valid_types = ["text", "image", "video", "link", "audio"]
        if content_type not in valid_types:
            raise gl.vm.UserError("Invalid content type")

        def evaluate_consensus():
            try:
                response = gl.nondet.web.render(url, mode="text")
                if hasattr(response, "body"):
                    content = response.body.decode("utf-8")[:4000]
                else:
                    content = str(response)[:4000]
            except Exception:
                content = ""

            if not content:
                return json.dumps({
                    "verdict": "UNVERIFIABLE",
                    "severity": 0.0,
                    "reasoning": "Failed to fetch URL content",
                    "evidence_summary": ""
                }, sort_keys=True)

            prompt = (
                "You are an expert content moderator. Analyze the following webpage content for policy violations.\n\n"
                f"CONTENT TYPE: {content_type}\n"
                f"WEBPAGE CONTENT:\n{content[:2000]}\n\n"
                "Evaluate for: hate speech, harassment, misinformation, violence, explicit content, spam, or other policy violations.\n"
                "Respond ONLY with valid JSON in this exact structure:\n"
                "{\n"
                '    "verdict": "SAFE" | "WARNING" | "HARMFUL" | "UNVERIFIABLE",\n'
                '    "severity": float (0.0 to 1.0),\n'
                '    "reasoning": "explanation of moderation findings",\n'
                '    "evidence_summary": "summary of violation or safe content found"\n'
                "}\n"
                "Do not include any other words or characters, your output must be only raw JSON."
            )
            result = gl.nondet.exec_prompt(prompt)
            json_str = _extract_json(result)

            try:
                parsed = json.loads(json_str) if json_str else {}
            except Exception:
                parsed = {}

            verdict = str(parsed.get("verdict", "UNVERIFIABLE")).upper().strip()
            if verdict not in ["SAFE", "WARNING", "HARMFUL", "UNVERIFIABLE"]:
                verdict = "UNVERIFIABLE"

            try:
                severity = float(parsed.get("severity", 0.0))
                if not (0.0 <= severity <= 1.0):
                    severity = 0.0
            except Exception:
                severity = 0.0

            return json.dumps({
                "verdict": verdict,
                "severity": severity,
                "reasoning": str(parsed.get("reasoning", "")),
                "evidence_summary": str(parsed.get("evidence_summary", ""))
            }, sort_keys=True)

        consensus_result_str = gl.eq_principle.strict_eq(evaluate_consensus)
        res = json.loads(consensus_result_str)

        count = int(self.moderation_count) + 1
        self.moderation_count = str(count)
        mod_id = str(count)

        m = json.loads(self.moderations) if self.moderations else {}
        m[mod_id] = {
            "id": mod_id,
            "creator": str(gl.message.sender_address),
            "url": url,
            "content_type": content_type,
            "verdict": res["verdict"],
            "severity": str(res["severity"]),
            "reasoning": res["reasoning"],
            "evidence_summary": res["evidence_summary"],
            "status": "resolved",
            "appeal_count": "0"
        }
        self.moderations = json.dumps(m, sort_keys=True)
        gl.emit("ContentModerated", {
            "moderation_id": mod_id,
            "creator": str(gl.message.sender_address),
            "verdict": res["verdict"],
            "severity": str(res["severity"])
        })
        return mod_id

    @gl.public.write
    def appealModeration(self, mod_id: str, new_url: str) -> str:
        new_url_str = str(new_url).strip()
        if not new_url_str:
            raise gl.vm.UserError("Replacement URL is required for appeal")

        m = json.loads(self.moderations) if self.moderations else {}
        mid = str(mod_id)
        if mid not in m:
            raise gl.vm.UserError("Moderation not found")

        mod = m[mid]
        if str(gl.message.sender_address) != mod["creator"]:
            raise gl.vm.UserError("Only the moderation creator can appeal")

        appeal_count = int(mod.get("appeal_count", "0"))
        if appeal_count >= 3:
            raise gl.vm.UserError("Maximum appeal count reached")

        content_type = mod.get("content_type", "text")

        def re_evaluate_consensus():
            try:
                response = gl.nondet.web.render(new_url_str, mode="text")
                if hasattr(response, "body"):
                    content = response.body.decode("utf-8")[:4000]
                else:
                    content = str(response)[:4000]
            except Exception:
                content = ""

            if not content:
                return json.dumps({
                    "verdict": "UNVERIFIABLE",
                    "severity": 0.0,
                    "reasoning": "Failed to fetch appeal URL content",
                    "evidence_summary": ""
                }, sort_keys=True)

            prompt = (
                "You are an expert content moderator reviewing an appeal. Analyze the following webpage content.\n\n"
                f"CONTENT TYPE: {content_type}\n"
                f"WEBPAGE CONTENT:\n{content[:2000]}\n\n"
                "Evaluate for policy violations and respond ONLY with valid JSON in this exact structure:\n"
                "{\n"
                '    "verdict": "SAFE" | "WARNING" | "HARMFUL" | "UNVERIFIABLE",\n'
                '    "severity": float (0.0 to 1.0),\n'
                '    "reasoning": "explanation of moderation findings",\n'
                '    "evidence_summary": "summary of findings"\n'
                "}"
            )
            result = gl.nondet.exec_prompt(prompt)
            json_str = _extract_json(result)

            try:
                parsed = json.loads(json_str) if json_str else {}
            except Exception:
                parsed = {}

            verdict = str(parsed.get("verdict", "UNVERIFIABLE")).upper().strip()
            if verdict not in ["SAFE", "WARNING", "HARMFUL", "UNVERIFIABLE"]:
                verdict = "UNVERIFIABLE"

            try:
                severity = float(parsed.get("severity", 0.0))
                if not (0.0 <= severity <= 1.0):
                    severity = 0.0
            except Exception:
                severity = 0.0

            return json.dumps({
                "verdict": verdict,
                "severity": severity,
                "reasoning": str(parsed.get("reasoning", "")),
                "evidence_summary": str(parsed.get("evidence_summary", ""))
            }, sort_keys=True)

        appeal_res_str = gl.eq_principle.strict_eq(re_evaluate_consensus)
        appeal_res = json.loads(appeal_res_str)

        appeal_count += 1
        mod["appeal_count"] = str(appeal_count)
        mod["url"] = new_url_str
        mod["status"] = "resolved"
        mod["verdict"] = appeal_res["verdict"]
        mod["severity"] = str(appeal_res["severity"])
        mod["reasoning"] = appeal_res["reasoning"]
        mod["evidence_summary"] = appeal_res["evidence_summary"]

        m[mid] = mod
        self.moderations = json.dumps(m, sort_keys=True)
        gl.emit("ModerationAppealed", {"moderation_id": mid, "appeal_count": str(appeal_count), "verdict": appeal_res["verdict"]})
        return f"Appeal #{appeal_count} resolved with verdict: {appeal_res['verdict']}"

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
            "safety_rate": str(round(safe / total, 2)) if total > 0 else "0"
        }
