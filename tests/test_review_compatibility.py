"""Historical-reader checks use only fictional, copied temporary workspaces."""

from contextlib import closing
from dataclasses import dataclass
import hashlib
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import struct
import subprocess
import sys
from urllib.parse import parse_qs, unquote, urlsplit

import ormsgpack
import pytest

from agent_support import FakeRetriever
from watchlist.agent.audit import verify_chain
from watchlist.agent.storage import ReviewService


REPOSITORY = Path(__file__).resolve().parents[1]
WORKSPACE = "data/review"
DATABASES = [f"{WORKSPACE}/{name}.sqlite" for name in ("cases", "checkpoints")]
STAGES = {
    "completed": "completed_audit_checkpoint",
    "pending": "packet_saved_pending_review",
    "after_case": "created_before_first_checkpoint",
    "after_packet": "packet_saved_pending_review",
    "after_submission": "submission_accepted_pending_completion",
    "during_explanation": "submission_accepted_pending_completion",
    "after_final_audit": "final_audit_pending_checkpoint",
}


@dataclass(frozen=True)
class Snapshot:
    project: Path
    database_root: Path
    audit_id: str
    thread_id: str

    def database(self, name: str) -> Path:
        return self.database_root / WORKSPACE / f"{name}.sqlite"


@pytest.fixture(scope="module")
def reader():
    return importlib.import_module("watchlist.review.compat_v1")


