"""Fictional readiness queues stay unreviewed, immutable and locally reproducible."""

from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
import os
import socket
import stat
import subprocess
import sys

import pytest

from watchlist import corpus
from watchlist import corpus_readiness as readiness
from watchlist.ingest import link_records as links
from watchlist.ingest.resource_guard import (
    GIB,
    ResourceGuard,
    ResourceSnapshot,
    ResourceStop,
)
from watchlist.normalize import MAX_NAME_LENGTH


EXPECTED_COUNTS = {
    "observations": 5,
    "organizations": 4,
    "vessels": 1,
    "name_entries": 9,
    "candidate_pairs": 3,
    "exact_pairs": 1,
    "normalized_only_pairs": 2,
    "review_components": 1,
    "collision_records": 3,
    "weak_name_entries": 2,
    "weak_records": 2,
    "overlength_name_entries": 1,
    "overlength_records": 1,
    "flagged_records": 4,
    "unknown_language_entries": 7,
}


def encoded(value):
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    ).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def rows(payload):
    return [json.loads(line) for line in payload.splitlines()]


def safe_guard(**kwargs):
    return ResourceGuard(
        probe=lambda: ResourceSnapshot(20_000_000, 20 * GIB, 0, 0.5, False),
        **kwargs,
    )


def name(evidence_id, value, *, field="properties.name", language=None, attrs=()):
    return corpus.CandidateNameEvidence(evidence_id, value, field, language, attrs)


def observation(oid, source, provider, aliases, *, entity_type="organization"):
    return corpus.CandidateObservation(
        observation_id=oid,
        snapshot_id="snapshot-" + source,
        source_id=source,
        provider_id=provider,
        source_record_key=(source, provider),
        entity_type=entity_type,
        primary_name=aliases[0].value,
        aliases=tuple(aliases),
        provider_schema="Fictional " + entity_type,
        classification_basis="authored-fictional-test",
        referents=(),
        provider_datasets=(),
        provider_topics=(),
        source_role="sanctions_reference",
    )


