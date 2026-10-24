"""Lazy adapter around the unchanged E5 model, cache and exact ranker."""

from dataclasses import asdict
from importlib.metadata import version
import json
from pathlib import Path
from typing import Protocol

from watchlist.entities import load_entities
from watchlist.database import load_database
from watchlist.agent.state import digest


class Retriever(Protocol):
    def search(self, query: str, recipe: dict) -> dict:
        """Return JSON candidates, all available alias evidence and a manifest."""
        ...


def make_recipe(config_path: Path, db: Path | None = None) -> dict:
    """Freeze dataset contents and model/config receipt before creating a case."""
    config = json.loads(config_path.read_text())
    entities = load_database(db)[0] if db else load_entities()
    model = config['model']
    receipt = json.loads((Path(model['model_path']) / 'acquisition.json').read_text())
    return {'config': config, 'db': str(db.resolve()) if db else None,
            'reference_sha256': digest([asdict(e) for e in entities]),
            'model_receipt_sha256': digest(receipt),
            'packages': {n: version(n) for n in ('numpy', 'torch', 'transformers', 'sentence-transformers', 'tokenizers')}}


class E5Retriever:
    """No encoder is created until search; status and resume require no weights."""

    def search(self, query: str, recipe: dict) -> dict:
        from watchlist.embeddings import E5Encoder, cached_aliases
        from watchlist.matching_embeddings import rank_vectors
        config = recipe['config']
        entities = load_database(Path(recipe['db']))[0] if recipe['db'] else load_entities()
        if digest([asdict(e) for e in entities]) != recipe['reference_sha256']: raise ValueError('reference changed since case creation')
        encoder = E5Encoder(config['model'])
        if digest(encoder.receipt) != recipe['model_receipt_sha256'] or encoder.metadata['packages'] != recipe['packages']: raise ValueError('model or runtime changed since case creation')
        vectors, cache = cached_aliases(entities, encoder, Path(config['cache_path']))
        ranked = rank_vectors(encoder.encode([query]), vectors, entities, top_k=5) if entities else []
        by_id = {e.entity_id: e for e in entities}
        candidates, evidence = [], []
        for rank, c in enumerate(ranked, 1):
            e = by_id[c.entity_id]
            refs = []
            for alias in e.aliases:
                eid = digest([e.entity_id, alias.alias_id])
                refs.append(eid)
                evidence.append({'evidence_id': eid, 'entity_id': e.entity_id, 'alias_id': alias.alias_id,
                                 'original_text': alias.name, 'source': e.source, 'synthetic': e.synthetic,
                                 'provenance': asdict(e.provenance) if e.provenance else None,
                                 'attribution': ('Authored fictional fixture; not real persons.' if e.synthetic else
                                                 f'{e.provenance.provider}; publisher: {e.provenance.publisher}; terms: {e.provenance.license_url}')})
            candidates.append({'entity_id': c.entity_id, 'display_name': c.display_name, 'entity_type': c.entity_type,
                               'rank': rank, 'matched_alias_id': c.matched_alias_id, 'matched_alias': c.matched_alias,
                               'evidence_ids': refs, 'similarity_score': c.similarity_score, 'score_kind': 'cosine_similarity'})
        return {'candidates': candidates, 'evidence': evidence,
                'retrieval': {'encoder': encoder.metadata, 'reference_sha256': recipe['reference_sha256'],
                              'reference_view': 'full', 'cache_key': cache['key'], 'top_k': 5, 'reranker': 'disabled'}}
