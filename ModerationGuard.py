# { "Depends": "py-genlayer:babwp9t37jw9g4j2bccgn14g6x7x9s1f7dsmh7emvz735pz4zxa0" }

import genlayer as gl
import json


class ModerationGuard(gl.contract.Contract):
    owner: str
    policies_json: str
    audits_json: str
    strikes_json: str
    challenges_json: str

    def __init__(self):
        self.owner = "0xCCF031DC9541d1771F5BFfCeF07D9b3bDd168f4f"

        # Explicit On-Chain Policy Rules
        default_policies = {
            "POL_MALWARE_PHISHING": {
                "name": "Malware, Phishing & Deceptive Software",
                "severity": "CRITICAL",
                "strike_penalty": 3,
                "description": "Content distributes harmful binaries, impersonates trusted login portals, or captures credentials."
            },
            "POL_FINANCIAL_SCAM": {
                "name": "Financial Fraud & Deceptive Schemes",
                "severity": "HIGH",
                "strike_penalty": 2,
                "description": "Ponzi schemes, unauthorized drainers, fraudulent token pre-sales, or counterfeit services."
            },
            "POL_HARASSMENT": {
                "name": "Targeted Harassment & Malicious Doxxing",
                "severity": "MEDIUM",
                "strike_penalty": 1,
                "description": "Targeted attacks on individuals, non-consensual personal disclosures, or coordinated abuse."
            },
            "POL_IP_VIOLATION": {
                "name": "Flagrant Copyright & Asset Theft",
                "severity": "LOW",
                "strike_penalty": 1,
                "description": "Unauthorized direct mirroring of copyrighted commercial media or counterfeit brand assets."
            }
        }
        self.policies_json = json.dumps(default_policies)
        self.audits_json = json.dumps({})
        self.strikes_json = json.dumps({})
        self.challenges_json = json.dumps({})

    # -------------------------------------------------------------
    # WRITE: Consensus-Bound Policy Audit
    # -------------------------------------------------------------
    @gl.public.write
    def audit_content(self, target_url: str, policy_id: str) -> str:
        policies = json.loads(self.policies_json)
        if policy_id not in policies:
            raise gl.vm.UserError(f"Unknown policy ID: {policy_id}")

        policy = policies[policy_id]

        def leader_fn():
            # 1. Independent Evidence Extraction
            content_sample = ""
            try:
                rendered = str(gl.nondet.web.render(target_url, mode="text"))
                content_sample = rendered[:2500]
            except Exception:
                try:
                    resp = gl.nondet.web.get(target_url)
                    content_sample = (resp.body or b"")[:2500].decode("utf-8", errors="ignore")
                except Exception:
                    content_sample = "[CONTENT_UNREACHABLE]"

            if not content_sample or content_sample == "[CONTENT_UNREACHABLE]":
                return json.dumps({
                    "verdict": "UNVERIFIABLE",
                    "violation": False,
                    "reason": "Target content could not be fetched or rendered by validators."
                })

            # 2. Multi-Vector Policy Evaluation
            prompt = (
                f"You are a strict decentralized consensus moderation validator.\n"
                f"Examine the target text against the following policy:\n"
                f"POLICY: {policy['name']}\n"
                f"POLICY DESCRIPTION: {policy['description']}\n\n"
                f"CONTENT TO EVALUATE:\n'''{content_sample}'''\n\n"
                f"Answer strictly with a single JSON object without formatting or markdown:\n"
                f'{{"violation": true/false, "verdict": "SAFE" or "VIOLATION", "reason": "<brief_reason_max_20_words>"}}'
            )
            raw_eval = str(gl.nondet.exec_prompt(prompt)).strip()
            return raw_eval

        def validator_fn(lr) -> bool:
            return isinstance(lr, gl.vm.Return)

        evaluation_raw = gl.vm.run_nondet(leader_fn, validator_fn)

        try:
            eval_data = json.loads(evaluation_raw)
        except Exception:
            eval_data = {"verdict": "UNVERIFIABLE", "violation": False, "reason": "Malformed LLM output"}

        audits = json.loads(self.audits_json)
        strikes = json.loads(self.strikes_json)

        current_strikes = strikes.get(target_url, 0)
        is_violation = eval_data.get("violation", False)

        if is_violation:
            penalty = policy.get("strike_penalty", 1)
            current_strikes += penalty
            strikes[target_url] = current_strikes

        # Concrete Restriction State
        status = "CLEAN"
        if current_strikes >= 3:
            status = "BLACKLISTED"
        elif current_strikes == 2:
            status = "QUARANTINED"
        elif current_strikes == 1:
            status = "FLAGGED"

        audits[target_url] = {
            "last_policy": policy_id,
            "verdict": eval_data.get("verdict", "UNVERIFIABLE"),
            "is_violation": is_violation,
            "reasoning": eval_data.get("reason", "No reasoning"),
            "status": status,
            "strikes": current_strikes
        }

        self.audits_json = json.dumps(audits)
        self.strikes_json = json.dumps(strikes)
        return json.dumps(audits[target_url])

    # -------------------------------------------------------------
    # WRITE: Multi-Party Dispute & Challenge Logic
    # -------------------------------------------------------------
    @gl.public.write
    def challenge_verdict(self, target_url: str, claim_type: str, justification: str) -> str:
        """
        claim_type: FALSE_POSITIVE | REMEDIATED | AUTHORIZED_EXCEPTION
        """
        audits = json.loads(self.audits_json)
        if target_url not in audits:
            raise gl.vm.UserError(f"No active moderation record found for {target_url}")

        record = audits[target_url]
        if not record.get("is_violation", False):
            raise gl.vm.UserError(f"Target {target_url} has no recorded violation to appeal.")

        def leader_challenge_eval():
            live_text = ""
            try:
                live_text = str(gl.nondet.web.render(target_url, mode="text"))[:2000]
            except Exception:
                live_text = "[UNABLE_TO_VERIFY_LIVE_STATUS]"

            prompt = (
                f"You are a judicial appeals validator for decentralized moderation.\n"
                f"Original Violation Reason: {record.get('reasoning')}\n"
                f"Appellant Claim Type: {claim_type}\n"
                f"Appellant Justification: {justification}\n"
                f"Current Live Content Snapshot: '''{live_text}'''\n\n"
                f"Determine whether this appeal is justified and should overturn or mitigate the penalty.\n"
                f"Reply strictly with JSON:\n"
                f'{{"overturn": true/false, "decision": "UPHELD" or "OVERTURNED", "appeal_summary": "<max_20_words>"}}'
            )
            return str(gl.nondet.exec_prompt(prompt)).strip()

        def validator_fn(lr) -> bool:
            return isinstance(lr, gl.vm.Return)

        appeal_eval_raw = gl.vm.run_nondet(leader_challenge_eval, validator_fn)

        try:
            appeal_res = json.loads(appeal_eval_raw)
        except Exception:
            appeal_res = {"overturn": False, "decision": "UPHELD", "appeal_summary": "Evaluation parse failure"}

        strikes = json.loads(self.strikes_json)
        challenges = json.loads(self.challenges_json)

        if appeal_res.get("overturn", False):
            strikes[target_url] = max(0, strikes.get(target_url, 0) - 2)
            record["is_violation"] = False
            record["status"] = "CLEAN" if strikes[target_url] == 0 else "FLAGGED"
            record["verdict"] = "APPEAL_APPROVED"
        else:
            record["verdict"] = "APPEAL_REJECTED"

        record["last_appeal"] = appeal_res

        audits[target_url] = record
        challenges[target_url] = {
            "claim_type": claim_type,
            "decision": appeal_res.get("decision"),
            "summary": appeal_res.get("appeal_summary")
        }

        self.audits_json = json.dumps(audits)
        self.strikes_json = json.dumps(strikes)
        self.challenges_json = json.dumps(challenges)
        return json.dumps(record)

    # -------------------------------------------------------------
    # VIEW: Reusable Interface for Other Smart Contracts
    # -------------------------------------------------------------
    @gl.public.view
    def is_allowed(self, target_url: str) -> bool:
        strikes = json.loads(self.strikes_json)
        return strikes.get(target_url, 0) < 3

    @gl.public.view
    def get_compliance_report(self, target_url: str) -> str:
        audits = json.loads(self.audits_json)
        return json.dumps(audits.get(target_url, {
            "target": target_url,
            "status": "UNAUDITED",
            "strikes": 0
        }))

    @gl.public.view
    def get_policies(self) -> str:
        return self.policies_json