class FictionalReadiness:
    """Small post-admission fixture; actual admission has a separate integration test."""

    def __init__(self, root):
        self.root = root.resolve()
        self.input_dir = self.root / "inputs"
        self.input_dir.mkdir(parents=True)
        (self.root / "data").mkdir()
        (self.root / "config").mkdir()
        self.output = self.root / "data" / "preparation"
        self.config_path = self.root / "config" / "corpus-readiness-v1.json"
        self.long_name = "Fictional " + "z" * MAX_NAME_LENGTH
        shared = "Fictional Lumen Orchard"
        observations = (
            observation(
                "observation-a",
                "opensanctions_un",
                "17",
                (
                    name("name-a1", shared),
                    name("name-a2", shared, field="properties.alias", language="en"),
                    name(
                        "name-a3", "虚构灯园", field="properties.alias", language="zh"
                    ),
                ),
            ),
            observation(
                "observation-b",
                "ofac_sdn",
                "17",
                (
                    name("name-b1", shared, field="sdnEntry.lastName"),
                    name(
                        "name-b2",
                        self.long_name,
                        field="sdnEntry.akaList.aka.lastName",
                        attrs=(("category", "weak"), ("type", "a.k.a.")),
                    ),
                ),
            ),
            observation(
                "observation-c",
                "eu_consolidated",
                "17",
                (
                    name(
                        "name-c1",
                        "ＦＩＣＴＩＯＮＡＬ　ＬＵＭＥＮ  ORCHARD",
                        field="sanctionEntity.nameAlias@wholeName",
                    ),
                ),
            ),
            observation(
                "observation-d",
                "opensanctions_un",
                "42",
                (
                    name("name-d1", "Fictional Aurora Boat"),
                    name("name-d2", "Fictional Mist", field="properties.weakAlias"),
                ),
                entity_type="vessel",
            ),
            observation(
                "observation-e",
                "eu_consolidated",
                "42",
                (name("name-e1", "Fictional Isolated Garden"),),
            ),
        )
        sources = []
        evidence = []
        for source in sorted({item.source_id for item in observations}):
            members = tuple(item for item in observations if item.source_id == source)
            selection = b"".join(encoded(asdict(item)) for item in members)
            selection_path = f"inputs/{source}.jsonl"
            permission = encoded({"fictional_permission": source})
            permission_path = f"inputs/{source}.permission.json"
            for path, payload in (
                (selection_path, selection),
                (permission_path, permission),
            ):
                (self.root / path).write_bytes(payload)
                evidence.append(corpus.SavedEvidence(path, digest(payload), payload))
            sources.append(
                corpus.ContinuationSource(
                    snapshot_id="snapshot-" + source,
                    source_id=source,
                    selection_path=selection_path,
                    selection_sha256=digest(selection),
                    selection_bytes=selection,
                    permission_path=permission_path,
                    permission_sha256=digest(permission),
                    permission_bytes=permission,
                    bound_permission_bytes=permission,
                    acquisition_origin="authored-fictional-readiness-fixture",
                    observations=members,
                )
            )
        receipt = encoded({"fixture": "fictional post-admission inputs"})
        self.receipt_path = self.input_dir / "receipt.json"
        self.receipt_path.write_bytes(receipt)
        evidence.append(
            corpus.SavedEvidence("inputs/receipt.json", digest(receipt), receipt)
        )
        input_manifest = encoded(
            {
                "schema_version": 1,
                "artifact_kind": "continuation-readiness-inputs-v1",
                "receipt": {"path": "inputs/receipt.json", "sha256": digest(receipt)},
                "release_authorized": False,
                "training_eligible": False,
                "evaluation_eligible": False,
                "fresh_final_eligible": False,
                "human_review_count": 0,
                "accepted_independent_families": 0,
                "evidence": [
                    {"path": item.path, "sha256": item.sha256} for item in evidence
                ],
                "sources": [
                    {
                        "source_id": source.source_id,
                        "selection": {
                            "path": source.selection_path,
                            "sha256": source.selection_sha256,
                        },
                        "permission": {
                            "path": source.permission_path,
                            "sha256": source.permission_sha256,
                        },
                    }
                    for source in sources
                ],
            }
        )
        self.preparation = corpus.ContinuationPreparation(
            receipt_sha256=digest(receipt),
            receipt_bytes=receipt,
            input_manifest_bytes=input_manifest,
            input_manifest_sha256=digest(input_manifest),
            evidence=tuple(evidence),
            sources=tuple(sources),
            observations=observations,
        )
        self.config = {
            "schema_version": 1,
            "scope": readiness.SCOPE,
            "receipt": {"path": "inputs/receipt.json", "sha256": digest(receipt)},
            "output_path": "data/preparation",
            "artifact_roots": ["inputs", "data"],
            "normalized_inputs": [
                {"path": source.selection_path, "sha256": source.selection_sha256}
                for source in sources
            ],
            "expected_counts": dict(EXPECTED_COUNTS),
            "limits": dict(readiness.LIMITS),
            "permissions": dict(readiness.RESTRICTIONS),
            "versions": {
                "normalization": links.READINESS_NORMALIZATION_VERSION,
                "nomination": links.READINESS_NOMINATION_VERSION,
                "unicode": links.READINESS_UNICODE_VERSION,
            },
            "entity_types": ["organization", "vessel"],
        }
        self.save_config()
        self.admissions = []

    def save_config(self):
        self.config_path.write_bytes(encoded(self.config))

    def admit(
        self, receipt_path, *, expected_receipt_sha256, evidence_root, checkpoint=None
    ):
        assert receipt_path == self.receipt_path
        assert expected_receipt_sha256 == digest(self.preparation.receipt_bytes)
        assert evidence_root == self.root
        self.admissions.append(receipt_path)
        if checkpoint:
            checkpoint()
        return self.preparation

    def prepare(self, *, guard=None):
        return readiness.prepare_readiness(
            self.config_path,
            self.output,
            project_root=self.root,
            guard=guard or safe_guard(),
        )

    def validate(self, *, guard=None):
        return readiness.validate_readiness(
            self.output, project_root=self.root, guard=guard or safe_guard()
        )


