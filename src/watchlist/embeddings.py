"""Explicit bounded acquisition, local E5 inference and fingerprinted alias caches."""

import argparse
from dataclasses import asdict
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import time
from urllib.request import urlopen
import numpy as np

from watchlist.evaluation_data import fingerprint
from watchlist.matching_embeddings import unit_vectors
from watchlist.normalize import normalize_name

MODEL_ID = 'intfloat/multilingual-e5-small'
REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
MODEL_FILES = ('1_Pooling/config.json', 'README.md', 'config.json', 'model.safetensors',
               'modules.json', 'sentence_bert_config.json', 'sentencepiece.bpe.model',
               'special_tokens_map.json', 'tokenizer.json', 'tokenizer_config.json')


def file_hash(path: Path) -> str:
    """Stream hashes without loading a half-gigabyte weight file into memory."""
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def validate_config(config: dict) -> None:
    """Only the approved model and frozen CPU/float32 protocol are accepted."""
    expected = {'model_id': MODEL_ID, 'revision': REVISION, 'device': 'cpu', 'dtype': 'float32',
                'dimension': 384, 'prefix': 'query: ', 'max_tokens': 512,
                'normalization': 'phase1-nfkc-casefold-whitespace-v1', 'pooling': 'mean'}
    if any(config.get(k) != v for k, v in expected.items()):
        raise ValueError('model configuration differs from approved protocol')
    if type(config.get('batch_size')) is not int or not 1 <= config['batch_size'] <= 8:
        raise ValueError('batch_size must be between 1 and 8')


def verify_model(config: dict) -> dict:
    """Verify all local files against the saved acquisition receipt, offline."""
    validate_config(config)
    root = Path(config['model_path'])
    receipt = json.loads((root / 'acquisition.json').read_text())
    if receipt['revision'] != REVISION or receipt['model_id'] != MODEL_ID or set(receipt['files']) != set(MODEL_FILES):
        raise ValueError('model receipt mismatch')
    for name, info in receipt['files'].items():
        if file_hash(root / name) != info['sha256']:
            raise ValueError(f'model checksum mismatch: {name}')
    return receipt


