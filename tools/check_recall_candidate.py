"""Verify retained replay artifacts; fail on score drift, any regression or added forbidden match."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
import eval_rp as E


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def checked(root: Path, label: str, cases: list[dict[str,Any]], budget: int) -> dict[str,Any]:
    result = {}
    paths = list((root/label/'cases').glob('*.json'))
    if len(paths) != len(cases):
        raise ValueError('incomplete run')
    for case in cases:
        saved = read(root/label/'cases'/(case['name']+'.json'))
        if saved['case'] != case:
            raise ValueError('question or gold changed')
        packet = saved['packet']
        if packet['vectors'] != 'on' or packet['policy'] != 'packet-v10' or packet['tokens'] > budget:
            raise ValueError('fixed packet conditions violated')
        score = E.score(case,packet['text'],saved['window'])
        if any(saved['result'][k] != v for k,v in score.items()):
            raise ValueError('saved score differs from retained packet')
        result[case['name']] = score
    return result


def verify(root: Path, label: str, cases_path: Path, reference: str = "baseline") -> dict[str,Any]:
    protocol = read(root/'protocol.json')
    if hashlib.sha256(cases_path.read_bytes()).hexdigest() != protocol['cases_sha256']:
        raise ValueError('gold file hash changed')
    if hashlib.sha256(Path(E.__file__).read_bytes()).hexdigest() != protocol['scorer_sha256']:
        raise ValueError('original scorer changed')
    cases = read(cases_path)
    if read(root/reference/'source.json') != read(root/label/'source.json'):
        raise ValueError('production source changed between runs')
    for case in cases:
        b = read(root/reference/'cases'/(case['name']+'.json'))
        n = read(root/label/'cases'/(case['name']+'.json'))
        if b['window'] != n['window']:
            raise ValueError('prompt window changed')
        if b['packet']['keywords'] != n['packet']['keywords']:
            raise ValueError('keyword route changed')
    base = checked(root,reference,cases,protocol['budget'])
    new = checked(root,label,cases,protocol['budget'])
    lost = [n for n,b in base.items() if b['passed'] and not new[n]['passed']]
    gained = [n for n,b in base.items() if not b['passed'] and new[n]['passed']]
    changed_denominator = [n for n,b in base.items() if b['needs_memory'] != new[n]['needs_memory']]
    forbidden = [n for n,b in base.items() if new[n]['placed'] > b['placed']]
    bp = sum(r['passed'] and r['needs_memory'] for r in base.values())
    np = sum(r['passed'] and r['needs_memory'] for r in new.values())
    return {'baseline_memory':bp,'candidate_memory':np,'denominator':sum(r['needs_memory'] for r in base.values()),
            'gained':gained,'lost':lost,'changed_denominator':changed_denominator,'new_forbidden':forbidden,
            'pass':np>bp and not (lost or changed_denominator or forbidden)}


def main() -> None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('root',type=Path);ap.add_argument('label');ap.add_argument('--cases',type=Path,required=True)
    ap.add_argument('--reference', default='baseline', help='also compare against a previously selected candidate')
    args=ap.parse_args();result=verify(args.root,args.label,args.cases,args.reference)
    print(json.dumps(result,ensure_ascii=False))
    if not result['pass']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