@pytest.fixture(autouse=True)
def no_fixture_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("readiness tests may not access the network")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    value = FictionalReadiness(tmp_path / "readiness-fixture")
    monkeypatch.setattr(corpus, "prepare_continuation_sources", value.admit)
    return value


def test_readiness_normalized_pairs_preserve_complete_names_and_qualifiers(fixture):
    payloads = readiness.assemble_readiness(fixture.preparation)
    assert set(payloads) == readiness.PAYLOAD_NAMES
    assert json.loads(payloads["summary.json"])["counts"] == EXPECTED_COUNTS
    observations = {
        item["observation_id"]: item for item in rows(payloads["observations.jsonl"])
    }
    assert {
        tuple(observations["observation-" + letter]["source_record_key"])
        for letter in "abc"
    } == {("opensanctions_un", "17"), ("ofac_sdn", "17"), ("eu_consolidated", "17")}
    aliases = [item for row in observations.values() for item in row["aliases"]]
    assert len(aliases) == 9
    assert next(item for item in aliases if item["evidence_id"] == "name-b2") == {
        "evidence_id": "name-b2",
        "value": fixture.long_name,
        "field": "sdnEntry.akaList.aka.lastName",
        "language": None,
        "attributes": [["category", "weak"], ["type", "a.k.a."]],
    }
    assert (
        observations["observation-c"]["aliases"][0]["value"]
        == "ＦＩＣＴＩＯＮＡＬ　ＬＵＭＥＮ  ORCHARD"
    )
    pairs = rows(payloads["nominations.jsonl"])
    assert {(item["left"], item["right"]) for item in pairs} == {
        ("observation-a", "observation-b"),
        ("observation-a", "observation-c"),
        ("observation-b", "observation-c"),
    }
    exact_pair = next(item for item in pairs if item["right"] == "observation-b")
    assert len(exact_pair["witnesses"]) == 4
    assert {item["left_evidence_id"] for item in exact_pair["witnesses"]} == {
        "name-a1",
        "name-a2",
    }
    assert all(
        item["preparation_input_sha256"] == fixture.preparation.input_manifest_sha256
        for item in pairs
    )


