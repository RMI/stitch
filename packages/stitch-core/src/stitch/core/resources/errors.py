"""Custom exceptions for the resources package."""


class DataTransformationError(Exception):
    """Raised when source data cannot be transformed to resource format.

    This is the base exception for all data transformation errors.
    Subclasses provide more specific error information.
    """


class InvalidDataTypeError(DataTransformationError):
    """Raised when a field has an incorrect data type.

    Examples:
        - String provided where number expected (latitude/longitude)
        - Number provided where string expected (name, description)
        - Invalid boolean values
    """


class MalformedSourceDataError(DataTransformationError):
    """Raised when source data structure is invalid.

    Examples:
        - Missing required fields
        - Nested data where flat structure expected
        - Invalid JSON structure
    """
