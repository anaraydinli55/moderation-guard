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

        default_policies = {
            "POL_MALWARE_PHISHING": {
                "name": "Malware, Phishing & Deceptive Software",
                "severity": "CRITICAL",
                "strike_penalty": 3,
                "description": "Content distributes harmful binaries, impersonates trusted portals, or captures credentials."
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
                "description": "Unauthorized direct mirroring of copyrighted media or counterfeit brand assets."
            }
        }
        self.policies_json = json.dumps(default_policies)
        self.audits_json = json.dumps({})
        self.strikes_json = json.dumps({})
        self.challenges_json = json.dumps({})

    # -------------------------------------------------------------
    # WRITE: Consensus-Bound Policy Audit (Independent Re-fetch & Re-eval)
    # -------------------------------------------------------------
    @gl.public.write
    def audit_content(self, target_url: str, policy_id: str) -> str:
        policies = json.loads(self.policies_json)
        if policy_id not in policies:
            raise gl.vm.UserError(f"Unknown policy ID: {policy_id}")

        policy = policies[policy_id]

        def _fetch_and_eval(url: str, pol_name: str, pol_desc: str) -> str:
            content = ""
            try:
                resp = gl.nondet.web.get(url)
                content = (resp.body or b"")[:3000].decode("utf-8", errors="ignore")
            except Exception:
                return "UNVERIFIABLE"

            if not content:
                return "UNVERIFIABLE"

            prompt = (
                f"You are an impartial decentralized content moderation validator.\n"
                f"Policy Name: {pol_name}\n"
                f"Policy Rule: {pol_desc}\n\n"
                f"Web Content Sample:\n'''{content}'''\n\n"
                f"Does this web content violate the specified policy rule?\n"
                f"Answer strictly with a single uppercase word: VIOLATION or SAFE."
            )
            res = str(gl.nondet.exec_prompt(prompt)).strip().upper()
            if "VIOLATION" in res:
                return "VIOLATION"
            return "SAFE"

        # 1. Leader independently fetches evidence and evaluates
        def leader_fn() -> str:
            return _fetch_and_eval(target_url, policy["name"], policy["description"])

        # 2. Validator independently re-fetches evidence and re-evaluates
        def validator_fn(lr) -> bool:
            if not isinstance(lr, gl.vm.Return):
                return False

            # lr.calldata contains the leader return value
            leader_verdict = lr.calldata

            # Validator independently re-fetches and re-evaluates
            validator_verdict = _fetch_and_eval(target_url, policy["name"], policy["description"])
            return leader_verdict == validator_verdict

        verdict = gl.vm.run_nondet(leader_fn, validator_fn)
        is_violation = (verdict == "VIOLATION")

        audits = json.loads(self.audits_json)
        strikes = json.loads(self.strikes_json)

        current_strikes = strikes.get(target_url, 0)
        if is_violation:
            penalty = policy.get("strike_penalty", 1)
            current_strikes += penalty
            strikes[target_url] = current_strikes

        status = "CLEAN"
        if current_strikes >= 3:
            status = "BLACKLISTED"
        elif current_strikes == 2:
            status = "QUARANTINED"
        elif current_strikes == 1:
            status = "FLAGGED"

        record = {
            "target": target_url,
            "policy": policy_id,
            "verdict": verdict,
            "is_violation": is_violation,
            "status": status,
            "strikes": current_strikes
        }

        audits[target_url] = record
        self.audits_json = json.dumps(audits)
        self.strikes_json = json.dumps(strikes)
        return json.dumps(record)

    # -------------------------------------------------------------
    # WRITE: Multi-Party Dispute (Independent Appeal Consensus)
    # -------------------------------------------------------------
    @gl.public.write
    def challenge_verdict(self, target_url: str, claim_type: str, justification: str) -> str:
        audits = json.loads(self.audits_json)
        if target_url not in audits:
            raise gl.vm.UserError(f"No active record for {target_url}")

        record = audits[target_url]
        if not record.get("is_violation", False):
            raise gl.vm.UserError(f"No recorded violation to appeal for {target_url}")

        def _eval_appeal(url: str, claim: str, just: str) -> str:
            live_text = ""
            try:
                resp = gl.nondet.web.get(url)
                live_text = (resp.body or b"")[:3000].decode("utf-8", errors="ignore")
            except Exception:
                return "UPHELD"

            prompt = (
                f"You are an impartial judicial appeals validator for content moderation.\n"
                f"Appellant Claim Type: {claim}\n"
                f"Appellant Justification: {just}\n"
                f"Live Page Content:\n'''{live_text}'''\n\n"
                f"Should the moderation penalty be overturned based on this claim?\n"
                f"Answer strictly with a single uppercase word: OVERTURN or UPHOLD."
            )
            res = str(gl.nondet.exec_prompt(prompt)).strip().upper()
            if "OVERTURN" in res:
                return "OVERTURN"
            return "UPHELD"

        def leader_appeal_fn() -> str:
            return _eval_appeal(target_url, claim_type, justification)

        def validator_appeal_fn(lr) -> bool:
            if not isinstance(lr, gl.vm.Return):
                return False
            leader_decision = lr.calldata
            validator_decision = _eval_appeal(target_url, claim_type, justification)
            return leader_decision == validator_decision

        decision = gl.vm.run_nondet(leader_appeal_fn, validator_appeal_fn)

        strikes = json.loads(self.strikes_json)
        challenges = json.loads(self.challenges_json)

        if decision == "OVERTURN":
            strikes[target_url] = max(0, strikes.get(target_url, 0) - 2)
            record["is_violation"] = False
            record["status"] = "CLEAN" if strikes[target_url] == 0 else "FLAGGED"
            record["verdict"] = "APPEAL_APPROVED"
        else:
            record["verdict"] = "APPEAL_REJECTED"

        record["last_appeal"] = decision
        audits[target_url] = record
        challenges[target_url] = {
            "claim_type": claim_type,
            "decision": decision
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
            "status": "UNAUDITED",
            "strikes": 0
        }))

    @gl.public.view
    def get_policies(self) -> str:
        return self.policies_json
