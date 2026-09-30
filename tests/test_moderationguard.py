import pytest


def _deploy_and_init(direct_deploy, direct_vm, owner):
    mg = direct_deploy("ModerationGuard.py")
    with direct_vm.prank(owner):
        mg.init()
    return mg


def _scores_json(hate=0.0, harassment=0.0, violence=0.0, misinfo=0.0, explicit=0.0, spam=0.0, reasoning="x", evidence="y"):
    import json
    return json.dumps({
        "scores": {
            "hate_speech": hate, "harassment": harassment, "violence": violence,
            "misinformation": misinfo, "explicit_content": explicit, "spam": spam,
        },
        "reasoning": reasoning,
        "evidence_summary": evidence,
    })


class TestInit:
    def test_init_sets_owner(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        assert mg.getOwner() == direct_owner

    def test_starts_empty(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        assert mg.getAllModerations() == []


class TestPolicyThresholds:
    def test_low_scores_are_safe(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        direct_vm.mock_web(r"example\.com", {"body": "A perfectly ordinary article."})
        direct_vm.mock_llm(r".*", _scores_json(hate=0.1, spam=0.2))

        mid = mg.moderateContent("https://example.com/a", "text")
        check = mg.getModeration(mid)
        assert check["verdict"] == "SAFE"

    def test_mid_scores_are_warning(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        direct_vm.mock_web(r"example\.com", {"body": "Some borderline content."})
        direct_vm.mock_llm(r".*", _scores_json(harassment=0.5))

        mid = mg.moderateContent("https://example.com/b", "text")
        assert mg.getModeration(mid)["verdict"] == "WARNING"

    def test_high_scores_are_harmful(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        direct_vm.mock_web(r"example\.com", {"body": "Severely violating content."})
        direct_vm.mock_llm(r".*", _scores_json(violence=0.9))

        mid = mg.moderateContent("https://example.com/c", "text")
        check = mg.getModeration(mid)
        assert check["verdict"] == "HARMFUL"
        assert check["worst_category"] == "violence"

    def test_verdict_is_not_taken_verbatim_from_llm(self, direct_deploy, direct_vm, direct_owner):
        """Even if the LLM free-text tried to assert its own verdict field,
        the contract ignores it and derives the bucket only from category scores."""
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        direct_vm.mock_web(r"example\.com", {"body": "content"})
        direct_vm.mock_llm(r".*", '{"verdict":"SAFE","scores":{"hate_speech":0.95},"reasoning":"x","evidence_summary":"y"}')

        mid = mg.moderateContent("https://example.com/d", "text")
        assert mg.getModeration(mid)["verdict"] == "HARMFUL"


class TestAggregation:
    def test_aggregation_takes_max_across_two_passes(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        direct_vm.mock_web(r"example\.com", {"body": "content"})
        direct_vm.mock_llm(r"subtle", _scores_json(hate=0.2))
        direct_vm.mock_llm(r"explicit or overt", _scores_json(hate=0.85))

        mid = mg.moderateContent("https://example.com/e", "text")
        check = mg.getModeration(mid)
        assert check["verdict"] == "HARMFUL"
        assert check["category_scores"]["hate_speech"] == 0.85


class TestFetchFailure:
    def test_fetch_failure_is_unverifiable(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        direct_vm.mock_web(r"unreachable\.example", {"status": 500, "body": ""})

        mid = mg.moderateContent("https://unreachable.example/x", "text")
        assert mg.getModeration(mid)["verdict"] == "UNVERIFIABLE"

    def test_invalid_content_type_reverts(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        with direct_vm.expect_revert("Invalid content type"):
            mg.moderateContent("https://example.com/x", "smell")


class TestDomainStrikesAndBlacklist:
    def test_strikes_accumulate_and_blacklist_after_limit(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        direct_vm.mock_web(r"badsite\.example", {"body": "content"})
        direct_vm.mock_llm(r".*", _scores_json(hate=0.9))

        mg.moderateContent("https://badsite.example/1", "text")
        assert mg.getDomainStrikes("badsite.example") == "1"
        assert mg.isDomainBlacklisted("badsite.example") is False

        mg.moderateContent("https://badsite.example/2", "text")
        mg.moderateContent("https://badsite.example/3", "text")
        assert mg.getDomainStrikes("badsite.example") == "3"
        assert mg.isDomainBlacklisted("badsite.example") is True

    def test_blacklisted_domain_short_circuits_to_harmful(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        direct_vm.mock_web(r"badsite\.example", {"body": "content"})
        direct_vm.mock_llm(r".*", _scores_json(hate=0.9))
        for _ in range(3):
            mg.moderateContent("https://badsite.example/repeat", "text")
        assert mg.isDomainBlacklisted("badsite.example") is True

        # A brand new URL under the same already-blacklisted domain, with no
        # web/LLM mock registered for it at all, must still resolve — proving
        # the blacklist short-circuit actually skips re-fetch/re-consensus.
        mid = mg.moderateContent("https://badsite.example/never-fetched-before", "text")
        check = mg.getModeration(mid)
        assert check["verdict"] == "HARMFUL"
        assert check["worst_category"] == "blacklisted_domain"

    def test_safe_content_does_not_add_strikes(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        direct_vm.mock_web(r"goodsite\.example", {"body": "content"})
        direct_vm.mock_llm(r".*", _scores_json())
        mg.moderateContent("https://goodsite.example/1", "text")
        assert mg.getDomainStrikes("goodsite.example") == "0"


class TestChallenge:
    def test_challenge_requires_min_argument_length(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        direct_vm.mock_web(r"example\.com", {"body": "content"})
        direct_vm.mock_llm(r".*", _scores_json(hate=0.9))
        mid = mg.moderateContent("https://example.com/f", "text")

        with direct_vm.expect_revert("at least 15 characters"):
            mg.challengeModeration(mid, "https://counter.example", "too short")

    def test_challenge_open_to_any_address_not_just_creator(self, direct_deploy, direct_vm, direct_owner, direct_alice):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        direct_vm.mock_web(r"example\.com", {"body": "content"})
        direct_vm.mock_llm(r"WEBPAGE CONTENT", _scores_json(hate=0.9))
        mid = mg.moderateContent("https://example.com/g", "text")

        direct_vm.mock_web(r"counter\.example", {"body": "exculpatory context"})
        direct_vm.mock_llm(
            r"CHALLENGER ARGUMENT",
            '{"final_verdict":"SAFE","severity":0.1,"outcome":"OVERTURNED","reasoning":"context clears it"}',
        )
        with direct_vm.prank(direct_alice):
            result = mg.challengeModeration(mid, "https://counter.example", "This was clearly satire, not a real threat")

        assert "OVERTURNED" in result
        check = mg.getModeration(mid)
        assert check["verdict"] == "SAFE"
        assert check["last_challenge_outcome"] == "OVERTURNED"
        assert check["status"] == "challenged"

    def test_challenge_can_uphold_original_verdict(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        direct_vm.mock_web(r"example\.com", {"body": "content"})
        direct_vm.mock_llm(r"WEBPAGE CONTENT", _scores_json(hate=0.9))
        mid = mg.moderateContent("https://example.com/h", "text")

        direct_vm.mock_web(r"counter\.example", {"body": "weak counter-evidence"})
        direct_vm.mock_llm(
            r"CHALLENGER ARGUMENT",
            '{"final_verdict":"HARMFUL","severity":0.9,"outcome":"UPHELD","reasoning":"counter-evidence unconvincing"}',
        )
        result = mg.challengeModeration(mid, "https://counter.example", "I do not think this violates policy")
        assert "UPHELD" in result
        assert mg.getModeration(mid)["verdict"] == "HARMFUL"

    def test_challenge_count_capped_at_strike_limit(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        direct_vm.mock_web(r"example\.com|counter\.example", {"body": "content"})
        direct_vm.mock_llm(r"WEBPAGE CONTENT", _scores_json(hate=0.9))
        mid = mg.moderateContent("https://example.com/i", "text")

        direct_vm.mock_llm(
            r"CHALLENGER ARGUMENT",
            '{"final_verdict":"HARMFUL","severity":0.9,"outcome":"UPHELD","reasoning":"x"}',
        )
        for _ in range(3):
            mg.challengeModeration(mid, "https://counter.example", "This still does not violate policy at all")

        with direct_vm.expect_revert("Maximum challenge count reached"):
            mg.challengeModeration(mid, "https://counter.example", "One challenge too many for this item")

    def test_challenge_nonexistent_moderation_reverts(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        with direct_vm.expect_revert("Moderation not found"):
            mg.challengeModeration("999", "https://counter.example", "Something is wrong here")


class TestReadMethods:
    def test_get_nonexistent_moderation_reverts(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        with direct_vm.expect_revert("Moderation not found"):
            mg.getModeration("999")

    def test_moderations_by_verdict_and_type(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        direct_vm.mock_web(r"example\.com", {"body": "content"})
        direct_vm.mock_llm(r".*", _scores_json())
        mg.moderateContent("https://example.com/1", "text")
        mg.moderateContent("https://example.com/2", "image")

        assert len(mg.getModerationsByVerdict("SAFE")) == 2
        assert len(mg.getModerationsByType("text")) == 1
        assert len(mg.getModerationsByType("image")) == 1

    def test_stats(self, direct_deploy, direct_vm, direct_owner):
        mg = _deploy_and_init(direct_deploy, direct_vm, direct_owner)
        direct_vm.mock_web(r"example\.com", {"body": "content"})
        direct_vm.mock_llm(r".*", _scores_json())
        mg.moderateContent("https://example.com/1", "text")
        stats = mg.getStats()
        assert stats["total_moderations"] == "1"
        assert stats["safety_rate"] == "1.0"
