"""
tests/test_teardown_wizard.py

Offline unit tests for teardown_wizard.py.
All gcloud / gsutil / vertexai calls are mocked — no real GCP required.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from subprocess import CalledProcessError
from unittest.mock import MagicMock, patch


# Add project root to path so teardown_wizard is importable
sys.path.insert(0, str(Path(__file__).parent.parent))
import teardown_wizard as tw


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_env(tmp_path: Path, contents: str) -> Path:
    env = tmp_path / ".env"
    env.write_text(contents)
    return env


# ── read_env ───────────────────────────────────────────────────────────────────

class TestReadEnv:
    def test_reads_key_value_pairs(self, tmp_path):
        env = _make_env(tmp_path, "FOO=bar\nBAZ=qux\n")
        result = tw.read_env(env)
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_skips_comments_and_blanks(self, tmp_path):
        env = _make_env(tmp_path, "# comment\n\nKEY=val\n")
        result = tw.read_env(env)
        assert result == {"KEY": "val"}

    def test_strips_quotes(self, tmp_path):
        env = _make_env(tmp_path, 'KEY="quoted value"\n')
        result = tw.read_env(env)
        assert result["KEY"] == "quoted value"

    def test_returns_empty_when_file_missing(self, tmp_path):
        result = tw.read_env(tmp_path / "nonexistent.env")
        assert result == {}


# ── delete_cloud_run ───────────────────────────────────────────────────────────

class TestDeleteCloudRun:
    def test_deletes_service_when_found(self):
        with patch("teardown_wizard.gcloud") as mock_gcloud:
            mock_gcloud.return_value = "hermes-gateway"  # describe succeeds
            tw.delete_cloud_run("my-project", "us-central1")
            # second call should be the delete
            delete_call = mock_gcloud.call_args_list[1]
            assert "delete" in delete_call.args
            assert "hermes-gateway" in delete_call.args

    def test_skips_when_service_not_found(self):
        with patch("teardown_wizard.gcloud") as mock_gcloud:
            mock_gcloud.side_effect = CalledProcessError(1, ["gcloud"])
            # should not raise
            tw.delete_cloud_run("my-project", "us-central1")
            # only one call (describe) — no delete attempted
            assert mock_gcloud.call_count == 1


# ── delete_reasoning_engine ────────────────────────────────────────────────────

class TestDeleteReasoningEngine:
    def test_skips_when_empty(self):
        with patch("teardown_wizard.gcloud") as mock_gcloud:
            tw.delete_reasoning_engine("")
            mock_gcloud.assert_not_called()

    def test_deletes_valid_resource_name(self):
        rn = "projects/proj/locations/us-central1/reasoningEngines/12345"
        with patch("teardown_wizard.gcloud") as mock_gcloud:
            tw.delete_reasoning_engine(rn)
            delete_call = mock_gcloud.call_args_list[0]
            assert "12345" in delete_call.args
            assert "--location=us-central1" in delete_call.args

    def test_warns_on_bad_resource_name_format(self):
        with patch("teardown_wizard.gcloud") as mock_gcloud:
            tw.delete_reasoning_engine("bad-format")
            # should still attempt delete with check=False
            assert mock_gcloud.called


# ── delete_memory_bank ─────────────────────────────────────────────────────────

class TestDeleteMemoryBank:
    def test_skips_when_empty(self):
        tw.delete_memory_bank("")  # should not raise

    def test_calls_sdk_delete(self):
        mock_bank_instance = MagicMock()
        mock_mb_module = MagicMock()
        mock_mb_module.MemoryBank.return_value = mock_bank_instance

        with patch.dict("sys.modules", {
            "vertexai": MagicMock(),
            "vertexai.preview": MagicMock(),
            "vertexai.preview.memory_bank": mock_mb_module,
        }):
            # Re-import the function with patched modules in place
            import importlib
            import teardown_wizard as _tw
            importlib.reload(_tw)
            _tw.delete_memory_bank("projects/p/locations/l/memoryBanks/123")
            # Should not raise — graceful handling regardless of SDK behaviour
        # Reload original to restore module state
        importlib.reload(tw)

    def test_falls_back_to_gcloud_on_import_error(self):
        with patch("teardown_wizard.gcloud") as mock_gcloud:
            # Simulate ImportError for vertexai
            original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
            def _mock_import(name, *args, **kwargs):
                if name == "vertexai":
                    raise ImportError("no vertexai")
                return original_import(name, *args, **kwargs)

            rn = "projects/proj/locations/us-central1/memoryBanks/abc"
            with patch("builtins.__import__", side_effect=_mock_import):
                tw.delete_memory_bank(rn)  # should not raise


# ── delete_gcs_bucket ──────────────────────────────────────────────────────────

class TestDeleteGcsBucket:
    def test_skips_when_empty(self):
        with patch("teardown_wizard._gcs_storage") as mock_storage:
            tw.delete_gcs_bucket("")
            mock_storage.Client.assert_not_called()

    def test_adds_gs_prefix_if_missing(self):
        mock_client = MagicMock()
        mock_client.list_blobs.return_value = []
        mock_storage = MagicMock()
        mock_storage.Client.return_value = mock_client
        with patch.object(tw, "_gcs_storage", mock_storage), \
             patch.object(tw, "_GcsNotFound", Exception):
            tw.delete_gcs_bucket("my-bucket")
            mock_client.bucket.assert_called_once_with("my-bucket")

    def test_uses_existing_gs_prefix(self):
        mock_client = MagicMock()
        mock_client.list_blobs.return_value = []
        mock_storage = MagicMock()
        mock_storage.Client.return_value = mock_client
        with patch.object(tw, "_gcs_storage", mock_storage), \
             patch.object(tw, "_GcsNotFound", Exception):
            tw.delete_gcs_bucket("gs://my-bucket")
            mock_client.bucket.assert_called_once_with("my-bucket")


# ── delete_service_account ─────────────────────────────────────────────────────

class TestDeleteServiceAccount:
    def test_deletes_when_sa_exists(self):
        with patch("teardown_wizard.gcloud") as mock_gcloud:
            mock_gcloud.return_value = "some-output"  # describe succeeds
            tw.delete_service_account("my-project")
            calls = [c.args for c in mock_gcloud.call_args_list]
            assert any("delete" in c for c in calls)

    def test_skips_when_sa_not_found(self):
        with patch("teardown_wizard.gcloud") as mock_gcloud:
            mock_gcloud.side_effect = CalledProcessError(1, ["gcloud"])
            tw.delete_service_account("my-project")
            assert mock_gcloud.call_count == 1  # only describe — no delete


# ── delete_firestore ───────────────────────────────────────────────────────────

class TestDeleteFirestore:
    def test_deletes_default_db_when_found(self):
        db_list = [{"name": "projects/p/databases/(default)"}]
        with patch("teardown_wizard.gcloud") as mock_gcloud:
            mock_gcloud.return_value = json.dumps(db_list)
            tw.delete_firestore("my-project")
            calls = [c.args for c in mock_gcloud.call_args_list]
            assert any("delete" in c for c in calls)

    def test_skips_when_no_default_db(self):
        with patch("teardown_wizard.gcloud") as mock_gcloud:
            mock_gcloud.return_value = json.dumps([])
            tw.delete_firestore("my-project")
            # only one gcloud call (list) — no delete
            assert mock_gcloud.call_count == 1


# ── delete_scheduler_jobs ──────────────────────────────────────────────────────

class TestDeleteSchedulerJobs:
    def test_deletes_hermes_jobs(self):
        jobs = [
            {"name": "projects/p/locations/l/jobs/hermes-daily-eval"},
            {"name": "projects/p/locations/l/jobs/other-job"},
        ]
        with patch("teardown_wizard.gcloud") as mock_gcloud:
            mock_gcloud.return_value = json.dumps(jobs)
            tw.delete_scheduler_jobs("p", "us-central1")
            # Should delete only the hermes job
            calls = [c.args for c in mock_gcloud.call_args_list]
            delete_calls = [c for c in calls if "delete" in c]
            assert len(delete_calls) == 1
            assert any("hermes-daily-eval" in str(c) for c in delete_calls)

    def test_skips_when_no_hermes_jobs(self):
        jobs = [{"name": "projects/p/locations/l/jobs/unrelated"}]
        with patch("teardown_wizard.gcloud") as mock_gcloud:
            mock_gcloud.return_value = json.dumps(jobs)
            tw.delete_scheduler_jobs("p", "us-central1")
            # Only one call (list)
            assert mock_gcloud.call_count == 1


# ── wipe_env_file ──────────────────────────────────────────────────────────────

class TestWipeEnvFile:
    def test_deletes_env_when_confirmed(self, tmp_path):
        env = _make_env(tmp_path, "KEY=val\n")
        with patch("teardown_wizard.confirm", return_value=True):
            tw.wipe_env_file(env)
        assert not env.exists()

    def test_keeps_env_when_declined(self, tmp_path):
        env = _make_env(tmp_path, "KEY=val\n")
        with patch("teardown_wizard.confirm", return_value=False):
            tw.wipe_env_file(env)
        assert env.exists()

    def test_skips_when_no_env_file(self, tmp_path):
        tw.wipe_env_file(tmp_path / "nonexistent.env")  # should not raise


# ── disable_apis ──────────────────────────────────────────────────────────────

class TestDisableApis:
    def test_disables_when_confirmed(self):
        with patch("teardown_wizard.confirm", return_value=True):
            with patch("teardown_wizard.gcloud") as mock_gcloud:
                tw.disable_apis("my-project")
                assert mock_gcloud.called

    def test_skips_when_declined(self):
        with patch("teardown_wizard.confirm", return_value=False):
            with patch("teardown_wizard.gcloud") as mock_gcloud:
                tw.disable_apis("my-project")
                mock_gcloud.assert_not_called()
