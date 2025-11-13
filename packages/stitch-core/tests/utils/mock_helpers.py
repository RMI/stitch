"""Helper functions for configuring mocks in tests."""

from typing import Any


def configure_source_mock(
    mock_tx: Any,
    data: dict[str, Any],
    source_pk: str = "source_123",
    write_error: Exception | None = None,
) -> Any:
    """Configure source repository mock with common settings.

    Args:
        mock_tx: Mock transaction context
        data: Data to return from row_to_record_data
        source_pk: Primary key to return from write (default: "source_123")
        write_error: Optional exception to raise from write

    Returns:
        Configured source repository mock
    """
    source_repo = mock_tx.source_registry.get_source_repository.return_value
    source_repo.row_to_record_data.return_value = data

    if write_error:
        source_repo.write.side_effect = write_error
    else:
        source_repo.write.return_value = source_pk

    return source_repo
