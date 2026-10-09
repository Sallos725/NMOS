"""PHASE-42: source-clock provenance and spare-budget enrichment, not event-date inference."""
import dataclasses
import json
from uuid import uuid4
import xml.etree.ElementTree as ET

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import audit
from nmos_sidecar.retrieval import RecallOptions
from simchat import SimChat
from test_sidecar_integration import sync, recall


@pytest.fixture
def clock_story(tmp_path):
    path = tmp_path / 'clock.json'
    rule = {'id': 'clock', 'card': 'Clock test', 'kind': 'block', 'role': 'char',
            'start': r'☆ \[', 'end': r'\]\s*$', 'separator': '|'}
    path.write_text(json.dumps({'rules': [rule]}))
    chat = SimChat()
    for day in range(1, 9):
        chat.user('이야기를 계속한다.')
        prose = ('서윤은 도윤에게 은빛종을 건넸다.' if day == 1 else f'모두 평온하게 지냈다. 장면 {day}.')
        # The clock is intentionally outside the selected excerpt, as in the measured long source.
        prose += '\n' + '창밖의 거리에는 익숙한 풍경이 한없이 펼쳐져 있었다. ' * 50
        chat.reply(f'{prose}\n☆ [Date: 0712-03-{day:02d} | Time: {day + 6:02d}:05]')
    chat.user('지난 일을 떠올린다.')
    return path, chat, rule


def test_old_scene_recalls_its_exact_source_clock_without_changing_selection(migrated, clock_story):
    path, chat, _ = clock_story
    with make_client(migrated, parsers_file=str(path), packet_policy='packet-v18') as c:
        sync(c, chat, character_name='Clock test')
        out = recall(c, chat, '서윤이 도윤에게 은빛종을 건넨 것은 언제였지?', budget=4000)
        root = ET.fromstring(out['packet']['text'])
        clocks = root.findall('SourceTime')
        assert clocks, 'the selected old source must carry its own status-window clock'
        assert clocks[0].attrib['turn'] == '0'
        assert {e.attrib['key']: e.text for e in clocks[0]} == {'Date': '0712-03-01', 'Time': '07:05'}
        assert "not necessarily the event's occurrence time" in root.findtext('SourceTimeNote')
        assert '0712-03-01' not in root.findtext('Excerpt')
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            before = audit.replay(conn, out['trace_id'], RecallOptions(), source_clock=False)
            after = audit.replay(conn, out['trace_id'], RecallOptions())
            comparison = audit.compare(conn, [out['trace_id']], RecallOptions(), policies=('packet-v18',))
            assert comparison['policies']['packet-v18']['reproduced'] == 1
        assert after['reproduced'] is True
        assert after['text'] == out['packet']['text']
        assert before['text'] == out['packet']['text'].split('  <SourceTimeNote>')[0] + '</NarrativeMemory>'
        assert [e for e in after['lines'] if e['kind'] != 'source_time'] == before['lines']
        assert after['tokens'] <= 4000
        trace = c.get(f"/v1/trace/{out['trace_id']}").json()
        assert trace['recall_options']['source_clock'] is True


@pytest.mark.parametrize('policy,strict,narrator', [('packet-v16', False, None), ('packet-v17', False, None),
                                                  ('packet-v18', True, None), ('packet-v18', False, '서윤')])
def test_old_policies_and_restricted_modes_do_not_add_clocks(migrated, clock_story, policy, strict, narrator):
    path, chat, _ = clock_story
    from nmos_sidecar.retrieval import gather, compile_gathered
    from nmos_sidecar.parsers import load_rules
    with make_client(migrated, parsers_file=str(path), packet_policy=policy) as c:
        sync(c, chat, character_name='Clock test')
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            head = conn.execute('SELECT head_commit_id FROM conversation WHERE host_chat_ref=%s', (chat.id,)).fetchone()['head_commit_id']
            opts = RecallOptions(policy=policy, rules_version=load_rules(str(path)).version, strict=strict, narrator=narrator)
            g = gather(conn, head, '은빛종을 건넨 건 언제였지?', '', set(), opts)
            assert not g.source_clocks
            assert '<SourceTime' not in compile_gathered(g, 4000, policy).text


def test_legacy_trace_missing_option_and_non_temporal_query_stay_unchanged(migrated, clock_story):
    path, chat, _ = clock_story
    with make_client(migrated, parsers_file=str(path)) as c:
        sync(c, chat, character_name='Clock test')
        normal = recall(c, chat, '서윤이 도윤에게 건넨 은빛종을 떠올린다.', budget=4000)
        assert '<SourceTime' not in normal['packet']['text']
        out = recall(c, chat, '은빛종을 건넨 건 언제였지?', budget=4000)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            explicit = audit.replay(conn, out['trace_id'], RecallOptions(), source_clock=False)
            conn.execute("UPDATE retrieval_trace SET recall_options = recall_options - 'source_clock' WHERE id=%s", (out['trace_id'],))
            missing = audit.replay(conn, out['trace_id'], RecallOptions())
        assert missing['text'] == explicit['text']
        assert '<SourceTime' not in missing['text']


