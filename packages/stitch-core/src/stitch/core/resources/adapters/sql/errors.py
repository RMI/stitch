from stitch.core.resources.errors import StitchResourcesError


class PersistenceError(StitchResourcesError): ...


class EntityNotFoundError(PersistenceError): ...


class ResourceIntegrityError(PersistenceError): ...
