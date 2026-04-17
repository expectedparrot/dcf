import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "SPEC.md").read_text(encoding="utf-8")
PLAN = (ROOT / "TEST_PLAN.md").read_text(encoding="utf-8")


class SpecContractTests(unittest.TestCase):
    def test_proposal_is_the_public_command_group(self):
        self.assertIn("- [proposal](#48-proposal)", SPEC)
        self.assertIn("### 4.8 `proposal`", SPEC)
        self.assertIn("dcf proposal submit", SPEC)
        self.assertIn("dcf proposal compare", SPEC)
        self.assertNotIn("- [agent](#48-agent)", SPEC)
        self.assertNotIn("### 4.8 `agent`", SPEC)
        self.assertNotIn("dcf agent ", SPEC)

    def test_package_boundary_excludes_agent_simulation(self):
        self.assertIn("does not generate proposals", SPEC)
        self.assertIn("never generates proposals", PLAN)
        self.assertIn("call LLM", SPEC)
        self.assertNotIn("Available AI agents", SPEC)
        self.assertIn("simulates agents", PLAN)
        self.assertNotIn("dcf proposal challenge", SPEC)
        self.assertNotIn("dcf proposal debate", SPEC)

    def test_proposal_storage_paths_are_used(self):
        self.assertIn("proposals/", SPEC)
        self.assertIn("proposals/sessions/<session>/proposals/", SPEC)
        self.assertIn("each submitted proposal can be hash-verified", SPEC)
        self.assertIn('"event":"proposal_session"', SPEC)
        self.assertNotIn(".dcf/agents/", SPEC)
        self.assertNotIn("agents/sessions", SPEC)

    def test_proposal_records_are_first_class_inputs(self):
        required_fields = [
            '"proposal_id"',
            '"participant_id"',
            '"participant_type"',
            '"base_version"',
            '"scenario_seq"',
            '"overrides"',
            '"rationale"',
        ]
        for field in required_fields:
            with self.subTest(field=field):
                self.assertIn(field, SPEC)

    def test_scenario_provenance_links_back_to_proposals(self):
        self.assertIn('"provenance"', SPEC)
        self.assertIn('"proposal_id": null', SPEC)
        self.assertIn('"participant_id": null', SPEC)
        self.assertIn('"source": "proposal"', SPEC)
        self.assertIn("session, proposal, and participant ids", SPEC)

    def test_append_only_revision_storage_is_specified(self):
        self.assertIn("Existing JSON artifacts are never modified", SPEC)
        self.assertIn("Scenario revision", SPEC)
        self.assertIn("Import map revision", SPEC)
        self.assertIn("Historical record", SPEC)
        self.assertIn("highest-`seq` revision", SPEC)

    def test_verify_contract_covers_artifacts_and_log_chain(self):
        checks = [
            "SHA-256",
            "artifact files",
            "logged artifact path that is missing",
            "unlogged file",
            "entry hash chain",
            "trailing log",
        ]
        for check in checks:
            with self.subTest(check=check):
                self.assertIn(check, SPEC)

    def test_test_plan_covers_major_feature_areas(self):
        headings = re.findall(r"^## \d+\. (.+)$", PLAN, flags=re.MULTILINE)
        expected = {
            "Project initialization",
            "Append-only storage",
            "Assumptions",
            "Scenarios",
            "Imports and historicals",
            "DCF model runs",
            "Proposal sessions",
            "Sensitivity analysis",
            "Display and export",
            "Integrity verification",
            "JSON output and errors",
        }
        self.assertEqual(expected, set(headings))


if __name__ == "__main__":
    unittest.main()
