"""Frozen, inert reader for phase-07a v1 archives.

Only normalized SQLite copies are opened. The reader uses no live application,
LangGraph, model, preservation script, or deserializer that revives Python types.
The receipt intentionally retains the Step 00 format for archive comparisons.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import struct
from typing import Any, NoReturn
import unicodedata
from uuid import UUID


class ArchiveError(ValueError):
    """The archive does not satisfy the frozen, read-only v1 contract."""


def _pv1_fail(message: str) -> NoReturn:
    raise ArchiveError("v1 archive verification: " + message)


def _pv1_canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        _pv1_fail("unsupported canonical JSON value: " + type(exc).__name__)


def _pv1_digest(value: Any) -> str:
    return hashlib.sha256(_pv1_canonical(value)).hexdigest()


def _pv1_no_symlink(path: Path, *, allow_missing: bool = False) -> Path:
    """Check every path component before reading; resolving first hides links."""
    path = Path(path).absolute()
    if ".." in path.parts:
        _pv1_fail("parent traversal is not an archive path")
    for component in (*reversed(path.parents), path):
        try:
            mode = component.lstat().st_mode
        except FileNotFoundError:
            if allow_missing:
                return path
            _pv1_fail("missing archive path")
        if stat.S_ISLNK(mode):
            _pv1_fail("symlink component in archive path")
        if component != path and not stat.S_ISDIR(mode):
            _pv1_fail("non-directory archive path component")
    return path


def _pv1_regular(path: Path, maximum: int) -> Path:
    path = _pv1_no_symlink(path)
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
        _pv1_fail("nonregular or oversized archive file")
    return path


def _pv1_sidecars(path: Path) -> bool:
    return any(os.path.lexists(str(path) + suffix) for suffix in ("-wal", "-shm", "-journal"))


def _pv1_file_hash(path: Path) -> str:
    _pv1_regular(path, 512 * 1024 * 1024)
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _pv1_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            _pv1_fail("duplicate JSON object key")
        result[key] = value
    return result


def _pv1_json(raw: Any, label: str, *, canonical: bool = False) -> Any:
    if not isinstance(raw, (str, bytes)) or len(raw) > 16 * 1024 * 1024:
        _pv1_fail(label + ": missing or oversized JSON")
    try:
        value = json.loads(raw, object_pairs_hook=_pv1_pairs,
                           parse_constant=lambda token: _pv1_fail("nonfinite JSON number"))
        encoded = _pv1_canonical(value)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        _pv1_fail(label + ": invalid JSON: " + type(exc).__name__)
    if canonical and encoded != (raw.encode("utf-8") if isinstance(raw, str) else raw):
        _pv1_fail(label + ": noncanonical JSON")
    return value


class _PV1Extension:
    """Opaque MessagePack bytes, never an imported or constructed application class."""
    __slots__ = ("code", "payload", "decoded")

    def __init__(self, code: int, payload: bytes) -> None:
        self.code, self.payload = code, payload
        self.decoded = None


class _PV1MessagePack:
    """Bounded inert decoder for the pinned v1 primitive checkpoint format."""
    def __init__(self, raw: bytes) -> None:
        if not isinstance(raw, bytes) or len(raw) > 16 * 1024 * 1024:
            _pv1_fail("missing or oversized MessagePack blob")
        self.raw, self.position, self.nodes = raw, 0, 0

    def take(self, size: int) -> bytes:
        if size < 0 or self.position + size > len(self.raw):
            _pv1_fail("truncated MessagePack blob")
        start = self.position
        self.position += size
        return self.raw[start:self.position]

    def number(self, fmt: str) -> Any:
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def length(self, size: int) -> int:
        return self.number({1: ">B", 2: ">H", 4: ">I"}[size])

    def string(self, size: int) -> str:
        try:
            return self.take(size).decode("utf-8")
        except UnicodeError:
            _pv1_fail("invalid MessagePack UTF-8")

    def array(self, size: int, depth: int) -> list[Any]:
        if size > 100000:
            _pv1_fail("MessagePack array exceeds item limit")
        return [self.value(depth + 1) for _ in range(size)]

    def mapping(self, size: int, depth: int) -> dict[Any, Any]:
        if size > 100000:
            _pv1_fail("MessagePack map exceeds item limit")
        result = {}
        for _ in range(size):
            key = self.value(depth + 1)
            if type(key) not in (str, int, bool, bytes) or key in result:
                _pv1_fail("unsupported or duplicate MessagePack map key")
            result[key] = self.value(depth + 1)
        return result

    def value(self, depth: int = 0) -> Any:
        self.nodes += 1
        if depth > 64 or self.nodes > 200000:
            _pv1_fail("MessagePack nesting or node budget exceeded")
        code = self.number(">B")
        if code <= 0x7f:
            return code
        if code >= 0xe0:
            return code - 256
        if 0xa0 <= code <= 0xbf:
            return self.string(code & 31)
        if 0x90 <= code <= 0x9f:
            return self.array(code & 15, depth)
        if 0x80 <= code <= 0x8f:
            return self.mapping(code & 15, depth)
        if code == 0xc0:
            return None
        if code in (0xc2, 0xc3):
            return code == 0xc3
        formats = {0xca: ">f", 0xcb: ">d", 0xcc: ">B", 0xcd: ">H",
                   0xce: ">I", 0xcf: ">Q", 0xd0: ">b", 0xd1: ">h",
                   0xd2: ">i", 0xd3: ">q"}
        if code in formats:
            value = self.number(formats[code])
            if isinstance(value, float) and not math.isfinite(value):
                _pv1_fail("nonfinite MessagePack number")
            return value
        if code in (0xc4, 0xc5, 0xc6):
            return self.take(self.length({0xc4: 1, 0xc5: 2, 0xc6: 4}[code]))
        if code in (0xd9, 0xda, 0xdb):
            return self.string(self.length({0xd9: 1, 0xda: 2, 0xdb: 4}[code]))
        if code in (0xdc, 0xdd):
            return self.array(self.length(2 if code == 0xdc else 4), depth)
        if code in (0xde, 0xdf):
            return self.mapping(self.length(2 if code == 0xde else 4), depth)
        if code in (0xc7, 0xc8, 0xc9, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8):
            fixed = {0xd4: 1, 0xd5: 2, 0xd6: 4, 0xd7: 8, 0xd8: 16}
            size = fixed[code] if code in fixed else self.length({0xc7: 1, 0xc8: 2, 0xc9: 4}[code])
            extension_code = self.number(">b")
            return _PV1Extension(extension_code, self.take(size))
        _pv1_fail("unsupported MessagePack opcode")

    def decode(self) -> Any:
        result = self.value()
        if self.position != len(self.raw):
            _pv1_fail("trailing bytes in MessagePack blob")
        return result


def _pv1_inert_shape(value: Any, label: str, *, allow_interrupt: bool = False, depth: int = 0) -> None:
    """Accept JSON primitives and one pinned interrupt data shape, never classes."""
    if depth > 64:
        _pv1_fail(label + ": inert value nesting limit")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if isinstance(value, list):
        for item in value:
            _pv1_inert_shape(item, label, allow_interrupt=allow_interrupt, depth=depth + 1)
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            _pv1_fail(label + ": non-string key outside the pinned JSON state contract")
        for item in value.values():
            _pv1_inert_shape(item, label, allow_interrupt=allow_interrupt, depth=depth + 1)
        return
    if isinstance(value, _PV1Extension) and allow_interrupt and value.code == 2:
        payload = _PV1MessagePack(value.payload).decode()
        if (not isinstance(payload, list) or len(payload) != 3
                or payload[:2] != ["langgraph.types", "Interrupt"]):
            _pv1_fail(label + ": unknown MessagePack extension constructor shape")
        fields = payload[2]
        if not isinstance(fields, dict) or set(fields) != {"value", "id", "response_schema"}:
            _pv1_fail(label + ": unsupported pinned interrupt fields")
        if fields["response_schema"] is not None:
            _pv1_fail(label + ": v1 interrupt has unexpected response schema")
        _pv1_text(fields["id"], "interrupt ID", 128)
        _pv1_inert_shape(fields["value"], label + " interrupt value", depth=depth + 1)
        value.decoded = fields
        return
    _pv1_fail(label + ": unsupported bytes, extension, or non-JSON value")


def _pv1_decode(kind: str, raw: bytes, label: str, *, allow_interrupt: bool = False) -> Any:
    if not isinstance(raw, bytes):
        _pv1_fail(label + ": serialized value is not bytes")
    if kind == "msgpack":
        value = _PV1MessagePack(raw).decode()
    elif kind == "json":
        value = _pv1_json(raw, label)
    elif kind == "null" and raw == b"":
        value = None
    else:
        _pv1_fail(label + ": unsupported serialization type " + repr(kind))
    _pv1_inert_shape(value, label, allow_interrupt=allow_interrupt)
    return value


_PV1_STATE = ("schema_version", "workflow_version", "workflow_sha256", "thread_id",
              "audit_id", "parent_audit_id", "created_at", "query", "normalized_query",
              "recipe", "candidates", "evidence", "retrieval", "evidence_sha256",
              "review_revision", "review_status", "reviewer_decision", "explanation",
              "error", "audit_status", "audit_event_id", "audit_head_sha256")
_PV1_PACKET = ("schema_version", "workflow_version", "workflow_sha256", "thread_id", "audit_id",
               "query", "normalized_query", "recipe", "candidates", "evidence", "retrieval", "review_revision")
_PV1_REVIEW = ("submission_id", "review_revision", "evidence_sha256", "expected_checkpoint_id",
               "outcome", "candidate_entity_id", "reviewer_id", "reason", "submitted_at")
_PV1_HEADER = ("schema_version", "workflow_version", "workflow_sha256", "thread_id", "audit_id",
               "parent_audit_id", "created_at", "query", "recipe")
_PV1_FINAL = ("evidence_sha256", "reviewer_decision", "explanation", "error")
_PV1_NODES = ("__start__", "normalize", "retrieve_e5", "format_candidates",
              "prepare_review", "human_review", "explain", "audit_record")
_PV1_TRIGGERS = {name: "__start__" if name == "__start__" else "branch:to:" + name
                 for name in _PV1_NODES}
_PV1_CHANNELS = set(_PV1_STATE) | set(_PV1_TRIGGERS.values())
_PV1_CONTROL_INDEX = {"__error__": -1, "__interrupt__": -3, "__resume__": -4}
_PV1_NULL_TASK = "00000000-0000-0000-0000-000000000000"


def _pv1_initial(value: dict[str, Any]) -> None:
    """Validate exactly the envelope written by frozen ReviewService.start.

    Blank or 201–1000 character strings are valid request envelopes: the v1
    normalize node records their validation error later in the graph.
    """
    if not isinstance(value["query"], str) or len(value["query"]) > 1000:
        _pv1_fail("initial query violates the v1 request envelope")
    if not isinstance(value["recipe"], dict):
        _pv1_fail("initial recipe must be an object")
    for key in ("audit_id", "thread_id"):
        try:
            if str(UUID(value[key])) != value[key] or UUID(value[key]).version != 4:
                _pv1_fail("initial case identity is not a canonical UUID4")
        except (ValueError, TypeError, AttributeError):
            _pv1_fail("invalid initial case identity")
    if value["parent_audit_id"] is not None:
        _pv1_text(value["parent_audit_id"], "parent audit ID", 36)
    _pv1_text(value["created_at"], "initial creation timestamp", 100)
    defaults = {
        "normalized_query": None, "candidates": [], "evidence": [], "retrieval": None,
        "evidence_sha256": None, "review_status": "not_requested", "reviewer_decision": None,
        "explanation": None, "error": None, "audit_status": "pending",
        "audit_event_id": None, "audit_head_sha256": None,
    }
    if (any(value[key] != expected for key, expected in defaults.items())
            or type(value["review_revision"]) is not int or value["review_revision"] != 1):
        _pv1_fail("initial fields differ from the frozen empty request state")


def _pv1_version(value: Any) -> None:
    """Validate the pinned SQLite saver's monotonically ordered version string."""
    if not isinstance(value, str) or len(value) > 64:
        _pv1_fail("unsupported channel version")
    counter, separator, fraction = value.partition(".")
    if separator != "." or len(counter) != 32 or not counter.isascii() or not counter.isdigit() or int(counter) < 1:
        _pv1_fail("invalid channel version counter")
    try:
        number = float(fraction)
    except ValueError:
        _pv1_fail("invalid channel version random suffix")
    if not math.isfinite(number) or not 0 <= number < 1 or f"{number:016}" != fraction:
        _pv1_fail("invalid channel version suffix")