def fetch_model(config: dict) -> dict:
    """Only explicit CLI fetch uses the network; cap total selected files at 600 MB."""
    validate_config(config)
    root = Path(config['model_path'])
    if (root / 'acquisition.json').exists():
        return verify_model(config)
    if root.exists() and any(root.iterdir()):
        raise ValueError('incomplete model directory; inspect it before retrying')
    api = f'https://huggingface.co/api/models/{MODEL_ID}/revision/{REVISION}?blobs=true'
    with urlopen(api, timeout=60) as response:
        payload = response.read(8_000_001)
    if len(payload) > 8_000_000:
        raise ValueError('model metadata exceeds cap')
    metadata = json.loads(payload)
    if metadata['sha'] != REVISION:
        raise ValueError('remote revision mismatch')
    info = {item['rfilename']: item for item in metadata['siblings']}
    total = sum(info[name]['size'] for name in MODEL_FILES)
    if total + len(payload) > 600_000_000:
        raise ValueError('approved 600 MB model limit exceeded')
    receipt = {'model_id': MODEL_ID, 'revision': REVISION, 'license': 'MIT',
               'source': f'https://huggingface.co/{MODEL_ID}', 'bytes': total,
               'metadata_bytes': len(payload), 'files': {}}
    received = len(payload)
    for name in MODEL_FILES:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + '.partial')
        size = 0
        with urlopen(f'https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{name}', timeout=60) as response, temporary.open('wb') as stream:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                received += len(chunk)
                if size > info[name]['size'] or received > 600_000_000:
                    raise ValueError('download exceeded advertised or approved size')
                stream.write(chunk)
        if size != info[name]['size']:
            raise ValueError('incomplete download')
        digest = file_hash(temporary)
        expected = info[name].get('lfs', {}).get('sha256')
        if expected and digest != expected:
            raise ValueError('remote weight/tokenizer checksum mismatch')
        temporary.replace(target)
        receipt['files'][name] = {'bytes': size, 'sha256': digest}
        print(f'Acquired {name}: {size} bytes', flush=True)
    (root / 'acquisition.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


class E5Encoder:
    """Load verified local weights once; no training and no automatic downloads."""

    def __init__(self, config: dict):
        validate_config(config)
        self.receipt = verify_model(config)
        import torch
        from sentence_transformers import SentenceTransformer
        torch.manual_seed(42)
        torch.set_num_threads(4)
        torch.use_deterministic_algorithms(True)
        start = time.perf_counter()
        self.model = SentenceTransformer(str(Path(config['model_path']).resolve()), device='cpu',
                                         local_files_only=True, trust_remote_code=False,
                                         model_kwargs={'dtype': torch.float32, 'use_safetensors': True})
        self.model.eval()
        self.model.max_seq_length = config['max_tokens']
        self.config = config
        if self.model.get_embedding_dimension() != config['dimension']:
            raise ValueError('unexpected model vector dimension')
        self.load_seconds = time.perf_counter() - start
        self.metadata = {'config': config, 'files': self.receipt['files'], 'threads': 4,
                         'packages': {name: version(name) for name in
                                      ('numpy', 'torch', 'transformers', 'sentence-transformers', 'tokenizers')}}

    def encode(self, texts: list[str]) -> np.ndarray:
        """Normalize/prefix, reject truncation, mean-pool through the model pipeline."""
        inputs = [self.config['prefix'] + normalize_name(t) for t in texts]
        if not inputs:
            return np.empty((0, self.config['dimension']), dtype=np.float32)
        tokenized = self.model.tokenizer(inputs, truncation=False, padding=False)
        if any(len(ids) > self.config['max_tokens'] for ids in tokenized['input_ids']):
            raise ValueError('name would be truncated by tokenizer')
        result = self.model.encode(inputs, batch_size=self.config['batch_size'],
                                   normalize_embeddings=True, convert_to_numpy=True,
                                   show_progress_bar=False, precision='float32')
        result = unit_vectors(result)
        if result.shape != (len(texts), self.config['dimension']):
            raise ValueError('encoder output shape mismatch')
        return result


def cached_aliases(entities: tuple, encoder: object, root: Path) -> tuple[np.ndarray, dict]:
    """Cache exact ordered alias rows and provenance; verify bytes on every hit."""
    manifest = json.loads(json.dumps({'version': 'alias-cache-v1', 'encoder': encoder.metadata,
                                     'entities': [asdict(e) for e in entities]}))
    key = fingerprint(manifest)
    root.mkdir(parents=True, exist_ok=True)
    vectors_path, metadata_path = root / f'{key}.npy', root / f'{key}.json'
    start = time.perf_counter()
    if metadata_path.exists():
        saved = json.loads(metadata_path.read_text())
        if saved['manifest'] != manifest or file_hash(vectors_path) != saved['vectors_sha256']:
            raise ValueError('embedding cache metadata or checksum mismatch')
        vectors = np.load(vectors_path, allow_pickle=False)
        hit = True
    else:
        vectors = encoder.encode([a.name for e in entities for a in e.aliases])
        np.save(vectors_path, vectors, allow_pickle=False)
        metadata_path.write_text(json.dumps({'manifest': manifest, 'vectors_sha256': file_hash(vectors_path)},
                                            ensure_ascii=False, indent=2) + '\n')
        hit = False
    if vectors.shape != (sum(len(e.aliases) for e in entities), encoder.config['dimension']):
        raise ValueError('cache alias count or vector dimension mismatch')
    vectors = unit_vectors(vectors)
    return vectors, {'key': key, 'hit': hit, 'seconds': time.perf_counter()-start, 'shape': list(vectors.shape)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['fetch', 'verify'])
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text())['model']
        receipt = fetch_model(config) if args.action == 'fetch' else verify_model(config)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps({'model_id': receipt['model_id'], 'revision': receipt['revision'], 'bytes': receipt['bytes']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
