# { "Depends": "py-genlayer:15qfivjvy80800rh998pcxmd2m8va1wq2qzqhz850n8ggcr4i9q0" }
from genlayer import *
import json

class ModerationGuard(gl.Contract):
    owner: str = ""
    moderation_count: str = "0"
    moderations: str = "{}"

    def __init__(self):
        self.owner = str(gl.message.sender_address)
        self.moderation_count = "0"
        self.moderations = "{}"

    @gl.public.view
    def getOwner(self):
        return self.owner

    @gl.public.view
    def moderateContent(self, url, content_type="text"):
        """View method: fetches web content and runs LLM moderation analysis. No state change, no consensus needed."""
        valid_types = ["text", "image", "video", "link", "audio"]
        if content_type not in valid_types:
            raise ValueError("Invalid content type")
        
        # Fetch content — failures return UNVERIFIABLE
        try:
            response = gl.nondet.web.get(url)
            if hasattr(response, "body"):
                content = response.body.decode("utf-8")[:4000]
            else:
                content = str(response)[:4000]
        except Exception:
            return {
                "verdict": "UNVERIFIABLE",
                "severity": "0",
                "reasoning": "Failed to fetch URL content",
                "evidence_summary": "",
                "content_snippet": ""
            }
        
        # LLM moderation analysis — parse failures return UNVERIFIABLE
        try:
            prompt = (
                "You are an expert content moderator. Analyze the following webpage content for policy violations.\n\n"
                "CONTENT TYPE: " + content_type + "\n"
                "WEBPAGE CONTENT:\n" + content[:2000] + "\n\n"
                "Evaluate for: hate speech, harassment, misinformation, violence, explicit content, spam, or other policy violations.\n"
                "Respond ONLY with valid JSON in this exact format:\n"
                '{"verdict":"SAFE"|"WARNING"|"HARMFUL"|"UNVERIFIABLE","severity":0.0-1.0,"reasoning":"...","evidence_summary":"..."}'
            )
            result = gl.nondet.exec_prompt(prompt)
            
            if isinstance(result, dict):
                parsed = result
            elif isinstance(result, str):
                cleaned = result.replace("```json", "").replace("```", "").strip()
                parsed = json.loads(cleaned)
            else:
                return {"verdict": "UNVERIFIABLE", "severity": "0", "reasoning": "Invalid LLM response format", "evidence_summary": "", "content_snippet": content[:500]}
            
            verdict = str(parsed.get("verdict", "UNVERIFIABLE")).upper().strip()
            if verdict not in ["SAFE", "WARNING", "HARMFUL", "UNVERIFIABLE"]:
                verdict = "UNVERIFIABLE"
            
            severity = float(parsed.get("severity", 0.0))
            if not (0.0 <= severity <= 1.0):
                severity = 0.0
            
            return {
                "verdict": verdict,
                "severity": str(severity),
                "reasoning": str(parsed.get("reasoning", "")),
                "evidence_summary": str(parsed.get("evidence_summary", "")),
                "content_snippet": content[:500]
            }
        except Exception:
            return {
                "verdict": "UNVERIFIABLE",
                "severity": "0",
                "reasoning": "Failed to parse LLM response",
                "evidence_summary": "",
                "content_snippet": content[:500]
            }

    @gl.public.write
    def submitModeration(self, url, content_type, verdict, severity_pct, reasoning, evidence_summary):
        """Write method: validator logic checks meaningful verdict before storing."""
        # Validator logic: check meaningful verdict
        v = str(verdict).upper().strip()
        if v not in ["SAFE", "WARNING", "HARMFUL", "UNVERIFIABLE"]:
            raise ValueError("Invalid verdict: must be SAFE, WARNING, HARMFUL, or UNVERIFIABLE")
        
        # Validator logic: check severity range
        sev_pct = int(severity_pct)
        if not (0 <= sev_pct <= 100):
            raise ValueError("Invalid severity: must be 0-100")
        
        # Validator logic: check reasoning quality
        if not reasoning or len(str(reasoning).strip()) < 10:
            raise ValueError("Reasoning required: minimum 10 characters")
        
        # Validator logic: check evidence summary
        if not evidence_summary or len(str(evidence_summary).strip()) < 5:
            raise ValueError("Evidence summary required: minimum 5 characters")
        
        # Validator logic: check content type
        valid_types = ["text", "image", "video", "link", "audio"]
        if content_type not in valid_types:
            raise ValueError("Invalid content type")
        
        count = int(self.moderation_count) + 1
        self.moderation_count = str(count)
        mod_id = str(count)
        
        sev = sev_pct / 100.0
        
        m = json.loads(self.moderations) if self.moderations else {}
        m[mod_id] = {
            "id": mod_id,
            "creator": str(gl.message.sender_address),
            "url": url,
            "content_type": content_type,
            "verdict": v,
            "severity": str(sev),
            "reasoning": str(reasoning),
            "evidence_summary": str(evidence_summary),
            "status": "resolved",
            "appeal_count": "0"
        }
        self.moderations = json.dumps(m, sort_keys=True)
        return mod_id

    @gl.public.write
    def appealModeration(self, mod_id, new_url):
        new_url_str = str(new_url).strip()
        if not new_url_str:
            raise ValueError("Replacement URL is required for appeal")
        m = json.loads(self.moderations) if self.moderations else {}
        mid = str(mod_id)
        if mid not in m:
            raise ValueError("Moderation not found")
        mod = m[mid]
        if str(gl.message.sender_address) != mod["creator"]:
            raise ValueError("Only the moderation creator can appeal")
        if mod["status"] == "pending":
            raise ValueError("Moderation is still pending")
        appeal_count = int(mod["appeal_count"])
        if appeal_count >= 3:
            raise ValueError("Maximum appeal count reached")
        appeal_count += 1
        mod["appeal_count"] = str(appeal_count)
        mod["url"] = new_url_str
        mod["status"] = "pending"
        mod["severity"] = "0"
        mod["verdict"] = "PENDING"
        mod["reasoning"] = ""
        mod["evidence_summary"] = ""
        m[mid] = mod
        self.moderations = json.dumps(m, sort_keys=True)
        return "Appeal #" + str(appeal_count) + " submitted successfully"

    @gl.public.view
    def getModeration(self, mod_id):
        m = json.loads(self.moderations) if self.moderations else {}
        mid = str(mod_id)
        if mid not in m:
            raise ValueError("Moderation not found")
        return m[mid]

    @gl.public.view
    def getAllModerations(self):
        return list(json.loads(self.moderations).values()) if self.moderations else []

    @gl.public.view
    def getModerationsByVerdict(self, verdict):
        m = json.loads(self.moderations) if self.moderations else {}
        return [x for x in m.values() if x["verdict"] == verdict]

    @gl.public.view
    def getModerationsByType(self, content_type):
        m = json.loads(self.moderations) if self.moderations else {}
        return [x for x in m.values() if x["content_type"] == content_type]

    @gl.public.view
    def getStats(self):
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
