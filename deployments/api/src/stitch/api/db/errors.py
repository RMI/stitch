from stitch.api.errors import StitchAPIError


class ResourceNotFoundError(StitchAPIError): ...


class ResourceIntegrityError(StitchAPIError): ...


class InvalidActionError(StitchAPIError): ...
