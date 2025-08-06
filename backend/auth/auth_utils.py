import base64
import json
import logging

logger = logging.getLogger('logger')

def get_authenticated_user_details(request_headers):
    """
    Extract user details (display_name, email, roles, oid) from
    the EasyAuth X-MS-CLIENT-PRINCIPAL header.
    Falls back to sample_user in development if header is absent.
    """
    user_object = {}

    # Development fallback if header not present
    if "X-Ms-Client-Principal-Id" not in request_headers:
        from . import sample_user
        raw_user_object = sample_user.sample_user
        client_principal_b64 = raw_user_object.get("X-Ms-Client-Principal")
    else:
        raw_user_object = request_headers
        client_principal_b64 = raw_user_object.get("X-Ms-Client-Principal")

    # Basic header fields
    user_object['user_principal_id'] = raw_user_object.get('X-Ms-Client-Principal-Id')
    user_object['user_name']         = raw_user_object.get('X-Ms-Client-Principal-Name')
    user_object['auth_provider']     = raw_user_object.get('X-Ms-Client-Principal-Idp')
    user_object['auth_token']        = raw_user_object.get('X-Ms-Token-Aad-Id-Token')
    user_object['client_principal']  = client_principal_b64
    user_object['aad_id_token']      = raw_user_object.get('X-Ms-Token-Aad-Id-Token')

    # Decode and parse claims
    if client_principal_b64:
        try:
            decoded   = base64.b64decode(client_principal_b64).decode("utf-8")
            principal = json.loads(decoded)
            claims    = principal.get("claims", [])

            # Determine which claim types carry name and roles
            name_types = {
                principal.get("name_typ"),      # e.g. "http://.../claims/name"
                "name",                         # present in your token
                "preferred_username",           # fallback
            }
            role_types = {
                principal.get("role_typ"),      # e.g. "http://.../claims/role"
                "roles",                        # present in your token
                "role",                         # fallback
            }

            # Display name
            user_object["display_name"] = next(
                (c["val"] for c in claims if c.get("typ") in name_types and c.get("val")),
                None
            )

            # Email
            user_object["email"] = next(
                (c["val"] for c in claims
                 if c.get("typ") in ("preferred_username",) or c.get("typ", "").endswith("emailaddress")),
                None
            )

            # Roles list
            user_object["roles"] = [
                c["val"] for c in claims if c.get("typ") in role_types
            ]

            # Azure OID
            user_object["oid"] = next(
                (c["val"] for c in claims
                 if c.get("typ", "").endswith("objectidentifier") or c.get("typ") == "oid"),
                None
            )

        except Exception as e:
            logger.warning(f"Failed to decode X-MS-CLIENT-PRINCIPAL: {e}")
    else:
        logger.warning(f"X-MS-CLIENT-PRINCIPAL is not available in the request headers")

    return user_object