def test_readiness_quarantine_unions_records_without_discarding_valid_siblings(fixture):
    payloads = readiness.assemble_readiness(fixture.preparation)
    quarantine = {
        item["observation_id"]: item for item in rows(payloads["quarantine.jsonl"])
    }
    assert set(quarantine) == {"observation-" + letter for letter in "abcd"}
    assert quarantine["observation-b"]["name_restrictions"] == [
        {
            "evidence_id": "name-b2",
            "reasons": ["explicit_source_weak_name", "normalization_contract_rejected"],
            "excluded_from": [
                "positive_label_use",
                "negative_mining",
                "final_query_use",
                "matcher_input",
            ],
            "original_preserved": True,
        }
    ]
    assert quarantine["observation-d"]["component_id"] is None
    assert quarantine["observation-d"]["group_reasons"] == []
    assert quarantine["observation-d"]["name_restrictions"] == [
        {
            "evidence_id": "name-d2",
            "reasons": ["explicit_source_weak_name"],
            "excluded_from": [
                "positive_label_use",
                "negative_mining",
                "final_query_use",
            ],
            "original_preserved": True,
        }
    ]
    assert all(
        item["valid_sibling_names_discarded"] is False for item in quarantine.values()
    )
    assert all(
        item["identity_confirmed"] is False and item["human_resolution"] is None
        for item in quarantine.values()
    )
    (component,) = rows(payloads["components.jsonl"])
    assert component["observation_ids"] == ["observation-" + letter for letter in "abc"]
    assert component["identity_confirmed"] is False
    summary = json.loads(payloads["summary.json"])
    assert summary["flag_intersections"] == {
        "duplicate_and_weak_records": 1,
        "duplicate_and_overlength_records": 1,
        "weak_and_overlength_records": 1,
        "all_three_records": 1,
        "no_listed_flag_records": 1,
    }
    assert summary["pair_scope"] == {"within_source": 0, "cross_source": 3}
    diagnostics = summary["readiness_diagnostics"]
    assert diagnostics["component_size_histogram"] == {"3": 1}
    assert diagnostics["any_of_three_flags"] == {
        "groups": 4,
        "organizations": 3,
        "vessels": 1,
        "by_source": {"eu_consolidated": 1, "ofac_sdn": 1, "opensanctions_un": 2},
    }
    assert diagnostics["no_listed_flag"] == {
        "groups": 1,
        "organizations": 1,
        "vessels": 0,
        "by_source": {"eu_consolidated": 1},
    }
    assert diagnostics["at_least_two_distinct_normalized_nonweak_accepted_names"] == {
        "groups": 1,
        "organizations": 1,
        "vessels": 0,
        "by_source": {"opensanctions_un": 1},
    }
    assert diagnostics["two_names_and_no_listed_flag"] == {
        "groups": 0,
        "organizations": 0,
        "vessels": 0,
        "by_source": {},
    }
    assert summary["status"] == "unreviewed_preparation"
    assert (
        summary["human_decisions"]
        == summary["accepted_labels"]
        == summary["identity_merges"]
        == 0
    )
    assert summary["accepted_corpus_release"] is False
    assert all(value is False for value in summary["permissions"].values())


def test_readiness_deterministic_under_source_observation_and_alias_reordering(fixture):
    original = readiness.assemble_readiness(fixture.preparation)
    reversed_observations = tuple(
        replace(item, aliases=tuple(reversed(item.aliases)))
        for item in reversed(fixture.preparation.observations)
    )
    reordered = replace(
        fixture.preparation,
        observations=reversed_observations,
        sources=tuple(reversed(fixture.preparation.sources)),
        evidence=tuple(reversed(fixture.preparation.evidence)),
    )
    assert readiness.assemble_readiness(reordered) == original


@pytest.mark.parametrize(
    "change", ["manifest", "observation", "evidence", "source_key"]
)
def test_readiness_rejects_corrupt_or_ambiguous_preparation(fixture, change):
    preparation = fixture.preparation
    if change == "manifest":
        preparation = replace(preparation, input_manifest_bytes=b"{}\n")
    elif change == "observation":
        preparation = replace(
            preparation,
            observations=preparation.observations + preparation.observations[:1],
        )
    elif change == "evidence":
        first, *others = preparation.observations
        first = replace(first, aliases=first.aliases + first.aliases[:1])
        preparation = replace(preparation, observations=(first, *others))
    else:
        first, *others = preparation.observations
        first = replace(first, source_record_key=("ofac_sdn", first.provider_id))
        preparation = replace(preparation, observations=(first, *others))
    with pytest.raises(readiness.ReadinessError):
        readiness.assemble_readiness(preparation)


def test_readiness_assembly_honors_resource_checkpoint(fixture):
    calls = []

    def stop():
        calls.append(True)
        raise ResourceStop("fictional_checkpoint_stop")

    with pytest.raises(ResourceStop, match="fictional_checkpoint_stop"):
        readiness.assemble_readiness(fixture.preparation, checkpoint=stop)
    assert len(calls) == 1
    assert not fixture.output.exists()


