"""Read-only, local-embedding replay with frozen questions and retained candidate/packet evidence.

The model here is a local GGUF embedding model only. It never extracts or generates an answer.
Private inputs, vectors, retrieved source and packets must stay outside the repository.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

import eval_rp as E
from nmos_sidecar import audit, llm, retrieval

EXTRACTOR = 'extract-fe5e340b99f9d2c5979e0192480cee7c'
SUMMARY = 'summarize-28fd99a5b31bf06478793f99b5ff4513'
PROJECTION = 'embed-8ff0a8d435c02d61ed4939dcd7b68ff8'
KNOWN_AT = datetime.fromisoformat('2026-10-01T09:21:00+00:00')
MODEL = 'qwen3-embedding:8b'
URL = 'http://127.0.0.1:11501/v1'


def encode(value: Any) -> str:
    def special(x: Any) -> Any:
        if isinstance(x, (set, frozenset)):
            return sorted(x, key=str)
        return str(x)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=special)


def digest(value: Any) -> str:
    return hashlib.sha256(encode(value).encode()).hexdigest()


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.partial')
    temp.write_text(encode(value), encoding='utf-8')
    temp.replace(path)


class CachedLocalEmbedder:
    def __init__(self, out: Path, allow_local: bool):
        self.out, self.allow_local = out, allow_local
        self.model = llm.Embedder(URL, MODEL, '')

    def embed(self, texts: list[str], timeout_s: float) -> list[list[float]]:
        vectors = []
        for text in texts:
            identity = {'text': text, 'model': MODEL, 'endpoint': URL}
            path = self.out / 'query-vectors' / (digest(identity) + '.json')
            if path.exists():
                saved = json.loads(path.read_text())
                if saved['identity'] != identity:
                    raise ValueError('query vector identity changed')
                vector = saved['vector']
            else:
                if not self.allow_local:
                    raise ValueError('missing frozen local query vector')
                (vector,) = self.model.embed([text], timeout_s=300)
                self.validate(vector)
                write(path, {'identity': identity, 'vector': vector})
            self.validate(vector)
            vectors.append(vector)
        return vectors

    @staticmethod
    def validate(vector: list[float]) -> None:
        if len(vector) != 4096 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vector):
            raise ValueError('invalid frozen query vector')
        if not any(vector):
            raise ValueError('empty query vector norm')


def run(args: argparse.Namespace) -> None:
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', args.label):
        raise ValueError('invalid run label')
    if any((p / '.git').exists() for p in (args.out.resolve(), *args.out.resolve().parents)):
        raise ValueError('private artifacts must be outside a repository')
    if (args.out / args.label).exists():
        raise ValueError('preserve prior measurement; choose a new label')
    if getattr(args, 'answer_spans', False) and not args.candidate:
        raise ValueError('--answer-spans requires --candidate')
    cases_bytes = args.cases.read_bytes()
    cases = json.loads(cases_bytes)
    fixed = {'cases_sha256': hashlib.sha256(cases_bytes).hexdigest(), 'extractor': EXTRACTOR,
             'summary': SUMMARY, 'projection': PROJECTION, 'known_at': KNOWN_AT.isoformat(),
             'budget': 4000, 'policy': 'packet-v10', 'keywords': True,
             'embed_model': MODEL, 'query_prefix': retrieval.QWEN3_QUERY_INSTRUCTION,
             'scorer_sha256': hashlib.sha256(Path(E.__file__).read_bytes()).hexdigest()}
    frozen = args.out / 'protocol.json'
    if frozen.exists() and json.loads(frozen.read_text()) != fixed:
        raise ValueError('fixed evaluation changed')
    write(frozen, fixed)
    run_dir = args.out / args.label
    write(run_dir / 'source.json', {str(p.relative_to(Path.cwd())): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted((Path.cwd() / 'apps/sidecar/src/nmos_sidecar').glob('*.py'))})
    for name in ('eval_recall_candidate.py', 'recall_candidate.py', 'recall_passages.py', 'recall_answer_spans.py'):
        source = Path(__file__).parent / name
        (run_dir / name).write_bytes(source.read_bytes())
    embedder = CachedLocalEmbedder(args.out, args.allow_local_embeddings)
    opts = retrieval.RecallOptions(embedder=embedder, embed_projection=PROJECTION,
                                   query_prefix=retrieval.QWEN3_QUERY_INSTRUCTION)
    reference = getattr(args, 'frozen_candidates', None)
    frozen_cases = {}
    if reference:
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', reference):
            raise ValueError('invalid candidate reference')
        if (json.loads((args.out / reference / 'source.json').read_text())
                != json.loads((run_dir / 'source.json').read_text())):
            raise ValueError('candidate reference production source changed')
        for case in cases:
            saved = json.loads((args.out / reference / 'cases' / (case['name'] + '.json')).read_text())
            if saved['case'] != case:
                raise ValueError('frozen candidate question or gold changed')
            frozen_cases[case['name']] = saved
    write(run_dir / 'mode.json', {'candidate': args.candidate,
                                 'answer_spans': getattr(args, 'answer_spans', False),
                                 'frozen_candidates_from': reference,
                                 'frozen_case_sha256': {name: digest(saved) for name, saved in frozen_cases.items()}})
    frozen_current = None
    original_gather = audit.gather
    original_fuse, original_excerpt = retrieval.fuse, retrieval.grown_excerpt
    gather_for_run = original_gather
    captured = {}
    def gather(*a: Any, **kw: Any) -> retrieval.Gathered:
        g = gather_for_run(*a, **kw)
        if frozen_current is not None:
            captured['live_routes_before_freeze'] = {name: getattr(g, name) for name in
                                                     ('lexical_note', 'keyword_note', 'vector_note')}
            for name in ('lexical_note', 'keyword_note', 'vector_note'):
                setattr(g, name, frozen_current['gathered'][name])
        captured['gathered'] = dataclasses.asdict(g)
        return g
    try:
        if reference:
            def frozen_fuse(*a: Any, **kw: Any) -> list[dict[str, Any]]:
                if frozen_current is None:
                    raise ValueError('no frozen candidates for the active question')
                return [dict(row) for row in frozen_current['gathered']['candidates']]
            retrieval.fuse = frozen_fuse
        if args.candidate:
            from recall_candidate import install
            gather_for_run = install(original_gather, args.out, answer_spans=getattr(args, "answer_spans", False))
        audit.gather = gather
        with psycopg.connect(args.db, row_factory=dict_row, autocommit=True,
                             options='-c default_transaction_read_only=on') as conn:
            assert conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only'] == 'on'
            for index, case in enumerate(cases):
                frozen_current = frozen_cases.get(case['name'])
                out = audit.replay(conn, UUID(case['trace']), opts, 'packet-v10', known_at=KNOWN_AT,
                                   query=case.get('query'), budget=4000, projection=PROJECTION,
                                   extractor_key=EXTRACTOR, summarize_key=SUMMARY,
                                   embed_timeout_ms=5000, lexical_keywords=True)
                if not out or out['status'] != 'ok' or out['vectors'] != 'on':
                    raise ValueError('case missing or vector search unavailable')
                window = E.prompt_window(conn, UUID(case['trace']), case.get('query') is not None)
                if frozen_current is not None and window != frozen_current['window']:
                    raise ValueError('frozen candidate prompt window changed')
                result = {'name': case['name'], 'category': case['category'], **E.score(case, out['text'], window)}
                write(run_dir / 'cases' / (case['name'] + '.json'),
                      {'case': case, 'result': result, 'packet': out, 'window': window, **captured})
                print(encode({'done': index + 1, 'total': len(cases), 'name': case['name'],
                              'passed': result['passed'], 'tokens': out['tokens']}), flush=True)
    finally:
        audit.gather = original_gather
        retrieval.fuse, retrieval.grown_excerpt = original_fuse, original_excerpt
    saved = [json.loads(p.read_text())['result'] for p in (run_dir / 'cases').glob('*.json')]
    summary = {'completed': len(saved), 'total': len(cases), 'passed': sum(r['passed'] for r in saved),
               'memory_cases': sum(r['needs_memory'] for r in saved),
               'memory_passed': sum(r['passed'] and r['needs_memory'] for r in saved),
               'forbidden': sum(r['placed'] for r in saved),
               'failed': sorted(r['name'] for r in saved if not r['passed'])}
    write(run_dir / 'summary.json', summary)
    print(encode(summary), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--db', required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--candidate', action='store_true')
    parser.add_argument('--answer-spans', action='store_true', help='try contiguous answer spans; requires --candidate')
    parser.add_argument('--frozen-candidates', help='use a retained run’s fused candidates and route states')
    parser.add_argument('--allow-local-embeddings', action='store_true')
    run(parser.parse_args())


if __name__ == '__main__':
    main()
