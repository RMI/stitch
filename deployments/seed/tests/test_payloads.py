from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter

from stitch.ogsi.model import OGFieldSource
from stitch.seed.payloads import REGIONS, iter_payloads


def test_iter_payloads_adds_source_record_to_faker_payloads() -> None:
    payloads = list(
        iter_payloads(
            static_payload_dir=None,
            faker_count=1,
            random_seed=7,
            seed_source="mixed",
            null_prob=0.1,
        )
    )

    assert len(payloads) == 1
    source = payloads[0]["source_data"][0]
    source_record = source["source_record"]

    assert source_record["record_id"] == "faker:1:1"
    assert source_record["run_id"]
    assert source_record["producer"].startswith("stitch-seed/")
    assert source_record["payload"]["kind"] == "seed_faker"
    assert source_record["payload"]["random_seed"] == 7
    assert source_record["payload"]["index"] == 1
    assert source_record["payload"]["seed_source"] == "mixed"
    assert source_record["payload"]["null_probability"] == 0.1

    original_source = dict(source)
    original_source.pop("source_record")
    assert source_record["payload"]["source"] == original_source


def test_faker_payloads_populate_region_and_ownership() -> None:
    payloads = list(
        iter_payloads(
            static_payload_dir=None,
            faker_count=40,
            random_seed=7,
            seed_source="mixed",
            null_prob=0.2,
        )
    )
    sources = [payload["source_data"][0] for payload in payloads]

    regions = {source["region"] for source in sources} - {None}
    assert regions
    assert regions <= set(REGIONS)

    owner_lists = [source["owners"] for source in sources if source["owners"]]
    operator_lists = [source["operators"] for source in sources if source["operators"]]
    assert owner_lists
    assert operator_lists

    for owners in owner_lists:
        assert all(owner["stake"] is not None for owner in owners)
        assert sum(owner["stake"] for owner in owners) == pytest.approx(100.0)
    for operators in operator_lists:
        assert all(operator["stake"] is None for operator in operators)

    # Everything generated must validate against the real model — including the
    # null-stake entries that the now-nullable `stake` permits.
    adapter = TypeAdapter(OGFieldSource)
    for source in sources:
        adapter.validate_python(source)


def test_iter_payloads_adds_source_record_to_static_payloads(tmp_path) -> None:
    payload_file = tmp_path / "source.json"
    payload_file.write_text(
        json.dumps(
            {
                "id": 1,
                "source_data": [{"source": "gem", "name": "Alpha", "country": "USA"}],
                "constituents": [],
            }
        ),
        encoding="utf-8",
    )

    payloads = list(
        iter_payloads(
            static_payload_dir=str(tmp_path),
            faker_count=0,
            random_seed=7,
            seed_source="gem",
            null_prob=0.1,
        )
    )

    assert len(payloads) == 1
    source = payloads[0]["source_data"][0]
    source_record = source["source_record"]

    assert source_record["record_id"] == "static:source.json:1:1"
    assert source_record["payload"] == {
        "kind": "seed_static",
        "source": {"source": "gem", "name": "Alpha", "country": "USA"},
        "path": str(payload_file),
        "item_index": 1,
        "source_index": 1,
    }


def test_iter_payloads_rejects_preexisting_source_record_in_static_payloads(
    tmp_path,
) -> None:
    payload_file = tmp_path / "source.json"
    payload_file.write_text(
        json.dumps(
            {
                "id": 1,
                "source_data": [
                    {
                        "source": "gem",
                        "name": "Alpha",
                        "country": "USA",
                        "source_record": {"producer": "already-there"},
                    }
                ],
                "constituents": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must not already include source_record"):
        list(
            iter_payloads(
                static_payload_dir=str(tmp_path),
                faker_count=0,
                random_seed=7,
                seed_source="gem",
                null_prob=0.1,
            )
        )
