"""Evaluation-only passage selector over immutable local embeddings, with exact source offsets."""
from __future__ import annotations

import array
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def cosine(a: list[float] | array.array, b: list[float] | array.array) -> float:
    if len(a) != len(b) or not a:
        raise ValueError('embedding dimensions differ')
    aa = sum(x*x for x in a); bb = sum(x*x for x in b)
    if not aa or not bb:
        raise ValueError('empty embedding norm')
    return sum(x*y for x,y in zip(a,b,strict=True)) / math.sqrt(aa*bb)


class PassageIndex:
    def __init__(self, root: Path):
        self.root = root
        self.by_revision: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.vectors: dict[str, array.array] = {}
        self.queries: dict[str, list[float]] = {}
        self.cache: dict[tuple[str,str,str], dict[str,Any]] = {}
        manifest = json.loads((root / 'passages/manifest.json').read_text())
        if manifest['version'] != 'passage-eval-v1' or manifest['model'] != 'qwen3-embedding:8b':
            raise ValueError('unknown passage generation')
        self.generation = hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
        for row in manifest['entries']:
            self.by_revision[row['revision']].append(row)
        for p in (root/'query-vectors').glob('*.json'):
            q = json.loads(p.read_text())
            if q['identity']['model'] != manifest['model']:
                raise ValueError('query model differs')
            self.queries[q['identity']['text']] = q['vector']

    def best(self, revision: str, source: str, query: str) -> dict[str,Any] | None:
        rows = self.by_revision.get(revision)
        if not rows:
            return None
        source_hash = hashlib.sha256(source.encode()).hexdigest()
        key = (revision,source_hash,query)
        if key in self.cache:
            return self.cache[key]
        q = self.queries.get(query)
        if q is None:
            raise ValueError('query vector was not frozen')
        scored = []
        for row in rows:
            if row['source_sha256'] != source_hash or source[row['start']:row['end']] != row['text']:
                raise ValueError('passage does not match immutable source')
            k = row['key']
            if k not in self.vectors:
                v = array.array('f')
                with (self.root/'passages'/(k+'.f32')).open('rb') as f:
                    v.fromfile(f,4096)
                if not all(math.isfinite(x) for x in v):
                    raise ValueError('non-finite passage vector')
                self.vectors[k] = v
            scored.append((cosine(q,self.vectors[k]),-row['start'],row))
        score,_,row = max(scored,key=lambda x:(x[0],x[1]))
        answer = {**row,'similarity':score,'generation':self.generation}
        self.cache[key] = answer
        return answer
