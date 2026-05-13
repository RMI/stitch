from __future__ import annotations

import json
import pytest

from stitch.seed import payloads as payloads_module


def test_iter_payloads_wraps_static_sources_without_editing_files(
    monkeypatch, tmp_path
) -> None:
    payload_file = tmp_path / "seed.json"
    payload_file.write_text(
        json.dumps(
            {
                "id": None,
                "source_data": [
                    {"source": "gem", "name": "Alpha", "country": "USA"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(payloads_module, "version", lambda _: "0.1.0")
    monkeypatch.setattr(payloads_module, "uuid4", lambda: "run-123")

    [payload] = list(
        payloads_module.iter_payloads(
            static_payload_dir=str(tmp_path),
            faker_count=0,
            random_seed=7,
            seed_source="gem",
            null_prob=0.1,
        )
    )

    source = payload["source_data"][0]
    assert source["name"] == "Alpha"
    assert source["source_record"]["kind"] == "seed_static"
    assert source["source_record"]["run_id"] == "run-123"
    assert source["source_record"]["producer"] == "stitch-seed@0.1.0"
    assert source["source_record"]["payload"] == {
        "source": "gem",
        "name": "Alpha",
        "country": "USA",
    }


def test_iter_payloads_wraps_faker_sources_with_repro_metadata(monkeypatch) -> None:
    monkeypatch.setattr(payloads_module, "version", lambda _: "0.1.0")
    monkeypatch.setattr(payloads_module, "uuid4", lambda: "run-123")

    [payload] = list(
        payloads_module.iter_payloads(
            static_payload_dir=None,
            faker_count=1,
            random_seed=7,
            seed_source="gem",
            null_prob=0.1,
        )
    )

    source = payload["source_data"][0]
    record = source["source_record"]
    assert record["kind"] == "seed_faker"
    assert record["record_id"] == "run-123:1"
    assert record["run_id"] == "run-123"
    assert record["producer"] == "stitch-seed@0.1.0"
    assert record["payload"]["random_seed"] == 7
    assert record["payload"]["record_index"] == 1
    assert record["payload"]["seed_config"] == {
        "seed_source": "gem",
        "null_probability": 0.1,
    }
    assert record["payload"]["source_discriminator"] == source["source"]
    assert record["payload"]["generated_source"]["name"] == source["name"]


def test_iter_payloads_rejects_static_sources_with_existing_source_record(
    monkeypatch, tmp_path
) -> None:
    payload_file = tmp_path / "seed.json"
    payload_file.write_text(
        json.dumps(
            {
                "id": None,
                "source_data": [
                    {
                        "source": "gem",
                        "name": "Alpha",
                        "country": "USA",
                        "source_record": {"kind": "seed_static"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(payloads_module, "version", lambda _: "0.1.0")
    monkeypatch.setattr(payloads_module, "uuid4", lambda: "run-123")

    with pytest.raises(ValueError, match="must not include source_record"):
        list(
            payloads_module.iter_payloads(
                static_payload_dir=str(tmp_path),
                faker_count=0,
                random_seed=7,
                seed_source="gem",
                null_prob=0.1,
            )
        )
