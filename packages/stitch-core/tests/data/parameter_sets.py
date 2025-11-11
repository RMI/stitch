"""Parameterized test data sets for reuse across test modules."""

import pytest

from stitch.core.resources.errors import InvalidDataTypeError, MalformedSourceDataError


# Unicode test cases for resource fields
UNICODE_TEST_CASES = [
    pytest.param(
        {"name": "Test Field 世界", "country": "China", "dataset": "gem"},
        {"name": "Test Field 世界", "country": "China"},
        id="chinese-characters",
    ),
    pytest.param(
        {"name": "حقل النفط", "operator": "شركة البترول", "dataset": "gem"},
        {"name": "حقل النفط", "operator": "شركة البترول"},
        id="arabic-rtl",
    ),
    pytest.param(
        {"name": "Oil Field 🚀", "description": "Production 🎉", "dataset": "gem"},
        {"name": "Oil Field 🚀", "description": "Production 🎉"},
        id="emoji-characters",
    ),
    pytest.param(
        {"name": "Test\u200bField", "operator": "Op\u200bCo", "dataset": "gem"},
        {"name": "Test\u200bField", "operator": "Op\u200bCo"},
        id="zero-width-characters",
    ),
]


# Data type validation error cases
DATA_TYPE_ERROR_CASES = [
    pytest.param(
        {"latitude": "not-a-number", "name": "Test", "dataset": "gem"},
        InvalidDataTypeError,
        "latitude",
        id="string-for-latitude",
    ),
    pytest.param(
        {"longitude": "invalid", "name": "Test", "dataset": "gem"},
        InvalidDataTypeError,
        "longitude",
        id="string-for-longitude",
    ),
    pytest.param(
        {"name": 12345, "dataset": "gem"},
        InvalidDataTypeError,
        "name",
        id="number-for-name",
    ),
    pytest.param(
        {"description": ["list", "not", "string"], "name": "Test", "dataset": "gem"},
        InvalidDataTypeError,
        "description",
        id="list-for-description",
    ),
]


# Malformed source data cases
MALFORMED_DATA_CASES = [
    pytest.param(
        {},
        MalformedSourceDataError,
        "Missing required field",
        id="missing-all-fields",
    ),
    pytest.param(
        {"dataset": "gem"},
        MalformedSourceDataError,
        "Missing required field",
        id="missing-name",
    ),
    pytest.param(
        {"nested": {"name": "Test"}, "dataset": "gem"},
        MalformedSourceDataError,
        "Invalid structure",
        id="nested-data",
    ),
]