def test_exact_revision_membership_rules_and_ambiguous_fields(migrated, clock_story):
    from nmos_sidecar import source_time
    from nmos_sidecar.parsers import load_rules
    path, chat, _ = clock_story
    with make_client(migrated, parsers_file=str(path)) as c:
        sync(c, chat, character_name='Clock test')
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            head = conn.execute('SELECT head_commit_id FROM conversation WHERE host_chat_ref=%s', (chat.id,)).fetchone()['head_commit_id']
            rid = str(conn.execute('SELECT source_revision_id FROM active_membership WHERE commit_id=%s AND position=1', (head,)).fetchone()['source_revision_id'])
            version = load_rules(str(path)).version
            assert source_time.read(conn, head, version, [rid], 1, -1)[rid].turn == 0
            assert not source_time.read(conn, head, version, [rid], 0, -1)
            assert not source_time.read(conn, head, version, [rid], 16, 1)
            assert not source_time.read(conn, head, 'wrong-rules', [rid], 16, -1)
            assert not source_time.read(conn, uuid4(), version, [rid], 16, -1)
            conn.execute("INSERT INTO state_observation (conversation_id,source_revision_id,rules_version,rule_id,key,value)"
                         " SELECT conversation_id,source_revision_id,rules_version,'other-clock','date',value"
                         " FROM state_observation WHERE source_revision_id=%s AND key='Date'", (rid,))
            clock = source_time.read(conn, head, version, [rid], 16, -1)[rid]
            assert [k for k, _, _ in clock.fields] == ['Time']
        chat.disable(1)
        sync(c, chat, character_name='Clock test')
        out = recall(c, chat, '은빛종을 건넨 건 언제였지?', budget=4000)
        assert '0712-03-01' not in out['packet']['text']


def test_spare_budget_only_source_limit_and_escaping():
    from nmos_sidecar import source_time
    from nmos_sidecar.packet import Excerpt, compile_lines
    items = [Excerpt(n, 'speaker', f'A distinct scene number {n} with a source.', 1.0, str(uuid4())) for n in range(3)]
    base = compile_lines(items, 4000, policy='packet-v18')
    clocks = {e.revision_id: source_time.Clock(e.revision_id, e.turn, 'rules',
              (('Date', 'yesterday <not-a-tag>', 'clock'), ('Time', 'Morning', 'clock'))) for e in items}
    full = source_time.supplement(base, items, clocks, 4000, 'packet-v18')
    root = ET.fromstring(full.text)
    assert len(root.findall('SourceTime')) == 2
    assert root.find('SourceTime/Field').text == 'yesterday <not-a-tag>'
    assert root.find('SourceTime/Field/not-a-tag') is None
    assert full.excerpts == base.excerpts and full.ledger[:len(base.ledger)] == base.ledger
    tight = source_time.supplement(base, items, clocks, base.tokens, 'packet-v18')
    assert tight == base
    hidden = dataclasses.replace(base, excerpts=[])
    assert source_time.supplement(hidden, items, clocks, 4000, 'packet-v18') == hidden


def test_clock_secret_overlap_is_withheld_even_when_the_excerpt_is_safe(migrated, clock_story, monkeypatch):
    from nmos_sidecar import retrieval
    from nmos_sidecar.parsers import load_rules
    path, chat, _ = clock_story
    original = retrieval.memory_view
    def with_secret(*args, **kwargs):
        view = original(*args, **kwargs)
        return {**view, 'secrets': [*view['secrets'], {'text': 'Hana knows: 0712-03-01',
                                                    'holders': ['Hana'], 'open': ['Kaito']}]}
    monkeypatch.setattr(retrieval, 'memory_view', with_secret)
    with make_client(migrated, parsers_file=str(path)) as c:
        sync(c, chat, character_name='Clock test')
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            head = conn.execute('SELECT head_commit_id FROM conversation WHERE host_chat_ref=%s', (chat.id,)).fetchone()['head_commit_id']
            opts = RecallOptions(rules_version=load_rules(str(path)).version, extractor_key='missing-extractor')
            g = retrieval.gather(conn, head, '은빛종을 건넨 건 언제였지?', '', set(), opts)
            assert g.ranked and '은빛종' in g.ranked[0].text
            assert all('0712-03-01' not in clock.text() for clock in g.source_clocks.values())