def test_readiness_prepare_validate_are_private_and_never_overwrite(
    fixture, monkeypatch
):
    written = []
    original = readiness._write_payload

    def record_write(directory_fd, name, payload):
        if name == "manifest.json":
            assert set(os.listdir(directory_fd)) == readiness.PAYLOAD_NAMES
        written.append(name)
        original(directory_fd, name, payload)

    monkeypatch.setattr(readiness, "_write_payload", record_write)
    summary = fixture.prepare()
    assert summary["counts"] == EXPECTED_COUNTS
    assert written[-1] == "manifest.json"
    saved = {path.name: path.read_bytes() for path in fixture.output.iterdir()}
    assert stat.S_IMODE(fixture.output.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o400 for path in fixture.output.iterdir()
    )
    assert fixture.validate() == summary
    assert len(fixture.admissions) == 2
    with pytest.raises(FileExistsError):
        fixture.prepare()
    assert {path.name: path.read_bytes() for path in fixture.output.iterdir()} == saved
    assert len(fixture.admissions) == 2


def rewrite_artifact(fixture, filename, value, *, rehash):
    path = fixture.output / filename
    payload = (
        encoded(value)
        if filename.endswith(".json")
        else b"".join(encoded(row) for row in value)
    )
    path.chmod(0o600)
    path.write_bytes(payload)
    path.chmod(0o400)
    if rehash:
        manifest_path = fixture.output / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        manifest["files"][filename] = {"sha256": digest(payload), "bytes": len(payload)}
        manifest_path.chmod(0o600)
        manifest_path.write_bytes(encoded(manifest))
        manifest_path.chmod(0o400)


@pytest.mark.parametrize("rehash", [False, True])
@pytest.mark.parametrize("artifact", ["names", "links", "quarantine", "summary"])
def test_readiness_validation_regenerates_content_not_editable_self_hashes(
    fixture, artifact, rehash
):
    fixture.prepare()
    if artifact == "names":
        filename = "observations.jsonl"
        value = rows((fixture.output / filename).read_bytes())
        value[0]["aliases"][0]["value"] = "Fictional changed original"
    elif artifact == "links":
        filename = "nominations.jsonl"
        value = rows((fixture.output / filename).read_bytes())
        value[0]["right"] = "observation-e"
    elif artifact == "quarantine":
        filename = "quarantine.jsonl"
        value = rows((fixture.output / filename).read_bytes())
        value[0]["identity_confirmed"] = True
        value[0]["human_resolution"] = "same_entity"
    else:
        filename = "summary.json"
        value = json.loads((fixture.output / filename).read_bytes())
        value["permissions"]["fresh_final_eligible"] = True
        value["accepted_labels"] = 1
    rewrite_artifact(fixture, filename, value, rehash=rehash)
    with pytest.raises(readiness.ReadinessError):
        fixture.validate()


def test_readiness_forged_manifest_cannot_authorize_eligibility(fixture):
    fixture.prepare()
    path = fixture.output / "manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["permissions"]["training_allowed"] = True
    manifest["accepted_corpus_release"] = True
    path.chmod(0o600)
    path.write_bytes(encoded(manifest))
    path.chmod(0o400)
    with pytest.raises(readiness.ReadinessError, match="manifest"):
        fixture.validate()


@pytest.mark.parametrize("position", [1, 3, 7])
def test_readiness_interruption_preserves_partial_files_without_completion(
    fixture, monkeypatch, position
):
    original = readiness._write_payload
    attempted = []

    def interrupted(directory_fd, name, payload):
        attempted.append(name)
        if len(attempted) == position:
            raise OSError("fictional interrupted write")
        original(directory_fd, name, payload)

    monkeypatch.setattr(readiness, "_write_payload", interrupted)
    with pytest.raises(OSError, match="fictional interrupted write"):
        fixture.prepare()
    assert fixture.output.is_dir()
    assert not (fixture.output / "manifest.json").exists()
    saved = {path.name: path.read_bytes() for path in fixture.output.iterdir()}
    assert len(saved) == position - 1
    with pytest.raises(readiness.ReadinessError, match="incomplete"):
        fixture.validate()
    with pytest.raises(FileExistsError):
        fixture.prepare()
    assert {path.name: path.read_bytes() for path in fixture.output.iterdir()} == saved