def _pv1_schedule(value: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    """Derive frozen v1 PULL tasks from channel availability and seen versions.

    A channel holding None is available. No node code, channel object, scheduler,
    task constructor, or archived class is imported or invoked by this reader.
    """
    fields = {"v", "ts", "id", "channel_values", "channel_versions", "versions_seen", "updated_channels"}
    if set(value) != fields or type(value["v"]) is not int or value["v"] != 4:
        _pv1_fail("unsupported checkpoint version or envelope")
    _pv1_text(value["ts"], "checkpoint timestamp", 100)
    try:
        if str(UUID(value["id"])) != value["id"]:
            _pv1_fail("noncanonical checkpoint ID")
    except (ValueError, TypeError, AttributeError):
        _pv1_fail("invalid checkpoint ID")
    if (set(metadata) != {"source", "step", "parents"}
            or metadata["source"] not in ("input", "loop")
            or type(metadata["step"]) is not int or not -1 <= metadata["step"] <= 7
            or metadata["parents"] != {}
            or (metadata["source"] == "input") != (metadata["step"] == -1)):
        _pv1_fail("unsupported checkpoint scheduling metadata")
    channels, versions, seen = value["channel_values"], value["channel_versions"], value["versions_seen"]
    if (set(channels) - _PV1_CHANNELS or set(versions) - _PV1_CHANNELS
            or not set(channels).issubset(versions) or not versions):
        _pv1_fail("unknown channel or missing checkpoint channel version")
    for version in versions.values():
        _pv1_version(version)
    for node, previous in seen.items():
        if node not in (*_PV1_NODES, "__input__", "__interrupt__") or not isinstance(previous, dict):
            _pv1_fail("unknown node in checkpoint versions_seen")
        permitted = _PV1_CHANNELS if node == "__interrupt__" else set() if node == "__input__" else {_PV1_TRIGGERS[node]}
        if set(previous) - permitted:
            _pv1_fail("unexpected node trigger in checkpoint versions_seen")
        for channel, version in previous.items():
            _pv1_version(version)
            if channel not in versions or version > versions[channel]:
                _pv1_fail("seen version exceeds checkpoint channel version")
    if seen.get("__input__") != {}:
        _pv1_fail("missing pinned input scheduling marker")
    updated = value["updated_channels"]
    if (not isinstance(updated, list) or any(not isinstance(item, str) for item in updated)
            or updated != sorted(set(updated)) or not set(updated).issubset(versions)):
        _pv1_fail("invalid updated-channel scheduling metadata")
    for channel in set(channels) & set(_PV1_TRIGGERS.values()):
        if channel != "__start__" and channels[channel] is not None:
            _pv1_fail("nonempty frozen branch trigger")
    tasks = [node for node, trigger in _PV1_TRIGGERS.items()
             if trigger in channels and (node not in seen or versions[trigger] > seen[node].get(trigger, ""))]
    if len(tasks) > 1:
        _pv1_fail("parallel scheduling is unsupported by the frozen sequential graph")
    return tasks


def _pv1_history(snapshots: list[dict[str, Any]], initial: dict[str, Any],
                 states: dict[str, dict[str, Any]], submission: dict[str, Any] | None,
                 decoded_writes: dict[tuple[str, str, str], list[dict[str, Any]]]) -> None:
    """Check the single frozen path and its inert control/write associations.

    Task IDs remain opaque UUIDs, bound by one task path per checkpoint. Their
    runtime hash algorithm is not imported or executed. This is a reader for the
    v1 path, not an implementation of LangGraph or a facility for resuming it.
    """
    normal_path = ["__start__", "normalize", "retrieve_e5", "format_candidates",
                   "prepare_review", "human_review", "explain", "audit_record", None]
    error_path = ["__start__", "normalize", "explain", "audit_record", None]
    output_fields = {
        "__start__": set(_PV1_STATE) | {"branch:to:normalize"},
        "retrieve_e5": {"candidates", "evidence", "retrieval", "branch:to:format_candidates"},
        "format_candidates": {"evidence_sha256", "branch:to:prepare_review"},
        "prepare_review": {"review_status", "branch:to:human_review"},
        "human_review": {"reviewer_decision", "review_status", "branch:to:explain"},
        "explain": {"explanation", "branch:to:audit_record"},
        "audit_record": {"audit_event_id", "audit_head_sha256", "audit_status"},
    }
    previous = None
    used_task_ids: set[str] = set()
    for item in snapshots:
        row, checkpoint, step = item["row"], item["value"], item["metadata"]["step"]
        state = states.get(row["checkpoint_id"])
        path = error_path if state and state["error"] is not None else normal_path
        if step + 1 >= len(path):
            _pv1_fail("checkpoint step exceeds frozen workflow path")
        expected_node = path[step + 1]
        if item["next"] != ([] if expected_node is None else [expected_node]):
            _pv1_fail("checkpoint scheduling differs from frozen workflow stage")
        if previous is None:
            if step != -1 or row["parent_checkpoint_id"] is not None or checkpoint["channel_values"] != {"__start__": initial}:
                _pv1_fail("checkpoint history lacks its initial input envelope")
        else:
            parent = previous["value"]
            if row["parent_checkpoint_id"] != previous["row"]["checkpoint_id"] or step != previous["metadata"]["step"] + 1:
                _pv1_fail("checkpoint history is branched or skips a scheduling step")
            if not set(parent["channel_versions"]).issubset(checkpoint["channel_versions"]):
                _pv1_fail("checkpoint channel versions disappeared")
            if any(version > checkpoint["channel_versions"][channel] for channel, version in parent["channel_versions"].items()):
                _pv1_fail("checkpoint channel version moved backwards")
            if len(previous["next"]) != 1:
                _pv1_fail("checkpoint follows a completed workflow")
            parent_node = previous["next"][0]
            trigger = _PV1_TRIGGERS[parent_node]
            if checkpoint["versions_seen"].get(parent_node) != {trigger: parent["channel_versions"][trigger]}:
                _pv1_fail("checkpoint did not record its preceding task trigger")
        if state is not None:
            if (state["audit_status"] == "committed") != (expected_node is None):
                _pv1_fail("audit completion disagrees with frozen scheduler stage")
            if state["audit_status"] not in ("pending", "committed") or state["review_status"] not in ("not_requested", "pending", "recorded"):
                _pv1_fail("unsupported v1 application status")
            if expected_node == "human_review" and (state["review_status"] != "pending" or state["reviewer_decision"] is not None or state["evidence_sha256"] is None):
                _pv1_fail("human-review scheduler stage lacks its pending packet")
        writes = decoded_writes.get((row["thread_id"], "", row["checkpoint_id"]), [])
        if writes and expected_node is None:
            _pv1_fail("completed checkpoint has pending writes")
        task_ids, outputs, controls = set(), {}, {}
        for entry in writes:
            record, value = entry["row"], entry["value"]
            task_id, channel = record["task_id"], record["channel"]
            try:
                if str(UUID(task_id)) != task_id:
                    _pv1_fail("noncanonical checkpoint task ID")
            except (ValueError, TypeError, AttributeError):
                _pv1_fail("invalid checkpoint task ID")
            if task_id == _PV1_NULL_TASK:
                if channel != "__resume__" or record["task_path"] != "" or expected_node != "human_review":
                    _pv1_fail("unsupported null-task control write")
            else:
                if record["task_path"] != "~__pregel_pull, " + str(expected_node):
                    _pv1_fail("checkpoint task path differs from scheduled node")
                task_ids.add(task_id)
            if channel == "__resume__":
                wanted = submission if task_id == _PV1_NULL_TASK else [submission]
                if expected_node != "human_review" or submission is None or value != wanted or submission["expected_checkpoint_id"] != row["checkpoint_id"]:
                    _pv1_fail("resume control differs from the durable review submission")
            elif channel == "__interrupt__":
                if expected_node != "human_review" or task_id == _PV1_NULL_TASK:
                    _pv1_fail("interrupt control is outside the human-review task")
                if not re.fullmatch(r"[0-9a-f]{32}", value[0].decoded["id"]):
                    _pv1_fail("invalid pinned interrupt ID")
            elif channel == "__error__":
                _pv1_text(value, "saved task error", 100000)
            elif channel in outputs:
                _pv1_fail("duplicate task output channel")
            else:
                outputs[channel] = value
            if channel in _PV1_CONTROL_INDEX:
                controls[channel] = value
        if len(task_ids) > 1 or used_task_ids & task_ids:
            _pv1_fail("inconsistent or reused checkpoint task identity")
        used_task_ids.update(task_ids)
        if "__resume__" in controls and "__interrupt__" not in controls:
            _pv1_fail("resume control lacks its saved human-review interrupt")
        if outputs:
            expected_outputs = output_fields.get(expected_node)
            if expected_node == "normalize":
                expected_outputs = ({"error", "branch:to:explain"} if "error" in outputs else
                                    {"normalized_query", "branch:to:retrieve_e5"})
            if set(outputs) != expected_outputs:
                _pv1_fail("task outputs differ from the frozen node contract")
            if any(value is not None for channel, value in outputs.items() if channel.startswith("branch:to:")):
                _pv1_fail("nonempty task branch output")
            if expected_node == "__start__" and any(outputs[key] != initial[key] for key in _PV1_STATE):
                _pv1_fail("input task output differs from the original case")
            if expected_node == "human_review" and (outputs["reviewer_decision"] != submission or outputs["review_status"] != "recorded"):
                _pv1_fail("human-review output differs from the durable submission")
            if expected_node == "prepare_review" and outputs["review_status"] != "pending":
                _pv1_fail("prepare-review task did not enter pending review")
        item["outputs"] = outputs
        if previous is not None:
            # Pinned LangGraph saves ordinary LastValue write batches and the
            # next checkpoint on independent background futures. An abrupt exit
            # can preserve the checkpoint before its preceding batch. Only
            # DeltaChannel writes receive an ordering barrier in that runtime;
            # this v1 graph has no DeltaChannels. Validate the surviving full
            # checkpoint's frozen transition instead of requiring that batch.
            parent_node = previous["next"][0]
            transition_fields = output_fields.get(parent_node)
            if parent_node == "normalize":
                transition_fields = ({"error", "branch:to:explain"} if state["error"] is not None else
                                     {"normalized_query", "branch:to:retrieve_e5"})
            if checkpoint["updated_channels"] != sorted(transition_fields):
                _pv1_fail("checkpoint updates differ from its preceding frozen node")
            parent_state = states.get(previous["row"]["checkpoint_id"], initial)
            if any(state[key] != parent_state[key] for key in _PV1_STATE if key not in transition_fields):
                _pv1_fail("checkpoint changed state outside its preceding node contract")
            if parent_node == "human_review" and (state["reviewer_decision"] != submission or state["review_status"] != "recorded"):
                _pv1_fail("checkpoint review transition differs from durable submission")
            if parent_node == "prepare_review" and state["review_status"] != "pending":
                _pv1_fail("checkpoint prepare transition did not enter pending review")
            if any(checkpoint["channel_values"].get(channel) != value for channel, value in previous["outputs"].items()):
                _pv1_fail("checkpoint differs from saved preceding task output")
            item["preceding_output_batch_present"] = bool(previous["outputs"])
        previous = item


def _pv1_text(value: Any, label: str, maximum: int = 10000) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _pv1_fail(label + ": invalid bounded text")


def _pv1_hex(value: Any, label: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        _pv1_fail(label + ": invalid SHA-256")


def _pv1_packet(value: Any, initial: dict[str, Any]) -> str:
    """Validate frozen packet evidence, candidate references and its digest."""
    if not isinstance(value, dict) or set(value) != set(_PV1_PACKET):
        _pv1_fail("packet fields differ from review-v1")
    for key in set(_PV1_HEADER) & set(_PV1_PACKET):
        if value[key] != initial[key]:
            _pv1_fail("packet/header mismatch: " + key)
    query = value["query"]
    if not isinstance(query, str) or len(query) > 200:
        _pv1_fail("packet query violates v1 normalization envelope")
    normalized = " ".join(unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", query).casefold()).split())
    if not normalized or len(normalized) > 200 or value["normalized_query"] != normalized:
        _pv1_fail("packet normalization mismatch")
    if type(value["review_revision"]) is not int or value["review_revision"] != 1:
        _pv1_fail("unsupported packet revision")
    candidates, evidence = value["candidates"], value["evidence"]
    if not isinstance(candidates, list) or len(candidates) > 5 or not isinstance(evidence, list) or len(evidence) > 10000:
        _pv1_fail("invalid candidate/evidence lists")
    evidence_fields = {"evidence_id", "entity_id", "alias_id", "original_text", "source", "synthetic", "provenance", "attribution"}
    candidate_fields = {"entity_id", "display_name", "entity_type", "rank", "matched_alias_id", "matched_alias", "evidence_ids", "similarity_score", "score_kind"}
    provenance_fields = {"snapshot_id", "dataset", "provider", "publisher", "source_url", "download_url", "retrieved_at", "source_updated_at", "export_version", "raw_sha256", "license_url"}
    by_id = {}
    for item in evidence:
        if not isinstance(item, dict) or set(item) != evidence_fields:
            _pv1_fail("invalid evidence fields")
        for key in evidence_fields - {"synthetic", "provenance"}:
            _pv1_text(item[key], "evidence " + key)
        if type(item["synthetic"]) is not bool or (not item["synthetic"] and not isinstance(item["provenance"], dict)):
            _pv1_fail("invalid evidence provenance/origin")
        provenance = item["provenance"]
        if provenance is not None:
            if not isinstance(provenance, dict) or set(provenance) != provenance_fields:
                _pv1_fail("invalid provenance fields")
            for key in provenance_fields - {"source_updated_at", "export_version"}:
                _pv1_text(provenance[key], "provenance " + key)
        if item["evidence_id"] in by_id:
            _pv1_fail("duplicate evidence ID")
        by_id[item["evidence_id"]] = item
    seen, used = set(), set()
    for rank, item in enumerate(candidates, 1):
        if not isinstance(item, dict) or set(item) != candidate_fields:
            _pv1_fail("invalid candidate fields")
        for key in ("entity_id", "display_name", "entity_type", "matched_alias_id", "matched_alias"):
            _pv1_text(item[key], "candidate " + key)
        if item["entity_id"] in seen or type(item["rank"]) is not int or item["rank"] != rank:
            _pv1_fail("duplicate candidate or invalid rank")
        seen.add(item["entity_id"])
        score = item["similarity_score"]
        if type(score) not in (int, float) or not math.isfinite(score) or not -1 <= score <= 1 or item["score_kind"] != "cosine_similarity":
            _pv1_fail("invalid candidate score")
        refs = item["evidence_ids"]
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) for ref in refs) or len(set(refs)) != len(refs):
            _pv1_fail("invalid candidate evidence references")
        linked = [by_id.get(ref) for ref in refs]
        if any(e is None or e["entity_id"] != item["entity_id"] for e in linked):
            _pv1_fail("cross-entity/missing evidence reference")
        if not any(e["alias_id"] == item["matched_alias_id"] and e["original_text"] == item["matched_alias"] for e in linked):
            _pv1_fail("winning alias missing from packet")
        used.update(refs)
    if used != set(by_id):
        _pv1_fail("orphan evidence")
    if not isinstance(value["retrieval"], dict) or value["retrieval"].get("reranker") != "disabled" or value["retrieval"].get("top_k") != 5:
        _pv1_fail("unsupported v1 retrieval manifest")
    return _pv1_digest(value)


def _pv1_submission(value: Any, packet: dict[str, Any], packet_hash: str) -> None:
    """Bind a saved review to its immutable packet without treating it as truth."""
    if not isinstance(value, dict) or set(value) != set(_PV1_REVIEW):
        _pv1_fail("submission fields differ from review-v1")
    for key in ("submission_id", "evidence_sha256", "expected_checkpoint_id", "reviewer_id", "reason", "submitted_at"):
        _pv1_text(value[key], "submission " + key, 1000)
    try:
        UUID(value["submission_id"])
    except (ValueError, TypeError, AttributeError):
        _pv1_fail("submission ID is not a UUID")
    if type(value["review_revision"]) is not int or value["review_revision"] != 1 or value["evidence_sha256"] != packet_hash:
        _pv1_fail("submission packet/revision mismatch")
    if value["outcome"] == "candidate_for_follow_up":
        if value["candidate_entity_id"] not in {c["entity_id"] for c in packet["candidates"]}:
            _pv1_fail("submission selected a record outside its packet")
    elif value["outcome"] in ("none_selected", "unresolved"):
        if value["candidate_entity_id"] is not None:
            _pv1_fail("unselected review has a candidate ID")
    else:
        _pv1_fail("unknown review outcome")


def _pv1_quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _pv1_rows(db: sqlite3.Connection, query: str, parameters: tuple = (), maximum: int = 100000) -> list[sqlite3.Row]:
    result = db.execute(query, parameters).fetchmany(maximum + 1)
    if len(result) > maximum:
        _pv1_fail("SQL row budget exceeded")
    return result


def _pv1_database(path: Path, relative: str) -> tuple[sqlite3.Connection, dict[str, Any]]:
    """Open one validated immutable copy and inventory its schema and integrity."""
    path = _pv1_regular(path, 512 * 1024 * 1024)
    if _pv1_sidecars(path):
        _pv1_fail("normalized database still has journal/sidecar files: " + relative)
    before = _pv1_file_hash(path)
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        if [row[0] for row in _pv1_rows(db, "PRAGMA integrity_check")] != ["ok"]:
            _pv1_fail("SQLite integrity failure: " + relative)
        if _pv1_rows(db, "PRAGMA foreign_key_check"):
            _pv1_fail("SQLite foreign-key failure: " + relative)
        schema = [dict(row) for row in _pv1_rows(db, "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        tables = {}
        for row in schema:
            if row["type"] != "table":
                continue
            if "VIRTUAL TABLE" in (row["sql"] or "").upper():
                _pv1_fail("unsupported virtual table: " + relative)
            name = row["name"]
            tables[name] = {"row_count": db.execute("SELECT COUNT(*) FROM " + _pv1_quote(name)).fetchone()[0],
                            "columns": [dict(r) for r in db.execute("PRAGMA table_info(" + _pv1_quote(name) + ")")],
                            "foreign_keys": [dict(r) for r in db.execute("PRAGMA foreign_key_list(" + _pv1_quote(name) + ")")]}
        receipt = {"path": relative, "sha256": before, "bytes": path.stat().st_size,
                   "user_version": db.execute("PRAGMA user_version").fetchone()[0],
                   "schema_sha256": _pv1_digest(schema), "schema": schema, "tables": tables,
                   "integrity_check": "ok", "foreign_key_check": "ok"}
        return db, receipt
    except BaseException:
        db.close()
        raise


def _pv1_expect_schema(receipt: dict[str, Any], expected: dict, version: int | None = None) -> None:
    if version is not None and receipt["user_version"] != version:
        _pv1_fail("unsupported database version: " + receipt["path"])
    if set(receipt["tables"]) != set(expected):
        _pv1_fail("unexpected table set: " + receipt["path"])
    if any(row["type"] in ("trigger", "view") for row in receipt["schema"]):
        _pv1_fail("unexpected trigger/view in v1 review store")
    for table, columns in expected.items():
        if tuple(column["name"] for column in receipt["tables"][table]["columns"]) != columns:
            _pv1_fail("unexpected v1 columns: " + table)
        integer_columns = {"revision", "sequence", "idx"}
        blob_columns = {"checkpoint", "metadata", "value"}
        nullable = {"cases": {"audit_id", "parent_audit_id"},
                    "review_submissions": {"submission_id"},
                    "checkpoints": {"parent_checkpoint_id", "type", "checkpoint", "metadata"},
                    "writes": {"type", "value"}}.get(table, set())
        for column in receipt["tables"][table]["columns"]:
            name = column["name"]
            declared = "INTEGER" if name in integer_columns else "BLOB" if name in blob_columns else "TEXT"
            default = "''" if name in ("checkpoint_ns", "task_path") else None
            if (column["type"].upper() != declared or column["notnull"] != int(name not in nullable)
                    or column["dflt_value"] != default):
                _pv1_fail("unexpected v1 column declaration: " + table + "." + name)


def _pv1_constraints(db: sqlite3.Connection, receipt: dict, primary_keys: dict,
                     foreign_keys: dict, extra_unique: dict) -> None:
    """Check declared keys too: valid rows alone do not prove the v1 schema."""
    for table, wanted in primary_keys.items():
        columns = receipt["tables"][table]["columns"]
        actual = tuple(column["name"] for column in sorted(columns, key=lambda c: c["pk"]) if column["pk"])
        if actual != wanted:
            _pv1_fail("unexpected primary key: " + table)
        groups = {}
        for row in receipt["tables"][table]["foreign_keys"]:
            if row["on_update"] != "NO ACTION" or row["on_delete"] != "NO ACTION":
                _pv1_fail("unexpected foreign-key action: " + table)
            groups.setdefault(row["id"], []).append(row)
        actual_fks = set()
        for group in groups.values():
            ordered = sorted(group, key=lambda row: row["seq"])
            actual_fks.add((ordered[0]["table"], tuple(row["from"] for row in ordered), tuple(row["to"] for row in ordered)))
        if actual_fks != set(foreign_keys.get(table, ())):
            _pv1_fail("unexpected declared foreign keys: " + table)
        unique = set()
        for index in db.execute("PRAGMA index_list(" + _pv1_quote(table) + ")"):
            if index["unique"] and not index["partial"]:
                unique.add(tuple(row["name"] for row in db.execute("PRAGMA index_info(" + _pv1_quote(index["name"]) + ")")))
        if not set(extra_unique.get(table, ())).issubset(unique):
            _pv1_fail("missing v1 unique constraint: " + table)


def _pv1_review_pair(ledger: sqlite3.Connection, checkpoint_db: sqlite3.Connection,
                     ledger_receipt: dict, checkpoint_receipt: dict) -> tuple[list[dict], dict, dict]:
    """Verify the frozen ledger/checkpoint pair and keep private details separate."""
    _pv1_expect_schema(ledger_receipt, {
        "cases": ("audit_id", "thread_id", "initial_json", "parent_audit_id"),
        "review_packets": ("audit_id", "revision", "packet_json", "sha256"),
        "review_submissions": ("submission_id", "audit_id", "revision", "payload_json", "sha256"),
        "audit_events": ("audit_id", "sequence", "event_key", "payload_json", "created_at", "previous_sha256", "event_sha256")}, 1)
    empty_checkpoint_store = not checkpoint_receipt["schema"]
    checkpoint_schema = {
        "checkpoints": ("thread_id", "checkpoint_ns", "checkpoint_id", "parent_checkpoint_id", "type", "checkpoint", "metadata"),
        "writes": ("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "task_path", "idx", "channel", "type", "value")}
    _pv1_expect_schema(checkpoint_receipt, {} if empty_checkpoint_store else checkpoint_schema, 0)
    _pv1_constraints(ledger, ledger_receipt,
        {"cases": ("audit_id",), "review_packets": ("audit_id", "revision"),
         "review_submissions": ("submission_id",), "audit_events": ("audit_id", "sequence")},
        {"cases": {("cases", ("parent_audit_id",), ("audit_id",))},
         "review_packets": {("cases", ("audit_id",), ("audit_id",))},
         "review_submissions": {("review_packets", ("audit_id", "revision"), ("audit_id", "revision"))},
         "audit_events": {("cases", ("audit_id",), ("audit_id",))}},
        {"cases": {("thread_id",)}, "review_submissions": {("audit_id", "revision")},
         "audit_events": {("audit_id", "event_key")}})
    if not empty_checkpoint_store:
        _pv1_constraints(checkpoint_db, checkpoint_receipt,
            {"checkpoints": ("thread_id", "checkpoint_ns", "checkpoint_id"),
             "writes": ("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx")}, {}, {})
    packet_sql = next(row["sql"] for row in ledger_receipt["schema"] if row["name"] == "review_packets")
    if "check(revision=1)" not in "".join(packet_sql.lower().split()):
        _pv1_fail("missing v1 fixed packet-revision constraint")
    cases = _pv1_rows(ledger, "SELECT * FROM cases ORDER BY audit_id", maximum=1000)
    case_by_thread = {row["thread_id"]: row for row in cases}
    if len(case_by_thread) != len(cases):
        _pv1_fail("duplicate case thread")
    checkpoints, by_thread = {}, {}
    checkpoint_rows = [] if empty_checkpoint_store else _pv1_rows(
        checkpoint_db, "SELECT * FROM checkpoints ORDER BY thread_id,checkpoint_ns,checkpoint_id")
    for row in checkpoint_rows:
        key = (row["thread_id"], row["checkpoint_ns"], row["checkpoint_id"])
        if row["thread_id"] not in case_by_thread or row["checkpoint_ns"] != "" or key in checkpoints:
            _pv1_fail("orphan, duplicate, or unsupported checkpoint namespace")
        value = _pv1_decode(row["type"], row["checkpoint"], "checkpoint")
        if not isinstance(value, dict) or value.get("id") != row["checkpoint_id"] or not isinstance(value.get("channel_values"), dict):
            _pv1_fail("checkpoint row/blob identity mismatch")
        for field in ("channel_versions", "versions_seen"):
            if not isinstance(value.get(field), dict):
                _pv1_fail("missing checkpoint scheduling metadata")
        metadata = _pv1_json(row["metadata"], "checkpoint metadata") if row["metadata"] is not None else {}
        if not isinstance(metadata, dict):
            _pv1_fail("checkpoint metadata is not an object")
        item = {"row": dict(row), "value": value, "metadata": metadata,
                "next": _pv1_schedule(value, metadata)}
        checkpoints[key] = item
        by_thread.setdefault(row["thread_id"], []).append(item)
    for key, item in checkpoints.items():
        parent = item["row"]["parent_checkpoint_id"]
        # Pinned checkpoint IDs increase monotonically. A strict decrease on
        # every parent edge proves acyclicity without a quadratic chain walk.
        if parent is not None and ((key[0], key[1], parent) not in checkpoints or parent >= key[2]):
            _pv1_fail("missing or nonmonotonic/cyclic checkpoint parent")
    writes, decoded_writes = {}, {}
    write_receipts = []
    write_rows = [] if empty_checkpoint_store else _pv1_rows(
        checkpoint_db, "SELECT * FROM writes ORDER BY thread_id,checkpoint_ns,checkpoint_id,task_id,idx")
    for row in write_rows:
        key = (row["thread_id"], row["checkpoint_ns"], row["checkpoint_id"])
        if key not in checkpoints:
            _pv1_fail("orphan checkpoint write")
        channel = row["channel"]
        if channel not in _PV1_CHANNELS | set(_PV1_CONTROL_INDEX):
            _pv1_fail("unknown checkpoint write channel")
        if (type(row["idx"]) is not int or
                (row["idx"] != _PV1_CONTROL_INDEX[channel] if channel in _PV1_CONTROL_INDEX else row["idx"] < 0)):
            _pv1_fail("invalid checkpoint control-write index")
        write_value = _pv1_decode(row["type"], row["value"], "checkpoint write",
                                  allow_interrupt=row["channel"] == "__interrupt__")
        if row["channel"] == "__interrupt__":
            if (not isinstance(write_value, list) or len(write_value) != 1
                    or not isinstance(write_value[0], _PV1Extension)):
                _pv1_fail("unexpected v1 interrupt control-write shape")
            interrupt = write_value[0].decoded["value"]
            fields = {"thread_id", "audit_id", "review_revision", "evidence_sha256", "message"}
            if not isinstance(interrupt, dict) or set(interrupt) != fields:
                _pv1_fail("unexpected v1 human-review interrupt payload")
            channels = checkpoints[key]["value"]["channel_values"]
            for field in fields - {"message"}:
                if interrupt[field] != channels.get(field):
                    _pv1_fail("interrupt payload differs from its checkpoint: " + field)
            _pv1_text(interrupt["message"], "interrupt message", 5000)
        writes.setdefault(key, []).append(row["channel"])
        decoded_writes.setdefault(key, []).append({"row": dict(row), "value": write_value})
        write_receipts.append({k: row[k] for k in ("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "task_path", "idx", "channel", "type")} | {"value_sha256": hashlib.sha256(row["value"]).hexdigest()})
    results, states = [], {}
    for case in cases:
        aid, thread = case["audit_id"], case["thread_id"]
        initial = _pv1_json(case["initial_json"], "case initial", canonical=True)
        if not isinstance(initial, dict) or set(initial) != set(_PV1_STATE):
            _pv1_fail("initial fields differ from review-v1")
        if initial["audit_id"] != aid or initial["thread_id"] != thread or initial["parent_audit_id"] != case["parent_audit_id"]:
            _pv1_fail("case row/header identity mismatch")
        if initial["schema_version"] != "review-v1" or initial["workflow_version"] != "phase-07a-v1":
            _pv1_fail("unsupported case schema/workflow")
        _pv1_hex(initial["workflow_sha256"], "workflow digest")
        _pv1_initial(initial)
        events, previous, ordered = {}, "", []
        for count, row in enumerate(_pv1_rows(ledger, "SELECT * FROM audit_events WHERE audit_id=? ORDER BY sequence", (aid,)), 1):
            envelope = {k: row[k] for k in ("audit_id", "sequence", "event_key", "payload_json", "created_at", "previous_sha256")}
            if row["sequence"] != count or row["previous_sha256"] != previous or _pv1_digest(envelope) != row["event_sha256"]:
                _pv1_fail("audit chain failure for " + aid)
            if row["event_key"] in events:
                _pv1_fail("duplicate audit event key")
            payload = _pv1_json(row["payload_json"], "audit payload", canonical=True)
            events[row["event_key"]] = {"row": dict(row), "payload": payload}
            ordered.append(row["event_key"])
            previous = row["event_sha256"]
        if not ordered or ordered[0] != "request_created" or events["request_created"]["payload"] != initial:
            _pv1_fail("missing/mismatched case creation event")
        semantic = [key for key in ordered if not key.startswith("attempt:")]
        if any(key not in ("request_created", "suggestions_ready", "review_submitted", "case_finalized") for key in semantic):
            _pv1_fail("unknown v1 semantic audit event")
        if semantic != sorted(semantic, key=("request_created", "suggestions_ready", "review_submitted", "case_finalized").index):
            _pv1_fail("invalid semantic audit event order")
        packet_rows = _pv1_rows(ledger, "SELECT * FROM review_packets WHERE audit_id=?", (aid,))
        submission_rows = _pv1_rows(ledger, "SELECT * FROM review_submissions WHERE audit_id=?", (aid,))
        if len(packet_rows) > 1 or len(submission_rows) > 1:
            _pv1_fail("multiple v1 packet/submission revisions")
        packet, packet_hash, submission, submission_hash = None, None, None, None
        if packet_rows:
            row = packet_rows[0]
            packet = _pv1_json(row["packet_json"], "saved packet", canonical=True)
            packet_hash = _pv1_packet(packet, initial)
            if row["revision"] != 1 or row["sha256"] != packet_hash or events.get("suggestions_ready", {}).get("payload") != {"packet_sha256": packet_hash}:
                _pv1_fail("packet row/event digest mismatch")
        elif "suggestions_ready" in events:
            _pv1_fail("missing saved packet")
        if submission_rows:
            row = submission_rows[0]
            submission = _pv1_json(row["payload_json"], "saved submission", canonical=True)
            if packet is None:
                _pv1_fail("submission has no packet")
            _pv1_submission(submission, packet, packet_hash)
            submission_hash = _pv1_digest(submission)
            if row["revision"] != 1 or row["submission_id"] != submission["submission_id"] or row["sha256"] != submission_hash or events.get("review_submitted", {}).get("payload") != {"submission": submission}:
                _pv1_fail("submission row/event identity mismatch")
        elif "review_submitted" in events:
            _pv1_fail("missing saved submission")
        final = events.get("case_finalized")
        if final:
            payload = final["payload"]
            if not isinstance(payload, dict) or set(payload) != set(_PV1_FINAL) or payload["evidence_sha256"] != packet_hash or payload["reviewer_decision"] != submission:
                _pv1_fail("final audit payload differs from packet/submission")
            if not payload["error"] and submission is None:
                _pv1_fail("successful finalization lacks a review")
            if payload["error"] and (packet is not None or submission is not None):
                _pv1_fail("unsupported v1 error finalization after review")
        snapshots = by_thread.get(thread, [])
        state_by_checkpoint = {}
        for item in snapshots:
            channels = item["value"]["channel_values"]
            if set(_PV1_STATE).issubset(channels):
                state = {key: channels[key] for key in _PV1_STATE}
                _pv1_canonical(state)  # rejects opaque extension/byte objects in application state
                for key in _PV1_HEADER:
                    if state[key] != initial[key]:
                        _pv1_fail("checkpoint/header mismatch: " + key)
                if state["evidence_sha256"] is not None:
                    checkpoint_packet = {key: state[key] for key in _PV1_PACKET}
                    actual = _pv1_packet(checkpoint_packet, initial)
                    if actual != state["evidence_sha256"] or (packet is not None and checkpoint_packet != packet):
                        _pv1_fail("checkpoint/saved packet mismatch")
                if state["reviewer_decision"] is not None and state["reviewer_decision"] != submission:
                    _pv1_fail("checkpoint/saved submission mismatch")
                if state["audit_status"] == "committed":
                    if not final or {key: state[key] for key in _PV1_FINAL} != final["payload"]:
                        _pv1_fail("committed checkpoint lacks matching final audit")
                    if state["audit_event_id"] != aid + ":" + str(final["row"]["sequence"]) or state["audit_head_sha256"] != final["row"]["event_sha256"]:
                        _pv1_fail("committed checkpoint receipt mismatch")
                state_by_checkpoint[item["row"]["checkpoint_id"]] = state
            elif channels.get("__start__") != initial:
                _pv1_fail("unsupported partial checkpoint application state")
        _pv1_history(snapshots, initial, state_by_checkpoint, submission, decoded_writes)
        if submission is not None:
            reviewed_id = submission["expected_checkpoint_id"]
            reviewed = state_by_checkpoint.get(reviewed_id)
            if reviewed is None or reviewed["evidence_sha256"] != packet_hash or reviewed["review_status"] != "pending":
                _pv1_fail("submission expected checkpoint is missing/foreign/not pending")
        latest = snapshots[-1] if snapshots else None
        latest_id = latest["row"]["checkpoint_id"] if latest else None
        state = state_by_checkpoint.get(latest_id)
        completed = bool(state and state["audit_status"] == "committed")
        if completed and latest["next"]:
            _pv1_fail("committed checkpoint still has scheduled graph work")
        if latest is None and (packet is not None or submission is not None or final is not None):
            _pv1_fail("durable review evidence exists but checkpoint history is missing")
        if final and (state is None or {key: state[key] for key in _PV1_FINAL} != final["payload"]):
            _pv1_fail("final audit disagrees with latest checkpoint evidence")
        if completed and any(channel in ("__interrupt__", "__error__", "__resume__", "__tasks__") for channel in writes.get((thread, "", latest_id), [])):
            _pv1_fail("completed checkpoint has unexpected pending control writes")
        if submission and latest:
            ancestors, cursor = set(), latest_id
            while cursor is not None:
                ancestors.add(cursor)
                cursor = checkpoints[(thread, "", cursor)]["row"]["parent_checkpoint_id"]
            if submission["expected_checkpoint_id"] not in ancestors:
                _pv1_fail("reviewed checkpoint is not an ancestor of latest state")
        status = ("completed_audit_checkpoint" if completed else "final_audit_pending_checkpoint" if final else
                  "submission_accepted_pending_completion" if submission else "packet_saved_pending_review" if packet else
                  "checkpoint_before_packet" if latest else "created_before_first_checkpoint")
        checkpoint_summaries = [{"checkpoint_id": item["row"]["checkpoint_id"],
                                 "parent_checkpoint_id": item["row"]["parent_checkpoint_id"],
                                 "type": item["row"]["type"],
                                 "blob_sha256": hashlib.sha256(item["row"]["checkpoint"]).hexdigest(),
                                 "metadata_sha256": _pv1_digest(item["metadata"])} for item in snapshots]
        result = {"audit_id": aid, "thread_id": thread, "schema_version": initial["schema_version"],
                  "workflow_version": initial["workflow_version"], "workflow_sha256": initial["workflow_sha256"],
                  "initial_sha256": _pv1_digest(initial), "packet_sha256": packet_hash,
                  "submission_id": submission["submission_id"] if submission else None,
                  "submission_sha256": submission_hash, "audit_count": len(ordered), "audit_head_sha256": previous,
                  "event_keys": ordered, "final_event_sha256": final["row"]["event_sha256"] if final else None,
                  "latest_checkpoint_id": latest_id, "latest_state_sha256": _pv1_digest(state) if state else None,
                  "status": status, "completed_audit_checkpoint": completed, "checkpoints": checkpoint_summaries,
                  "annotation_origin": "unknown"}
        results.append(result)
        states[aid] = {"initial": initial, "packet": packet, "submission": submission,
                       "latest_state": state, "states": state_by_checkpoint, "receipt": result,
                       "audit_events": [events[key]["row"] | {"payload": events[key]["payload"]}
                                        for key in ordered],
                       "checkpoint": None if latest is None else {
                           "checkpoint_id": latest_id,
                           "parent_checkpoint_id": latest["row"]["parent_checkpoint_id"],
                           "metadata": latest["metadata"],
                           "channel_versions": latest["value"]["channel_versions"],
                           "versions_seen": latest["value"]["versions_seen"],
                           "next": latest["next"],
                           "control_channels": sorted({channel for channel in writes.get((thread, "", latest_id), [])
                                                       if channel in _PV1_CONTROL_INDEX}),
                           "checkpoints_without_preceding_write_batch": [
                               item["row"]["checkpoint_id"] for item in snapshots
                               if item.get("preceding_output_batch_present") is False
                           ],
                       }}
    # The ledger's own FKs cover these relationships; retain explicit checks for altered schemas.
    for table in ("review_packets", "review_submissions", "audit_events"):
        if ledger.execute("SELECT COUNT(*) FROM " + table + " x LEFT JOIN cases c ON c.audit_id=x.audit_id WHERE c.audit_id IS NULL").fetchone()[0]:
            _pv1_fail("orphan ledger rows: " + table)
    return results, states, {"checkpoint_rows": len(checkpoints), "write_rows": len(write_receipts),
                            "writes_manifest_sha256": _pv1_digest(write_receipts),
                            "decoder": "bounded-inert-stdlib-msgpack-v1", "graph_executed": False}


def _pv1_saved_demo(project: Path, workspace_relative: Path, states: dict) -> tuple[dict, list[dict]]:
    """Check the known saved demo and attribute its explicit simulated annotation."""
    directory = project / workspace_relative / "verification"
    _pv1_no_symlink(directory, allow_missing=True)
    names = ("demo-start.json", "demo-status.json", "demo-recover-pending.json", "demo-review-form.json",
             "demo-review.json", "demo-recover.json", "demo-audit-verify.json")
    exists = [(directory / name).exists() for name in names]
    if not any(exists):
        return {"present": False, "verified": False}, []
    if not all(exists):
        _pv1_fail("saved demo artifact set is incomplete")
    docs, evidence = {}, []
    for name in names:
        path = _pv1_regular(directory / name, 16 * 1024 * 1024)
        docs[name] = _pv1_json(path.read_bytes(), name)
        if not isinstance(docs[name], dict):
            _pv1_fail("saved demo document must be a JSON object: " + name)
        if name in ("demo-start.json", "demo-status.json", "demo-recover-pending.json", "demo-review.json", "demo-recover.json"):
            if not isinstance(docs[name].get("state"), dict) or not set(_PV1_STATE).issubset(docs[name]["state"]):
                _pv1_fail("saved demo transcript lacks its v1 state object: " + name)
        evidence.append({"path": path.relative_to(project).as_posix(), "sha256": _pv1_file_hash(path)})
    start, done = docs["demo-start.json"], docs["demo-review.json"]
    aid = "e449b466-466d-4b81-9a29-cb3c9d957823"
    thread = "446f2137-621a-4426-8f95-9c82e07bcacf"
    final_id = "1f1ce0fc-cda5-66e0-8007-f6f0502a7876"
    pending_id = "1f1ce0fa-af59-63b4-8004-4f329c922484"
    head = "b62fc08e60b609a5c56e6cd4a4710f60e15b5a43c352ed76cc9220a7f1848a9e"
    actual = states.get(aid)
    if actual is None or done.get("thread_id") != thread or done.get("audit_id") != aid:
        _pv1_fail("known demo case identity mismatch")
    receipt = actual["receipt"]
    if receipt["audit_count"] != 4 or receipt["audit_head_sha256"] != head or receipt["latest_checkpoint_id"] != final_id or not receipt["completed_audit_checkpoint"]:
        _pv1_fail("known demo audit/checkpoint anchor mismatch")
    if done.get("state") != actual["latest_state"] or done.get("checkpoint_id") != final_id or done.get("completed") is not True or done.get("pending_interrupt") is not False or done.get("next") != []:
        _pv1_fail("completed demo transcript differs from restored checkpoint")
    if start.get("audit_id") != aid or start.get("thread_id") != thread or start.get("state") != actual["states"].get(pending_id) or start.get("checkpoint_id") != pending_id or start.get("pending_interrupt") is not True or start.get("completed") is not False or start.get("next") != ["human_review"]:
        _pv1_fail("pending demo transcript differs from reviewed checkpoint")
    pending_audit = {"audit_id": aid, "count": 2,
                     "head_sha256": "f42547719eecbddc2d95876bf373df3ec3aeb3e713d404a164b1d1ce9b4f7e45"}
    if start.get("audit") != pending_audit:
        _pv1_fail("saved pending demo audit anchor mismatch")
    if start != docs["demo-status.json"] or start != docs["demo-recover-pending.json"] or done != docs["demo-recover.json"]:
        _pv1_fail("saved demo restart transcripts disagree")
    expected_audit = {"audit_id": aid, "count": 4, "head_sha256": head}
    if done.get("audit") != expected_audit or docs["demo-audit-verify.json"] != {"audit": expected_audit, "completed": True}:
        _pv1_fail("saved demo audit transcript mismatch")
    submission = actual["submission"]
    if docs["demo-review-form.json"] != {key: value for key, value in submission.items() if key not in ("reviewer_id", "submitted_at")}:
        _pv1_fail("saved demo form differs from durable submission")
    if not submission["reason"].startswith("Simulated fictional demo annotation by the assistant:") or "This is not a real analyst identity decision." not in submission["reason"]:
        _pv1_fail("known demo lacks explicit simulation attribution")
    for name in ("demo-start.json", "demo-status.json", "demo-recover-pending.json", "demo-review.json", "demo-recover.json"):
        if {key: docs[name]["state"][key] for key in _PV1_PACKET} != actual["packet"]:
            _pv1_fail("demo transcript packet differs from durable packet")
    report = project / "docs/progress/phase-07a.md"
    _pv1_no_symlink(report, allow_missing=True)
    if report.exists():
        _pv1_regular(report, 2 * 1024 * 1024)
        if "Simulated fictional demo annotation by the assistant" not in report.read_text(encoding="utf-8"):
            _pv1_fail("historical report no longer corroborates demo origin")
        evidence.append({"path": "docs/progress/phase-07a.md", "sha256": _pv1_file_hash(report)})
    receipt["annotation_origin"] = "simulated_demo"
    attribution = {"audit_id": aid, "thread_id": thread, "submission_id": submission["submission_id"],
                   "origin": "simulated_demo", "basis": "explicit_saved_simulation_statement",
                   "packet_sha256": receipt["packet_sha256"], "audit_head_sha256": head,
                   "evidence": evidence, "original_record_modified": False,
                   "local_actor_label_is_not_human_authentication": True,
                   "independent_trusted_anchor": False}
    return {"present": True, "verified": True, "audit_id": aid,
            "pending_checkpoint_id": pending_id, "final_checkpoint_id": final_id,
            "evidence": evidence}, [attribution]


def _verify_archive(project: Path, workspace_relative: str, database_root: Path) -> tuple[dict, dict]:
    """Verify normalized COPIES and return a private receipt; perform no mutation.

    ``project`` must be the raw copied project. ``database_root`` must contain
    normalized databases at the same relative paths, without WAL/SHM journals.
    This helper intentionally never follows database paths from saved recipes.
    """
    project, database_root = _pv1_no_symlink(Path(project)), _pv1_no_symlink(Path(database_root))
    relative = Path(workspace_relative)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        _pv1_fail("review workspace must be a safe project-relative path")
    if (project.is_relative_to(database_root) or database_root.is_relative_to(project)
            or not project.is_dir() or not database_root.is_dir()):
        _pv1_fail("require distinct copied-project and normalized-database roots")
    ledger_relative = (relative / "cases.sqlite").as_posix()
    checkpoint_relative = (relative / "checkpoints.sqlite").as_posix()
    databases = {}
    connections = []
    paths = {}
    try:
        for path in sorted(database_root.rglob("*")):
            _pv1_no_symlink(path)
            if path.is_dir():
                continue
            _pv1_regular(path, 512 * 1024 * 1024)
            with path.open("rb") as source:
                header = source.read(16)
            if header != b"SQLite format 3\x00" and path.suffix.lower() not in (".sqlite", ".sqlite3", ".db"):
                continue
            name = path.relative_to(database_root).as_posix()
            original = project / name
            _pv1_no_symlink(original, allow_missing=True)
            if original.exists() and original.stat().st_ino == path.stat().st_ino and original.stat().st_dev == path.stat().st_dev:
                _pv1_fail("normalized database is a hardlink to the raw archived database")
            db, receipt = _pv1_database(path, name)
            connections.append(db)
            databases[name] = (db, receipt)
            paths[name] = path
        if ledger_relative not in databases or checkpoint_relative not in databases:
            _pv1_fail("normalized review database pair is missing")
        ledger, ledger_receipt = databases[ledger_relative]
        checkpoints, checkpoint_receipt = databases[checkpoint_relative]
        cases, states, checkpoint_summary = _pv1_review_pair(ledger, checkpoints, ledger_receipt, checkpoint_receipt)
        demo, attribution = _pv1_saved_demo(project, relative, states)
        result = {"verifier": "step00-v1-logical-verification-v1", "read_only": True,
                  "workspace_relative": relative.as_posix(), "databases": [databases[key][1] for key in sorted(databases)],
                  "case_count": len(cases), "cases": cases, "checkpoint_store": checkpoint_summary,
                  "saved_demo": demo, "external_origin_attributions": attribution,
                  "scope": "structural case/checkpoint coherence; no graph execution or general archive viewer",
                  "provenance": {"inputs": "normalized derivatives and copied saved transcripts",
                                 "original_databases_opened": False, "runtime_class_revival": False,
                                 "raw_queries_or_notes_in_receipt": False}}
        _pv1_canonical(result)
    except ArchiveError:
        raise
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        _pv1_fail(type(exc).__name__ + " while reading normalized copies: " + str(exc))
    finally:
        for db in connections:
            db.close()
    for name, (_, receipt) in databases.items():
        if _pv1_file_hash(paths[name]) != receipt["sha256"]:
            _pv1_fail("normalized database changed during verification: " + name)
        if _pv1_sidecars(paths[name]):
            _pv1_fail("verification created a SQLite sidecar")
    return result, states


def read_v1(project: Path, workspace_relative: str,
            database_root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Verify once and return the public receipt plus private case details.

    The second result contains saved queries and reviewer notes. Callers must
    expose it only through explicit case inspection, never a catalogue summary.
    No path from a saved recipe is opened and no archived Python is executed.
    """
    try:
        receipt, states = _verify_archive(project, workspace_relative, database_root)
    except ArchiveError:
        raise
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        _pv1_fail("invalid archive input: " + type(exc).__name__)
    details = {
        audit_id: {
            "archive_version": "v1", "workspace_relative": receipt["workspace_relative"],
            "case": value["receipt"], "initial": value["initial"],
            "review_packet": value["packet"], "review_submission": value["submission"],
            "packet": value["packet"], "submission": value["submission"],
            "latest_state": value["latest_state"],
            "audit_events": value["audit_events"], "checkpoint": value["checkpoint"],
        }
        for audit_id, value in states.items()
    }
    return receipt, details


def verify_v1(project: Path, workspace_relative: str,
              database_root: Path) -> dict[str, Any]:
    """Return a Step 00 compatible receipt without query or note text."""
    return read_v1(project, workspace_relative, database_root)[0]


def inspect_v1(project: Path, workspace_relative: str,
               database_root: Path, case_id: str) -> dict[str, Any]:
    """Explicitly inspect one verified case by its audit ID or thread ID."""
    _pv1_text(case_id, "case ID", 128)
    _, details = read_v1(project, workspace_relative, database_root)
    matches = [value for audit_id, value in details.items()
               if case_id in (audit_id, value["case"]["thread_id"])]
    if len(matches) != 1:
        _pv1_fail("case ID is unknown or ambiguous")
    return matches[0]

