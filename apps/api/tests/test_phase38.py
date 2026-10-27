"""Phase 3-8 — 분류 약한 매칭 보호, 데이터 건수 정합, 시연 데이터 백업·복원."""
import sqlite3

import pytest

from app.models.enums import ClassificationRelevance
from app.services.classification import classify_document_rule_based


def test_weak_single_keyword_in_body_only_is_held():
    body = "Federal Motor Vehicle Safety Standards. The rule mentions an autonomous vehicle once in passing."
    r = classify_document_rule_based(body, "Federal Motor Vehicle Safety Standards; FMVSS No. 305a")
    assert r["relevance"] == ClassificationRelevance.PENDING_REVIEW
    assert r["primary_field_code"] is None and "약한 단일 매칭" in r["reasoning"]


def test_keyword_in_title_still_matches():
    r = classify_document_rule_based("A study of large language model agents and machine learning.", "Large language model agents")
    assert r["relevance"] == ClassificationRelevance.MATCHED
    assert r["primary_field_code"].value == "ai"


def test_title_abbreviation_counts_as_title_keyword():
    r = classify_document_rule_based("NIST launches centers using artificial intelligence.", "NIST Launches Centers for AI in Manufacturing")
    assert r["relevance"] == ClassificationRelevance.MATCHED


def test_demo_backup_and_restore_roundtrip(tmp_path, monkeypatch):
    from app import demo_data
    db = tmp_path / "dev.db"
    con = sqlite3.connect(db)
    con.execute("create table t(x)"); con.execute("insert into t values (1)"); con.commit(); con.close()
    monkeypatch.setattr(demo_data, "DB", db)
    monkeypatch.setattr(demo_data, "BACKUP_DIR", tmp_path / "backups")
    saved = demo_data.backup("baseline")
    con = sqlite3.connect(db); con.execute("insert into t values (2)"); con.commit(); con.close()
    with pytest.raises(SystemExit):  # 확인(--yes) 없이는 복원하지 않는다
        demo_data.restore(saved.name, confirmed=False)
    demo_data.restore(saved.name, confirmed=True)
    con = sqlite3.connect(db)
    assert con.execute("select count(*) from t").fetchone()[0] == 1
    con.close()
    assert len(list((tmp_path / "backups").glob("dev-*before-restore.db"))) == 1  # 복원 직전 현재 DB가 먼저 백업됨