def test_readiness_guard_deadline_stops_partial_output_before_manifest(
    fixture, monkeypatch
):
    clock = [0.0]
    guard = safe_guard(clock=lambda: clock[0])
    original = readiness._write_payload

    def expires(directory_fd, name, payload):
        original(directory_fd, name, payload)
        clock[0] = 3601.0

    monkeypatch.setattr(readiness, "_write_payload", expires)
    with pytest.raises(ResourceStop, match="session_deadline"):
        fixture.prepare(guard=guard)
    assert len(list(fixture.output.iterdir())) == 1
    assert not (fixture.output / "manifest.json").exists()


def test_readiness_low_disk_fails_before_output_directory(fixture):
    guard = ResourceGuard(
        probe=lambda: ResourceSnapshot(20_000_000, GIB, 0, 0.5, False)
    )
    with pytest.raises(ResourceStop, match="free_disk_limit"):
        fixture.prepare(guard=guard)
    assert not fixture.output.exists()
    assert fixture.admissions == []


def test_readiness_validation_counts_unrelated_files_in_preparation_root(fixture):
    fixture.prepare()
    unrelated = fixture.output.parent / "fictional-oversized.log"
    with unrelated.open("wb") as stream:
        stream.truncate(readiness.MAX_BYTES + 1)
    with pytest.raises(readiness.ReadinessError):
        fixture.validate()
    assert unrelated.stat().st_size == readiness.MAX_BYTES + 1


@pytest.mark.parametrize("target", ["output", "parent", "artifact"])
def test_readiness_symlink_paths_fail_without_changing_target(fixture, target):
    outside = fixture.root / "external"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("fictional untouched sentinel")
    if target == "output":
        fixture.output.symlink_to(outside, target_is_directory=True)
        action = fixture.prepare
    elif target == "parent":
        fixture.output.parent.rmdir()
        fixture.output.parent.symlink_to(outside, target_is_directory=True)
        action = fixture.prepare
    else:
        fixture.prepare()
        artifact = fixture.output / "observations.jsonl"
        artifact.unlink()
        artifact.symlink_to(sentinel)
        action = fixture.validate
    with pytest.raises((ValueError, OSError)):
        action()
    assert sentinel.read_text() == "fictional untouched sentinel"
    assert list(outside.iterdir()) == [sentinel]


@pytest.mark.parametrize(
    "change", ["missing", "extra", "public_file", "public_directory"]
)
def test_readiness_incomplete_or_nonprivate_preparation_is_rejected(fixture, change):
    fixture.prepare()
    if change == "missing":
        (fixture.output / "manifest.json").unlink()
    elif change == "extra":
        (fixture.output / "unexpected.txt").write_text("fictional extra")
    elif change == "public_file":
        (fixture.output / "observations.jsonl").chmod(0o444)
    else:
        fixture.output.chmod(0o755)
    with pytest.raises(readiness.ReadinessError):
        fixture.validate()


@pytest.mark.parametrize(
    "change",
    ["permission", "counts", "version", "types", "limits", "reservation", "output"],
)
def test_readiness_config_does_not_expand_approved_scope(fixture, change):
    if change == "permission":
        fixture.config["permissions"]["human_review_execution_allowed"] = True
    elif change == "counts":
        fixture.config["expected_counts"]["observations"] += 1
    elif change == "version":
        fixture.config["versions"]["normalization"] = "different-normalization"
    elif change == "types":
        fixture.config["entity_types"].append("person")
    elif change == "limits":
        fixture.config["limits"]["max_new_artifact_bytes"] += 1
    elif change == "reservation":
        fixture.config["normalized_inputs"].append(
            deepcopy(fixture.config["normalized_inputs"][0])
        )
    else:
        fixture.config["output_path"] = "data/another-preparation"
    fixture.save_config()
    with pytest.raises(readiness.ReadinessError):
        fixture.prepare()
    assert not fixture.output.exists()