@pytest.fixture(scope="module")
def preservation():
    """Use the frozen Step 00 copier without invoking its CLI or original stores."""
    spec = importlib.util.spec_from_file_location(
        "compatibility_fixture_preservation", REPOSITORY / "scripts/preserve_v1.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def snapshot_templates(tmp_path_factory, preservation):
    """Create each real crash stage once; every test receives an independent copy."""
    cache = {}

    def build(stage: str) -> Snapshot:
        if stage in cache:
            return cache[stage]
        root = tmp_path_factory.mktemp("historical-" + stage).resolve()
        source = root / "source"
        shutil.copytree(REPOSITORY / "src", source / "src",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        workspace = source / WORKSPACE

        def worker(action, failpoint="none", review=None):
            args = [sys.executable, "-B", str(REPOSITORY / "tests/agent_support.py"),
                    action, str(workspace), failpoint]
            if review is not None:
                args.append(str(review))
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            return subprocess.run(args, capture_output=True, text=True, timeout=30, env=environment)

        if stage in ("invalid_blank", "invalid_too_long"):
            retriever = FakeRetriever(fail=True)
            with ReviewService(workspace, retriever) as service:
                result = service.start("   " if stage == "invalid_blank" else "X" * 201, {"fixture": "v1"})
                assert result["completed"] and result["state"]["error"]["code"] == "invalid_query"
            assert retriever.calls == 0
        else:
            start = worker("start", stage if stage in ("after_case", "after_packet") else "none")
            if stage in ("after_case", "after_packet"):
                assert start.returncode == 77, start.stderr + start.stdout
            else:
                assert start.returncode == 0, start.stderr + start.stdout
                pending = json.loads(start.stdout)
                if stage != "pending":
                    from agent_support import form
                    review = root / "fictional-review.json"
                    review.write_text(json.dumps(form(pending)), encoding="utf-8")
                    result = worker("review", "none" if stage == "completed" else stage, review)
                    assert result.returncode == (0 if stage == "completed" else 77), result.stderr + result.stdout
        project, databases = root / "project", root / "databases"
        shutil.copytree(source, project)
        preservation._backup_databases(project, DATABASES, databases)
        with closing(sqlite3.connect((databases / DATABASES[0]).as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
            audit_id, thread_id = db.execute("SELECT audit_id,thread_id FROM cases").fetchone()
        cache[stage] = Snapshot(project, databases, audit_id, thread_id)
        return cache[stage]

    return build


@pytest.fixture
def snapshot_factory(tmp_path, snapshot_templates):
    counter = 0

    def clone(stage="completed"):
        nonlocal counter
        counter += 1
        template = snapshot_templates(stage)
        root = tmp_path.resolve() / f"copy-{counter}"
        project, databases = root / "project", root / "databases"
        shutil.copytree(template.project, project)
        shutil.copytree(template.database_root, databases)
        return Snapshot(project, databases, template.audit_id, template.thread_id)

    return clone


def disk_state(snapshot):
    """Include bytes, permissions and identity; access-time changes are excluded."""
    result = {}
    for root in (snapshot.project, snapshot.database_root):
        for path in [root, *sorted(root.rglob("*"))]:
            metadata = path.lstat()
            value = (metadata.st_mode, metadata.st_dev, metadata.st_ino,
                     metadata.st_nlink, metadata.st_mtime_ns, metadata.st_ctime_ns)
            if stat.S_ISREG(metadata.st_mode):
                value += (hashlib.sha256(path.read_bytes()).hexdigest(),)
            elif stat.S_ISLNK(metadata.st_mode):
                value += (os.readlink(path),)
            result[str(path)] = value
    return result


def assert_rejected(reader, snapshot):
    before = disk_state(snapshot)
    with pytest.raises(reader.ArchiveError):
        reader.verify_v1(snapshot.project, WORKSPACE, snapshot.database_root)
    with pytest.raises(reader.ArchiveError):
        reader.inspect_v1(snapshot.project, WORKSPACE, snapshot.database_root, snapshot.audit_id)
    assert disk_state(snapshot) == before


@pytest.mark.parametrize("stage,expected_status", STAGES.items())
def test_actual_historical_stages_are_inspected_without_recovery(
    reader, preservation, snapshot_factory, stage, expected_status
):
    snapshot = snapshot_factory(stage)
    before = disk_state(snapshot)
    receipt = reader.verify_v1(snapshot.project, WORKSPACE, snapshot.database_root)
    assert receipt["case_count"] == 1
    case = receipt["cases"][0]
    assert case["status"] == expected_status
    assert case["completed_audit_checkpoint"] is (stage == "completed")
    assert case["annotation_origin"] == "unknown"
    assert receipt["checkpoint_store"]["graph_executed"] is False
    assert receipt["provenance"]["runtime_class_revival"] is False
    if stage != "after_case":
        assert receipt == preservation.logical_verification(snapshot.project, WORKSPACE, snapshot.database_root)
    else:
        assert case["latest_checkpoint_id"] is None
        assert receipt["checkpoint_store"]["checkpoint_rows"] == 0
    by_audit = reader.inspect_v1(snapshot.project, WORKSPACE, snapshot.database_root, snapshot.audit_id)
    by_thread = reader.inspect_v1(snapshot.project, WORKSPACE, snapshot.database_root, snapshot.thread_id)
    assert by_audit == by_thread
    assert by_audit["archive_version"] == "v1"
    assert by_audit["case"] == case
    assert by_audit["initial"]["query"] == "  LUMA   VESPER "
    assert (by_audit["review_packet"] is not None) is (stage != "after_case")
    assert (by_audit["review_submission"] is not None) is (
        stage in ("completed", "after_submission", "during_explanation", "after_final_audit")
    )
    with closing(sqlite3.connect(snapshot.database("cases").as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        db.row_factory = sqlite3.Row
        initial = json.loads(db.execute("SELECT initial_json FROM cases").fetchone()[0])
        saved_packet = db.execute("SELECT packet_json FROM review_packets").fetchone()
        saved_submission = db.execute("SELECT payload_json FROM review_submissions").fetchone()
        events = [dict(row) | {"payload": json.loads(row["payload_json"])}
                  for row in db.execute("SELECT * FROM audit_events ORDER BY sequence")]
    assert by_audit["initial"] == initial
    assert by_audit["review_packet"] == (json.loads(saved_packet[0]) if saved_packet else None)
    assert by_audit["review_submission"] == (json.loads(saved_submission[0]) if saved_submission else None)
    assert by_audit["audit_events"] == events
    assert initial["query"] not in json.dumps(receipt)
    if saved_submission:
        assert json.loads(saved_submission[0])["reason"] not in json.dumps(receipt)
    if stage == "after_case":
        assert by_audit["checkpoint"] is None
        assert by_audit["latest_state"] is None
    else:
        with closing(sqlite3.connect(snapshot.database("checkpoints").as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
            raw = db.execute("SELECT checkpoint FROM checkpoints ORDER BY checkpoint_id DESC LIMIT 1").fetchone()[0]
        saved_checkpoint = ormsgpack.unpackb(raw)
        assert by_audit["checkpoint"]["checkpoint_id"] == saved_checkpoint["id"]
        assert by_audit["latest_state"] == {key: saved_checkpoint["channel_values"][key] for key in initial}
    assert disk_state(snapshot) == before


@pytest.mark.parametrize("stage", ["invalid_blank", "invalid_too_long"])
def test_completed_input_errors_remain_inspectable_without_a_reviewer_decision(reader, preservation, snapshot_factory, stage):
    snapshot = snapshot_factory(stage)
    before = disk_state(snapshot)
    receipt = reader.verify_v1(snapshot.project, WORKSPACE, snapshot.database_root)
    assert receipt == preservation.logical_verification(snapshot.project, WORKSPACE, snapshot.database_root)
    assert receipt["cases"][0]["status"] == "completed_audit_checkpoint"
    assert receipt["cases"][0]["event_keys"] == ["request_created", "case_finalized"]
    detail = reader.inspect_v1(snapshot.project, WORKSPACE, snapshot.database_root, snapshot.audit_id)
    assert detail["review_packet"] is None and detail["review_submission"] is None
    assert detail["latest_state"]["error"]["code"] == "invalid_query"
    assert detail["latest_state"]["reviewer_decision"] is None
    assert detail["latest_state"]["retrieval"] is None
    assert disk_state(snapshot) == before


def test_unknown_case_is_an_explicit_read_only_error(reader, snapshot_factory):
    snapshot = snapshot_factory()
    before = disk_state(snapshot)
    with pytest.raises(reader.ArchiveError, match="[Uu]nknown|[Nn]ot found"):
        reader.inspect_v1(snapshot.project, WORKSPACE, snapshot.database_root, "missing-fictional-case")
    assert disk_state(snapshot) == before


def test_reader_uses_only_immutable_sqlite_and_never_writes_or_executes(reader, snapshot_factory, monkeypatch):
    snapshot = snapshot_factory()
    before = disk_state(snapshot)
    actual_connect, actual_open, actual_io_open, actual_os_open = sqlite3.connect, open, io.open, os.open
    opened = []

    def connect(database, *args, **kwargs):
        parsed = urlsplit(os.fspath(database))
        assert parsed.scheme == "file" and kwargs.get("uri") is True
        assert parse_qs(parsed.query) == {"mode": ["ro"], "immutable": ["1"]}
        path = Path(unquote(parsed.path)).resolve()
        assert path.is_relative_to(snapshot.database_root)
        opened.append(path)
        return actual_connect(database, *args, **kwargs)

    def read_only_open(original):
        def guarded(file, mode="r", *args, **kwargs):
            assert not any(flag in mode for flag in "wax+"), "Reader attempted a writable file open"
            return original(file, mode, *args, **kwargs)
        return guarded

    def read_only_os_open(path, flags, *args, **kwargs):
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        return actual_os_open(path, flags, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("Archive reading attempted a mutation, process launch, retrieval, or graph execution")

    from watchlist.agent import graph
    with monkeypatch.context() as guarded:
        guarded.setattr(sqlite3, "connect", connect)
        guarded.setattr("builtins.open", read_only_open(actual_open))
        guarded.setattr(io, "open", read_only_open(actual_io_open))
        guarded.setattr(os, "open", read_only_os_open)
        guarded.setattr(os, "chmod", forbidden)
        guarded.setattr(Path, "chmod", forbidden)
        guarded.setattr(subprocess, "Popen", forbidden)
        guarded.setattr(ReviewService, "__enter__", forbidden)
        guarded.setattr(FakeRetriever, "search", forbidden)
        guarded.setattr(graph, "build_graph", forbidden)
        reader.verify_v1(snapshot.project, WORKSPACE, snapshot.database_root)
        detail = reader.inspect_v1(snapshot.project, WORKSPACE, snapshot.database_root, snapshot.audit_id)
        assert detail["review_submission"]["candidate_entity_id"] == "syn-001"
    assert set(opened) == {snapshot.database("cases"), snapshot.database("checkpoints")}
    assert disk_state(snapshot) == before


def test_reader_runs_without_third_party_packages_or_runtime_class_revival(snapshot_factory):
    snapshot = snapshot_factory("pending")
    runner = """
import json
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from watchlist.review.compat_v1 import inspect_v1, verify_v1
project, databases = Path(sys.argv[2]), Path(sys.argv[3])
result = verify_v1(project, 'data/review', databases)
detail = inspect_v1(project, 'data/review', databases, result['cases'][0]['audit_id'])
blocked = ('langgraph', 'ormsgpack', 'torch', 'sentence_transformers', 'transformers', 'watchlist.agent')
assert not any(name == root or name.startswith(root + '.') for root in blocked for name in sys.modules)
assert detail['review_packet']['candidates'][0]['entity_id'] == 'syn-001'
print(json.dumps({'status': result['cases'][0]['status']}))
"""
    result = subprocess.run([sys.executable, "-B", "-I", "-S", "-c", runner,
                             str(REPOSITORY / "src"), str(snapshot.project), str(snapshot.database_root)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout) == {"status": "packet_saved_pending_review"}


def test_current_code_changes_do_not_block_reading_but_still_block_execution(reader, snapshot_factory, monkeypatch):
    snapshot = snapshot_factory("pending")
    from watchlist.agent import state as live_state
    changed = snapshot.project / "src/watchlist/agent/nodes.py"
    changed.write_bytes(changed.read_bytes() + b"\n# Fictional future implementation for compatibility test.\n")
    monkeypatch.setattr(live_state, "__file__", str(snapshot.project / "src/watchlist/agent/state.py"))
    with ReviewService(snapshot.project / WORKSPACE, FakeRetriever(fail=True)) as service:
        original = service.ledger.initial(snapshot.thread_id)
        assert service.code_hash != original["workflow_sha256"]
        with pytest.raises(ValueError, match="workflow/schema changed"):
            service.recover(snapshot.thread_id)
    before = disk_state(snapshot)
    detail = reader.inspect_v1(snapshot.project, WORKSPACE, snapshot.database_root, snapshot.thread_id)
    assert detail["initial"]["workflow_sha256"] == original["workflow_sha256"]
    assert detail["review_packet"]["candidates"][0]["matched_alias"] == "Luma Vesper"
    assert disk_state(snapshot) == before


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def rehash_audit(db, audit_id):
    """Make the adversarial chain internally valid, leaving semantic checks essential."""
    db.row_factory = sqlite3.Row
    previous = ""
    rows = db.execute("SELECT * FROM audit_events WHERE audit_id=? ORDER BY sequence", (audit_id,)).fetchall()
    for row in rows:
        envelope = {key: row[key] for key in
                    ("audit_id", "sequence", "event_key", "payload_json", "created_at", "previous_sha256")}
        envelope["previous_sha256"] = previous
        current = digest(envelope)
        db.execute("UPDATE audit_events SET previous_sha256=?,event_sha256=? WHERE audit_id=? AND sequence=?",
                   (previous, current, audit_id, row["sequence"]))
        previous = current
    assert verify_chain(db, audit_id)["count"] == len(rows)


def test_semantically_invalid_packet_is_rejected_even_with_rehashed_receipts(reader, snapshot_factory):
    snapshot = snapshot_factory("after_packet")
    with closing(sqlite3.connect(snapshot.database("cases"))) as db:
        packet = json.loads(db.execute("SELECT packet_json FROM review_packets").fetchone()[0])
        packet["candidates"][0]["similarity_score"] = 2.0
        packet_hash = digest(packet)
        db.execute("UPDATE review_packets SET packet_json=?,sha256=?", (canonical(packet), packet_hash))
        db.execute("UPDATE audit_events SET payload_json=? WHERE event_key='suggestions_ready'",
                   (canonical({"packet_sha256": packet_hash}),))
        rehash_audit(db, snapshot.audit_id)
        db.commit()
    with closing(sqlite3.connect(snapshot.database("checkpoints"))) as db:
        for rowid, raw in db.execute("SELECT rowid,checkpoint FROM checkpoints").fetchall():
            value = ormsgpack.unpackb(raw)
            channels = value["channel_values"]
            if channels.get("candidates"):
                channels["candidates"] = packet["candidates"]
            if channels.get("evidence_sha256"):
                channels["evidence_sha256"] = packet_hash
            db.execute("UPDATE checkpoints SET checkpoint=? WHERE rowid=?", (ormsgpack.packb(value), rowid))
        for channel, value in (("candidates", packet["candidates"]), ("evidence_sha256", packet_hash)):
            db.execute("UPDATE writes SET value=? WHERE channel=?", (ormsgpack.packb(value), channel))
        db.commit()
    assert_rejected(reader, snapshot)


def test_semantically_invalid_submission_is_rejected_even_with_rehashed_audit(reader, snapshot_factory):
    snapshot = snapshot_factory("after_submission")
    with closing(sqlite3.connect(snapshot.database("cases"))) as db:
        value = json.loads(db.execute("SELECT payload_json FROM review_submissions").fetchone()[0])
        value["candidate_entity_id"] = "fictional-record-outside-shortlist"
        db.execute("UPDATE review_submissions SET payload_json=?,sha256=?", (canonical(value), digest(value)))
        db.execute("UPDATE audit_events SET payload_json=? WHERE event_key='review_submitted'",
                   (canonical({"submission": value}),))
        rehash_audit(db, snapshot.audit_id)
        db.commit()
    assert_rejected(reader, snapshot)


def test_mixed_ledger_and_checkpoint_stores_are_rejected(reader, snapshot_factory):
    first, other = snapshot_factory("completed"), snapshot_factory("pending")
    assert first.thread_id != other.thread_id
    shutil.copy2(other.database("checkpoints"), first.database("checkpoints"))
    assert_rejected(reader, first)


def test_empty_checkpoint_exception_cannot_hide_lost_pending_history(reader, snapshot_factory):
    snapshot = snapshot_factory("pending")
    snapshot.database("checkpoints").unlink()
    with closing(sqlite3.connect(snapshot.database("checkpoints"))) as db:
        db.execute("VACUUM")
    assert_rejected(reader, snapshot)


@pytest.mark.parametrize("field,value", [("candidates", "not a list"), ("review_status", "recorded"), ("query", None)])
def test_rehashed_creation_only_case_requires_a_valid_initial_state(reader, snapshot_factory, field, value):
    snapshot = snapshot_factory("after_case")
    with closing(sqlite3.connect(snapshot.database("cases"))) as db:
        initial = json.loads(db.execute("SELECT initial_json FROM cases").fetchone()[0])
        initial[field] = value
        encoded = canonical(initial)
        db.execute("UPDATE cases SET initial_json=?", (encoded,))
        db.execute("UPDATE audit_events SET payload_json=? WHERE event_key='request_created'", (encoded,))
        rehash_audit(db, snapshot.audit_id)
        db.commit()
    assert_rejected(reader, snapshot)


@pytest.mark.parametrize("change", ["user_version", "unexpected_table"])
def test_unknown_database_schema_is_rejected(reader, snapshot_factory, change):
    snapshot = snapshot_factory()
    with closing(sqlite3.connect(snapshot.database("cases"))) as db:
        db.execute("PRAGMA user_version=99" if change == "user_version" else "CREATE TABLE future_state (value TEXT)")
        db.commit()
    assert_rejected(reader, snapshot)


@pytest.mark.parametrize("kind", ["pickle", "future_serializer"])
def test_unknown_checkpoint_serializer_is_rejected_as_stored_data(reader, snapshot_factory, kind):
    snapshot = snapshot_factory("pending")
    with closing(sqlite3.connect(snapshot.database("checkpoints"))) as db:
        db.execute("UPDATE checkpoints SET type=?,checkpoint=? WHERE checkpoint_id=(SELECT MAX(checkpoint_id) FROM checkpoints)",
                   (kind, b"\x80\x04N."))
        db.commit()
    assert_rejected(reader, snapshot)


def extension_blob(value, code=2):
    encoded = ormsgpack.packb(value)
    return b"\x91\xc9" + struct.pack(">I", len(encoded)) + bytes([code]) + encoded


@pytest.mark.parametrize("attack", ["unknown_extension", "constructor_revival", "extension_in_state_write"])
def test_runtime_extensions_never_revive_classes(reader, snapshot_factory, monkeypatch, attack):
    snapshot = snapshot_factory("pending")
    calls = []
    monkeypatch.setattr(os, "system", lambda command: calls.append(command))
    with closing(sqlite3.connect(snapshot.database("checkpoints"))) as db:
        if attack == "extension_in_state_write":
            db.execute("UPDATE writes SET channel='query' WHERE channel='__interrupt__'")
        else:
            payload = ["os", "system", {"command": "fictional-revival-must-not-run"}]
            db.execute("UPDATE writes SET value=? WHERE channel='__interrupt__'",
                       (extension_blob(payload, 83 if attack == "unknown_extension" else 2),))
        db.commit()
    assert_rejected(reader, snapshot)
    assert calls == []


@pytest.mark.parametrize("attack", ["unknown_branch", "missing_channel_version", "unknown_scheduler_node", "wrong_scheduler_version"])
def test_invalid_scheduler_state_is_rejected(reader, snapshot_factory, attack):
    snapshot = snapshot_factory("pending")
    with closing(sqlite3.connect(snapshot.database("checkpoints"))) as db:
        rowid, raw = db.execute("SELECT rowid,checkpoint FROM checkpoints ORDER BY checkpoint_id DESC LIMIT 1").fetchone()
        value = ormsgpack.unpackb(raw)
        if attack == "unknown_branch":
            value["channel_values"]["branch:to:unapproved_node"] = None
            value["channel_versions"]["branch:to:unapproved_node"] = value["channel_versions"]["branch:to:human_review"]
        elif attack == "missing_channel_version":
            del value["channel_versions"]["query"]
        elif attack == "unknown_scheduler_node":
            value["versions_seen"]["unapproved_node"] = {}
        else:
            value["v"] = 999
        db.execute("UPDATE checkpoints SET checkpoint=? WHERE rowid=?", (ormsgpack.packb(value), rowid))
        db.commit()
    assert_rejected(reader, snapshot)


@pytest.mark.parametrize("channel,idx", [("__resume__", -4), ("__unapproved_control__", -99)])
def test_invalid_control_writes_cannot_make_a_completed_case_resumable(reader, snapshot_factory, channel, idx):
    snapshot = snapshot_factory("completed")
    with closing(sqlite3.connect(snapshot.database("cases").as_uri() + "?mode=ro&immutable=1", uri=True)) as ledger:
        submission = ledger.execute("SELECT payload_json FROM review_submissions").fetchone()[0].encode("utf-8")
    with closing(sqlite3.connect(snapshot.database("checkpoints"))) as db:
        checkpoint_id = db.execute("SELECT MAX(checkpoint_id) FROM checkpoints").fetchone()[0]
        db.execute("INSERT INTO writes VALUES (?,?,?,?,?,?,?,?,?)",
                   (snapshot.thread_id, "", checkpoint_id, "00000000-0000-0000-0000-000000000000", "",
                    idx, channel, "json", submission if channel == "__resume__" else b"{}"))
        db.commit()
    assert_rejected(reader, snapshot)


def test_interrupt_cannot_be_reassigned_to_a_different_known_task(reader, snapshot_factory):
    snapshot = snapshot_factory("pending")
    with closing(sqlite3.connect(snapshot.database("checkpoints"))) as db:
        cursor = db.execute("UPDATE writes SET task_path='~__pregel_pull, audit_record' WHERE channel='__interrupt__'")
        assert cursor.rowcount == 1
        db.commit()
    assert_rejected(reader, snapshot)


@pytest.mark.parametrize("scope", ["input", "human_review_task"])
def test_resume_control_must_equal_the_durable_human_annotation(reader, snapshot_factory, scope):
    snapshot = snapshot_factory("completed")
    with closing(sqlite3.connect(snapshot.database("checkpoints"))) as db:
        zero_task = "00000000-0000-0000-0000-000000000000"
        comparison = "=" if scope == "input" else "!="
        rows = db.execute("SELECT rowid,type,value FROM writes WHERE channel='__resume__' AND task_id "
                          + comparison + " ?", (zero_task,)).fetchall()
        assert len(rows) == 1
        rowid, kind, raw = rows[0]
        assert kind == "msgpack"
        value = ormsgpack.unpackb(raw)
        submission = value if scope == "input" else value[0]
        submission["reason"] = "Altered control write; this is not the accepted fictional annotation."
        db.execute("UPDATE writes SET value=? WHERE rowid=?", (ormsgpack.packb(value), rowid))
        db.commit()
    assert_rejected(reader, snapshot)


def test_checkpoint_metadata_cannot_skip_a_workflow_step(reader, snapshot_factory):
    snapshot = snapshot_factory("pending")
    with closing(sqlite3.connect(snapshot.database("checkpoints"))) as db:
        rowid, raw = db.execute("SELECT rowid,metadata FROM checkpoints ORDER BY checkpoint_id DESC LIMIT 1").fetchone()
        metadata = json.loads(raw)
        metadata["step"] += 2
        db.execute("UPDATE checkpoints SET metadata=? WHERE rowid=?", (canonical(metadata).encode("utf-8"), rowid))
        db.commit()
    assert_rejected(reader, snapshot)


@pytest.mark.parametrize("corrupt_successor", [False, True], ids=["valid-successor", "invalid-successor"])
def test_missing_async_write_batch_requires_a_coherent_durable_successor(reader, snapshot_factory, corrupt_successor):
    snapshot = snapshot_factory("completed")
    with closing(sqlite3.connect(snapshot.database("cases").as_uri() + "?mode=ro&immutable=1", uri=True)) as ledger:
        submission = json.loads(ledger.execute("SELECT payload_json FROM review_submissions").fetchone()[0])
    reviewed_id = submission["expected_checkpoint_id"]
    with closing(sqlite3.connect(snapshot.database("checkpoints"))) as db:
        channels = {row[0] for row in db.execute(
            "SELECT channel FROM writes WHERE checkpoint_id=? AND task_path='~__pregel_pull, human_review' AND idx>=0",
            (reviewed_id,),
        )}
        assert {"reviewer_decision", "review_status"} <= channels
        db.execute("DELETE FROM writes WHERE checkpoint_id=? AND task_path='~__pregel_pull, human_review' AND idx>=0",
                   (reviewed_id,))
        successors = db.execute("SELECT rowid,checkpoint FROM checkpoints WHERE parent_checkpoint_id=?", (reviewed_id,)).fetchall()
        assert len(successors) == 1
        rowid, raw = successors[0]
        successor = ormsgpack.unpackb(raw)
        assert successor["channel_values"]["review_status"] == "recorded"
        assert successor["channel_values"]["reviewer_decision"] == submission
        if corrupt_successor:
            successor["channel_values"]["review_status"] = "pending"
            db.execute("UPDATE checkpoints SET checkpoint=? WHERE rowid=?", (ormsgpack.packb(successor), rowid))
        db.commit()
    if corrupt_successor:
        assert_rejected(reader, snapshot)
    else:
        before = disk_state(snapshot)
        detail = reader.inspect_v1(snapshot.project, WORKSPACE, snapshot.database_root, snapshot.audit_id)
        assert detail["case"]["status"] == "completed_audit_checkpoint"
        assert detail["latest_state"]["reviewer_decision"] == submission
        assert detail["checkpoint"]["checkpoints_without_preceding_write_batch"] == [successor["id"]]
        assert disk_state(snapshot) == before


@pytest.mark.parametrize("name", ["demo-start.json", "demo-review.json"])
@pytest.mark.parametrize("malformed", [[], None], ids=["array", "null"])
def test_saved_demo_nonobject_json_has_a_controlled_archive_error(reader, tmp_path, name, malformed):
    """Malformed transcripts must fail before attempting object attribute access."""
    project = tmp_path.resolve() / "fictional-project"
    directory = project / WORKSPACE / "verification"
    directory.mkdir(parents=True)
    audit_id = "e449b466-466d-4b81-9a29-cb3c9d957823"
    thread_id = "446f2137-621a-4426-8f95-9c82e07bcacf"
    final_id = "1f1ce0fc-cda5-66e0-8007-f6f0502a7876"
    pending_id = "1f1ce0fa-af59-63b4-8004-4f329c922484"
    head = "b62fc08e60b609a5c56e6cd4a4710f60e15b5a43c352ed76cc9220a7f1848a9e"
    done = {"audit_id": audit_id, "thread_id": thread_id, "state": {}, "checkpoint_id": final_id,
            "completed": True, "pending_interrupt": False, "next": []}
    start = {"audit_id": audit_id, "thread_id": thread_id, "state": {}, "checkpoint_id": pending_id,
             "completed": False, "pending_interrupt": True, "next": ["human_review"]}
    names = ("demo-start.json", "demo-status.json", "demo-recover-pending.json", "demo-review-form.json",
             "demo-review.json", "demo-recover.json", "demo-audit-verify.json")
    documents = dict.fromkeys(names, {}) | {"demo-start.json": start, "demo-review.json": done, name: malformed}
    for filename, value in documents.items():
        (directory / filename).write_text(json.dumps(value), encoding="utf-8")
    states = {audit_id: {"receipt": {"audit_count": 4, "audit_head_sha256": head,
                                    "latest_checkpoint_id": final_id, "completed_audit_checkpoint": True},
                         "latest_state": {}, "states": {pending_id: {}}}}
    before = {path.name: (path.read_bytes(), path.stat().st_mode) for path in directory.iterdir()}
    with pytest.raises(reader.ArchiveError):
        reader._pv1_saved_demo(project, Path(WORKSPACE), states)
    assert {path.name: (path.read_bytes(), path.stat().st_mode) for path in directory.iterdir()} == before
