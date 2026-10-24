"""Local CLI: validate inputs before storage, inspect without mutating live files."""

import argparse
import json
from pathlib import Path
import re
import sqlite3
import stat
from uuid import UUID

from watchlist.agent.retrieval import E5Retriever, make_recipe as _make_recipe
from watchlist.agent.state import (SCHEMA, WORKFLOW, canonical, digest, validate_query_envelope,
                                   validate_recipe, validate_review_form)
from watchlist.agent.storage import ReviewReader, ReviewService, _checked_path


class _Parser(argparse.ArgumentParser):
    """Route command syntax failures through the same JSON domain-error result."""

    def error(self, message: str) -> None:
        raise ValueError(message)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    """Reject ambiguous JSON instead of silently retaining the last field."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON field: {key}')
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ValueError(f'nonfinite JSON value: {value}')


def _path(value: object, label: str) -> Path:
    """Validate path text without expanding variables or creating anything."""
    if not isinstance(value, str) or not value.strip() or '\x00' in value or len(value) > 4096:
        raise ValueError(f'{label} must be nonblank path text of at most 4096 characters')
    return Path(value)


def _file(path: Path, label: str) -> None:
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f'{label} must be an existing regular file')


def _json_object(path: Path, label: str, limit: int = 65536) -> dict:
    """Read bounded finite JSON before a service or retriever is constructed."""
    _file(path, label)
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f'{label} exceeds {limit} bytes')
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_nonfinite)
    except RecursionError as exc:
        raise ValueError(f'{label} exceeds the JSON nesting limit') from exc
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be a JSON object')
    validate_recipe(value)
    return value


def load_config(path: Path) -> dict:
    """Accept the exact approved agent policy and well-typed path values."""
    config = _json_object(path, 'agent configuration')
    expected = {'schema_version': SCHEMA, 'workflow_version': WORKFLOW, 'top_k': 5,
                'reranker': 'disabled', 'review_policy': 'human_only'}
    if (set(config) != set(expected) | {'workspace', 'embedding_config'}
            or any(type(config[k]) is not type(v) or config[k] != v for k, v in expected.items())):
        raise ValueError('agent configuration differs from approved policy')
    workspace = _checked_path(_path(config['workspace'], 'workspace'), allow_missing=True)
    _path(config['embedding_config'], 'embedding_config')
    if workspace.exists() and not workspace.is_dir():
        raise ValueError('workspace must be a directory')
    return config


def make_recipe(config_path: Path, db: Path | None = None) -> dict:
    """Validate start-only configuration and receipt shapes before preparation.

    Status/review/recovery never read this configuration or load model weights.
    The existing recipe builder keeps its data fingerprint definition unchanged.
    """
    config = _json_object(config_path, 'embedding configuration')
    if set(config) != {'model', 'cache_path', 'timing_repetitions', 'datasets'}:
        raise ValueError('embedding configuration fields mismatch')
    model = config['model']
    model_fields = {'model_id', 'revision', 'model_path', 'device', 'dtype', 'dimension',
                    'prefix', 'max_tokens', 'normalization', 'pooling', 'batch_size'}
    if not isinstance(model, dict) or set(model) != model_fields:
        raise ValueError('model configuration fields mismatch')
    for field in ('dimension', 'max_tokens', 'batch_size'):
        if type(model[field]) is not int:
            raise ValueError(f'model {field} must be an integer')
    for field in model_fields - {'dimension', 'max_tokens', 'batch_size'}:
        if not isinstance(model[field], str):
            raise ValueError(f'model {field} must be text')
    # This module validates the existing pinned protocol; it does not load weights.
    from watchlist.embeddings import MODEL_FILES, validate_config
    validate_config(model)
    model_root = _path(model['model_path'], 'model_path')
    cache_root = _path(config['cache_path'], 'cache_path')
    if not model_root.is_dir():
        raise ValueError('model_path must be an existing directory')
    if cache_root.exists() and not cache_root.is_dir():
        raise ValueError('cache_path must be a directory')
    if type(config['timing_repetitions']) is not int or config['timing_repetitions'] <= 0:
        raise ValueError('timing_repetitions must be a positive integer')
    if (not isinstance(config['datasets'], list) or not config['datasets']
            or any(not isinstance(name, str) or not name.strip() for name in config['datasets'])):
        raise ValueError('datasets must be a nonempty list of names')
    receipt = _json_object(model_root / 'acquisition.json', 'model receipt', 8_000_000)
    if (receipt.get('model_id') != model['model_id'] or receipt.get('revision') != model['revision']
            or not isinstance(receipt.get('files'), dict) or set(receipt['files']) != set(MODEL_FILES)):
        raise ValueError('model receipt differs from approved model')
    for name, info in receipt['files'].items():
        if (not isinstance(info, dict) or set(info) != {'bytes', 'sha256'}
                or type(info['bytes']) is not int or info['bytes'] < 0
                or not isinstance(info['sha256'], str) or re.fullmatch('[0-9a-f]{64}', info['sha256']) is None):
            raise ValueError('model receipt file fields mismatch')
        _file(model_root / name, 'model artifact')
    if db is not None:
        _file(db, 'reference database')
    result = _make_recipe(config_path, db)
    validate_recipe(result)
    if canonical(result.get('config')) != canonical(config):
        raise ValueError('embedding configuration changed during recipe preparation')
    if result.get('model_receipt_sha256') != digest(receipt):
        raise ValueError('model receipt changed during recipe preparation')
    return result


def _arguments(args: argparse.Namespace) -> None:
    """Check action-specific options before opening a workspace or model path."""
    if args.action == 'start':
        if args.name is None:
            raise ValueError('start requires --name')
        if args.thread_id is not None or args.review_file is not None:
            raise ValueError('start cannot accept --thread-id or --review-file')
        validate_query_envelope(args.name)
        if args.db is not None:
            _file(args.db, 'reference database')
    else:
        if args.name is not None or args.db is not None:
            raise ValueError('resume/status cannot replace query or dataset')
        if args.action != 'review' and args.review_file is not None:
            raise ValueError('--review-file is only valid for review')
        if args.action != 'status' and args.thread_id is None:
            raise ValueError('--thread-id is required')
        if args.action == 'review' and args.review_file is None:
            raise ValueError('review requires --review-file')
    if args.thread_id is not None:
        if not args.thread_id or len(args.thread_id) > 128:
            raise ValueError('--thread-id must be a UUID')
        try:
            UUID(args.thread_id)
        except ValueError as exc:
            raise ValueError('--thread-id must be a UUID') from exc


def _review_template(result: dict) -> None:
    if result.get('pending_interrupt'):
        result['review_form'] = {
            'submission_id': 'REPLACE_WITH_NEW_UUID', 'review_revision': result['state']['review_revision'],
            'evidence_sha256': result['state']['evidence_sha256'], 'expected_checkpoint_id': result['checkpoint_id'],
            'outcome': 'CHOOSE_EXPLICITLY', 'candidate_entity_id': None, 'reason': 'WRITE_YOUR_REASON'}


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument('action', choices=['start', 'status', 'review', 'recover', 'audit-verify'])
    parser.add_argument('--config', type=Path, default=Path('config/agent.json'))
    parser.add_argument('--name')
    parser.add_argument('--db', type=Path)
    parser.add_argument('--thread-id')
    parser.add_argument('--review-file', type=Path, help='JSON form copied from status; fill outcome, candidate and reason')
    try:
        args = parser.parse_args(argv)
        _arguments(args)
        config = load_config(args.config)
        form = (validate_review_form(_json_object(args.review_file, 'review form', 8000))
                if args.action == 'review' else None)
        root = Path(config['workspace'])
        if args.action in ('status', 'audit-verify'):
            with ReviewReader(root) as reader:
                result = reader.status(args.thread_id) if args.thread_id is not None else {'cases': reader.list_cases()}
            if args.action == 'audit-verify':
                result = {'audit': result['audit'], 'completed': result['completed']}
        elif args.action == 'start':
            recipe = make_recipe(Path(config['embedding_config']), args.db)
            validate_recipe(recipe)
            # start explicitly allows initializing a new/empty workspace.
            with ReviewService(root, E5Retriever(), mode='auto') as service:
                result = service.start(args.name, recipe)
        else:
            # Validate stored-state-dependent input before writable access, then
            # revalidate under the writer lock inside the service to handle races.
            with ReviewReader(root) as reader:
                if args.action == 'review':
                    reader.validate_review(args.thread_id, form)
                else:
                    reader.status(args.thread_id)
            with ReviewService(root, E5Retriever(), mode='existing') as service:
                result = service.review(args.thread_id, form) if args.action == 'review' else service.recover(args.thread_id)
        _review_template(result)
        print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({'error': str(exc), 'recovery_notes': getattr(exc, '__notes__', []),
                          'completed': False}, ensure_ascii=True))
        return 2
