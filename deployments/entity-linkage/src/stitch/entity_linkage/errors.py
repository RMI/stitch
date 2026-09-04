from stitch.client import StitchAPIError


class MalformedResourceError(Exception):
    """An API resource payload could not be mapped into a candidate.

    Raised when a payload is missing a required field or has an invalid shape
    (e.g. a missing or non-integer ``id``). It is a distinct type -- not a bare
    ``KeyError``/``ValidationError`` -- so the bulk runner can isolate a single
    malformed resource without masking a genuine programming error.
    """

    def __init__(self, message: str, *, resource_id: int | None = None) -> None:
        super().__init__(message)
        self.resource_id = resource_id


__all__ = ["MalformedResourceError", "StitchAPIError"]