def test_readiness_changed_source_after_writes_prevents_manifest_commit(
    fixture, monkeypatch
):
    original = readiness._write_payload
    selection = fixture.root / fixture.preparation.sources[0].selection_path
    changed = False

    def changes_source(directory_fd, name, payload):
        nonlocal changed
        original(directory_fd, name, payload)
        if not changed:
            selection.write_bytes(selection.read_bytes() + b"\n")
            changed = True

    monkeypatch.setattr(readiness, "_write_payload", changes_source)
    with pytest.raises((readiness.ReadinessError, corpus.CorpusValidationError)):
        fixture.prepare()
    assert fixture.output.is_dir()
    assert not (fixture.output / "manifest.json").exists()


def test_readiness_changed_config_during_validation_is_rejected(fixture, monkeypatch):
    fixture.prepare()
    original = readiness.assemble_readiness

    def changes_config(preparation, *, checkpoint=None):
        result = original(preparation, checkpoint=checkpoint)
        fixture.config_path.write_bytes(fixture.config_path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(readiness, "assemble_readiness", changes_config)
    with pytest.raises(readiness.ReadinessError):
        fixture.validate()


def test_readiness_cli_installs_network_denial_and_keeps_failure_output_aggregate():
    code = """
import socket
from watchlist import corpus_readiness as readiness

def attempted_network(*args, **kwargs):
    try:
        socket.socket()
    except readiness.ReadinessError as error:
        assert str(error) == 'readiness_network_forbidden'
        raise
    raise RuntimeError('network denial was absent')

readiness.prepare_readiness = attempted_network
raise SystemExit(readiness.main(['prepare', '--config', 'fictional.json', '--output', 'fictional-output']))
"""
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 1
    assert json.loads(completed.stdout) == {
        "status": "failed",
        "reason": "readiness_validation_or_resource_failure",
    }
    assert completed.stderr == ""


def test_readiness_actual_fictional_continuation_admission_round_trip(tmp_path):
    from test_corpus import ContinuationInputs

    inputs = ContinuationInputs(tmp_path / "fictional-continuation")
    preparation = inputs.prepare()
    payloads = readiness.assemble_readiness(preparation)
    counts = json.loads(payloads["summary.json"])["counts"]
    (inputs.root / "config").mkdir()
    (inputs.root / "readiness-output").mkdir()
    output = inputs.root / "readiness-output" / "preparation"
    config_path = inputs.root / "config" / "corpus-readiness-v1.json"
    config = {
        "schema_version": 1,
        "scope": readiness.SCOPE,
        "receipt": {
            "path": "continuation-run/receipt.json",
            "sha256": digest(inputs.receipt_path.read_bytes()),
        },
        "output_path": "readiness-output/preparation",
        "artifact_roots": ["continuation-run", "readiness-output"],
        "normalized_inputs": [
            {"path": source.selection_path, "sha256": source.selection_sha256}
            for source in preparation.sources
        ],
        "expected_counts": counts,
        "limits": dict(readiness.LIMITS),
        "permissions": dict(readiness.RESTRICTIONS),
        "versions": {
            "normalization": links.READINESS_NORMALIZATION_VERSION,
            "nomination": links.READINESS_NOMINATION_VERSION,
            "unicode": links.READINESS_UNICODE_VERSION,
        },
        "entity_types": ["organization", "vessel"],
    }
    config_path.write_bytes(encoded(config))
    before = {
        item.path: (inputs.root / item.path).read_bytes()
        for item in preparation.evidence
    }
    result = readiness.prepare_readiness(
        config_path, output, project_root=inputs.root, guard=safe_guard()
    )
    assert result["counts"] == counts
    assert result["counts"]["observations"] == len(preparation.observations)
    assert result["accepted_corpus_release"] is False
    assert (
        readiness.validate_readiness(
            output, project_root=inputs.root, guard=safe_guard()
        )
        == result
    )
    assert before == {path: (inputs.root / path).read_bytes() for path in before}
    source = inputs.root / preparation.sources[0].selection_path
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises((readiness.ReadinessError, corpus.CorpusValidationError)):
        readiness.validate_readiness(
            output, project_root=inputs.root, guard=safe_guard()
        )
