"""Entity-linkage auth wiring.

All the mechanics live in :mod:`stitch.service.auth`; here we just bind a
:class:`~stitch.service.auth.ServiceAuth` to this service's settings and
re-export the dependencies the routers and tests import by name.
"""

from stitch.service.auth import ServiceAuth

from stitch.entity_linkage.settings import get_settings

_auth = ServiceAuth(is_auth_disabled=lambda: get_settings().auth_disabled)

validate_auth_config_at_startup = _auth.validate_auth_config_at_startup
get_token_claims = _auth.get_token_claims
require_permissions = _auth.require_permissions
get_current_user = _auth.get_current_user
get_request_auth_context = _auth.get_request_auth_context
initiated_by = _auth.initiated_by

Claims = _auth.Claims
CurrentUser = _auth.CurrentUser
AuthContext = _auth.AuthContext
