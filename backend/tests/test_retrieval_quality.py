"""Fixed recall cases for SourceLibrary.retrieve.

Measured on this fixture corpus (12 queries, top-5):
- Old top-5 hit rate (unigram + term count): 0.667 (8/12)
- New top-5 hit rate (Chinese bigram + BM25): 1.000 (12/12)
"""
from __future__ import annotations

import re
from pathlib import Path

from backend.app.sources import SourceLibrary, tokenize_terms
from backend.tests.conftest import make_client
from backend.tests.test_sources_api import create_subject, upload_source, wait_for_operation

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "retrieval"

CASES = [
    {"query": "拥塞控制", "source_name": "计算机网络讲义", "location_contains": "拥塞"},
    {"query": "滑动窗口", "source_name": "计算机网络讲义", "location_contains": "滑动窗口"},
    {"query": "慢启动", "source_name": "计算机网络讲义", "location_contains": "拥塞"},
    {"query": "TCP", "source_name": "TCP 协议", "location_contains": "Transmission"},
    {"query": "slow start", "source_name": "计算机网络讲义", "location_contains": "拥塞"},
    {"query": "congestion window", "source_name": "TCP 协议", "location_contains": "Transmission"},
    {"query": "throughput", "source_name": "测量数据", "location_contains": "测量"},
    {"query": "吞吐量", "source_name": "计算机网络讲义", "location_contains": "吞吐"},
    {"query": "Bernoulli", "source_name": "概率公式", "location_contains": "伯努利"},
    {"query": "伯努利公式", "source_name": "概率公式", "location_contains": "伯努利"},
    {"query": "RTT", "source_name": "测量数据", "location_contains": "测量"},
    {"query": "Cubic", "source_name": "测量数据", "location_contains": "测量"},
]

FILES = [
    ("networks.md", "计算机网络讲义"),
    ("noise.md", "噪声杂文"),
    ("tcp.md", "TCP 协议"),
    ("tables.md", "测量数据"),
    ("formulas.md", "概率公式"),
]


def _legacy_terms(query: str) -> list[str]:
    folded = query.casefold()
    return list(dict.fromkeys(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]", folded)))


def _legacy_retrieve(query: str, anchors: list[dict], limit: int = 5) -> list[dict]:
    terms = _legacy_terms(query)
    scored = []
    for anchor in anchors:
        text = SourceLibrary._anchor_text(anchor).casefold()
        score = sum(text.count(term) for term in terms)
        if score:
            scored.append((score, anchor))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [anchor for _, anchor in scored[:limit]]


def _hit(results: list[dict], case: dict, names: dict[str, str]) -> bool:
    needle = case["location_contains"].casefold()
    expected = case["source_name"]
    for anchor in results[:5]:
        if names.get(anchor.get("source_id")) != expected:
            continue
        label = str((anchor.get("location") or {}).get("label") or "")
        if needle in label.casefold():
            return True
    return False


def _upload_corpus(client, library: SourceLibrary):
    subject_id = create_subject(client, "检索评估")
    version_ids = []
    names = {}
    for filename, display_name in FILES:
        content = (FIXTURES / filename).read_bytes()
        uploaded = upload_source(client, subject_id, filename, content, "text/markdown", display_name)
        operation = wait_for_operation(client, uploaded.json()["operation"]["id"])
        assert operation["status"] == "succeeded"
        version_id = operation["result"]["id"]
        version_ids.append(version_id)
        source_id = uploaded.json()["resource"]["id"]
        names[source_id] = display_name
    anchors = []
    for version_id in version_ids:
        anchors.extend(library.list_anchors(version_id))
    return version_ids, names, anchors


def test_bm25_recall_beats_unigram_baseline(tmp_path):
    client, app = make_client(tmp_path)
    library = app.state.source_library
    with client:
        version_ids, names, anchors = _upload_corpus(client, library)
        old_hits = 0
        new_hits = 0
        for case in CASES:
            if _hit(_legacy_retrieve(case["query"], anchors), case, names):
                old_hits += 1
            if _hit(library.retrieve(case["query"], version_ids), case, names):
                new_hits += 1
        old_rate = old_hits / len(CASES)
        new_rate = new_hits / len(CASES)
        # Keep these comments in sync with the module docstring after any corpus change.
        # Old 0.667 (8/12); new 1.000 (12/12).
        assert abs(old_rate - 8 / 12) < 1e-9
        assert abs(new_rate - 12 / 12) < 1e-9
        assert new_rate >= old_rate
        assert new_rate > old_rate


def test_congestion_control_outranks_unigram_noise(tmp_path):
    client, app = make_client(tmp_path)
    library = app.state.source_library
    with client:
        version_ids, names, anchors = _upload_corpus(client, library)
        results = library.retrieve("拥塞控制", version_ids)
        assert results
        assert names[results[0]["source_id"]] == "计算机网络讲义"
        assert "拥塞" in results[0]["location"]["label"]
        noise_ids = {source_id for source_id, name in names.items() if name == "噪声杂文"}
        expected = next(index for index, item in enumerate(results) if names[item["source_id"]] == "计算机网络讲义")
        noise_indexes = [index for index, item in enumerate(results) if item.get("source_id") in noise_ids]
        assert not noise_indexes or expected < noise_indexes[0]

        legacy = _legacy_retrieve("拥塞控制", anchors)
        assert legacy
        # Old unigram counting prefers 控/制 noise; new ranking must not.
        assert names[legacy[0]["source_id"]] == "噪声杂文"


def test_chinese_query_uses_adjacent_bigrams():
    assert tokenize_terms("拥塞控制") == ["拥塞", "塞控", "控制"]
    assert tokenize_terms("TCP") == ["tcp"]
    assert tokenize_terms("slow start") == ["slow", "start"]
    assert tokenize_terms("控") == ["控"]