def test_late_clock_read_abstains_and_restores_a_shorter_caller_timeout(migrated, clock_story, monkeypatch):
    from nmos_sidecar import source_time
    from nmos_sidecar.parsers import load_rules
    path, chat, _ = clock_story
    with make_client(migrated, parsers_file=str(path)) as c:
        sync(c, chat, character_name='Clock test')
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            head = conn.execute('SELECT head_commit_id FROM conversation WHERE host_chat_ref=%s', (chat.id,)).fetchone()['head_commit_id']
            rid = str(conn.execute('SELECT source_revision_id FROM active_membership WHERE commit_id=%s AND position=1', (head,)).fetchone()['source_revision_id'])
            conn.execute("SET LOCAL statement_timeout = '20ms'")
            tick = iter((0.0, 0.021))
            monkeypatch.setattr(source_time.time, 'perf_counter', lambda: next(tick))
            assert source_time.read(conn, head, load_rules(str(path)).version, [rid], 16, -1) == {}
            assert conn.execute('SHOW statement_timeout').fetchone()['statement_timeout'] == '20ms'
            assert conn.execute('SELECT 1 AS ok').fetchone()['ok'] == 1


def test_edited_source_and_other_card_never_borrow_the_old_clock(migrated, clock_story):
    from nmos_sidecar import source_time
    from nmos_sidecar.parsers import load_rules
    path, chat, _ = clock_story
    version = load_rules(str(path)).version
    with make_client(migrated, parsers_file=str(path)) as c:
        sync(c, chat, character_name='Clock test')
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            old_head = conn.execute('SELECT head_commit_id FROM conversation WHERE host_chat_ref=%s', (chat.id,)).fetchone()['head_commit_id']
            old_revision = str(conn.execute('SELECT source_revision_id FROM active_membership WHERE commit_id=%s AND position=1', (old_head,)).fetchone()['source_revision_id'])
        chat.edit(1, chat.messages[1]['data'].split('☆ [')[0])
        sync(c, chat, character_name='Clock test')
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            head = conn.execute('SELECT head_commit_id FROM conversation WHERE host_chat_ref=%s', (chat.id,)).fetchone()['head_commit_id']
            edited = str(conn.execute('SELECT source_revision_id FROM active_membership WHERE commit_id=%s AND position=1', (head,)).fetchone()['source_revision_id'])
            assert old_revision != edited
            assert not source_time.read(conn, head, version, [old_revision, edited], 16, -1)
            # Superseded revisions remain raw evidence, but must not contribute a new clock.
            assert not source_time.read(conn, old_head, version, [old_revision], 16, -1)
            assert conn.execute('SELECT 1 FROM source_revision WHERE id=%s', (old_revision,)).fetchone()
        other = SimChat()
        other.user('다른 이야기다.')
        other.reply('서윤이 은빛종을 건넸다. ☆ [Date: 0712-03-01 | Time: 07:05]')
        other.user('기억한다.')
        sync(c, other, character_name='Another card')
        out = recall(c, other, '은빛종을 건넨 것은 언제였지?', budget=4000)
        assert '<SourceTime' not in out['packet']['text']
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            head = conn.execute('SELECT head_commit_id FROM conversation WHERE host_chat_ref=%s', (other.id,)).fetchone()['head_commit_id']
            assert not source_time.read(conn, head, version, [old_revision], 16, -1)


def test_flashback_and_repeated_key_keep_literal_parser_contract(migrated, clock_story):
    path, chat, _ = clock_story
    chat.edit(1, '서윤은 3년 전 은빛종을 건네던 날을 회상했다.\n☆ [Date: 0709-03-01 | Time: Dawn]\n'
              + '그 기억이 한참 동안 이어졌다. ' * 100 + '\n☆ [Date: 0712-03-01 | Time: Morning]')
    with make_client(migrated, parsers_file=str(path)) as c:
        sync(c, chat, character_name='Clock test')
        out = recall(c, chat, '은빛종을 건네던 것은 언제였지?', budget=4000)
        root = ET.fromstring(out['packet']['text'])
        fields = {e.attrib['key']: e.text for e in root.findall('SourceTime')[0]}
        assert fields == {'Date': '0712-03-01', 'Time': 'Morning'}
        assert 'Do not date a flashback' in root.findtext('SourceTimeNote')


def test_cancelled_clock_query_recovers_transaction_and_timeout(migrated, clock_story):
    from nmos_sidecar import source_time
    from nmos_sidecar.parsers import load_rules
    path, chat, _ = clock_story
    with make_client(migrated, parsers_file=str(path)) as c:
        sync(c, chat, character_name='Clock test')
        with psycopg.connect(migrated, row_factory=dict_row) as conn, psycopg.connect(migrated) as locker:
            head = conn.execute('SELECT head_commit_id FROM conversation WHERE host_chat_ref=%s', (chat.id,)).fetchone()['head_commit_id']
            rid = str(conn.execute('SELECT source_revision_id FROM active_membership WHERE commit_id=%s AND position=1', (head,)).fetchone()['source_revision_id'])
            conn.execute("SET LOCAL statement_timeout = '50ms'")
            locker.execute('LOCK TABLE state_observation IN ACCESS EXCLUSIVE MODE')
            assert source_time.read(conn, head, load_rules(str(path)).version, [rid], 16, -1) == {}
            assert conn.execute('SHOW statement_timeout').fetchone()['statement_timeout'] == '50ms'
            assert conn.execute('SELECT 1 AS ok').fetchone()['ok'] == 1
