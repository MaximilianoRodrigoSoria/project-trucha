from pathlib import Path

import pytest

from trucha.embed import embed_text
from trucha.ingest.scanner import chunk_text, validate_repository_path
from trucha.retrieve import reciprocal_rank_fusion


def test_embedding_is_deterministic_and_normalized():
    first = embed_text("Hola truchos", dimensions=16)
    second = embed_text("Hola truchos", dimensions=16)
    assert first == second
    assert sum(value * value for value in first) == pytest.approx(1.0)


def test_chunker_preserves_line_numbers_and_overlap():
    chunks = chunk_text("\n".join(f"line {number}" for number in range(1, 8)), size=4, overlap=1)
    assert [(chunk.start_line, chunk.end_line) for chunk in chunks] == [(1, 4), (4, 7)]
    assert chunks[0].text.splitlines()[-1] == chunks[1].text.splitlines()[0]


def test_repository_path_must_be_inside_allowed_root(tmp_path: Path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    assert validate_repository_path(allowed, [tmp_path]) == allowed.resolve()
    with pytest.raises(ValueError, match="TRUCHA_ALLOWED_ROOTS"):
        validate_repository_path(outside, [allowed])


def test_reciprocal_rank_fusion_rewards_shared_results():
    scores = reciprocal_rank_fusion([["a", "b"], ["b", "c"]])
    assert scores["b"] > scores["a"]
    assert scores["b"] > scores["c"]
