import base64
import json
import logging

logger = logging.getLogger('logger')

def get_authenticated_user_details(request_headers):
    user_object = {}

    ## check the headers for the Principal-Id (the guid of the signed in user)
    if "X-Ms-Client-Principal-Id" not in request_headers.keys():
        ## if it's not, assume we're in development mode and return a default user
        from . import sample_user
        raw_user_object = sample_user.sample_user
        client_principal_b64 = raw_user_object.get("X-Ms-Client-Principal")
    else:
        ## if it is, get the user details from the EasyAuth headers
        raw_user_object = {k:v for k,v in request_headers.items()}
        client_principal_b64 = raw_user_object.get("X-Ms-Client-Principal")

    # Basisdaten aus den Standard Headern
    user_object['user_principal_id'] = raw_user_object.get('X-Ms-Client-Principal-Id')
    user_object['user_name'] = raw_user_object.get('X-Ms-Client-Principal-Name')
    user_object['auth_provider'] = raw_user_object.get('X-Ms-Client-Principal-Idp')
    user_object['auth_token'] = raw_user_object.get('X-Ms-Token-Aad-Id-Token')
    user_object['client_principal_b64'] = raw_user_object.get('X-Ms-Client-Principal')
    user_object['aad_id_token'] = raw_user_object.get('X-Ms-Token-Aad-Id-Token')

    # Claims aus X-MS-CLIENT-PRINCIPAL decodieren
    if client_principal_b64:
        try:
            decoded = base64.b64decode(client_principal_b64).decode("utf-8")
            principal = json.loads(decoded)

            claims_list    = principal.get("claims", [])
            name_claim_uri = principal.get("name_typ")
            role_claim_uri = principal.get("role_typ")

            # Anzeigename
            user_object["display_name"] = next(
                (c["val"] for c in claims_list if c["typ"] == name_claim_uri),
                None
            )

            # E-Mail (manchmal über preferred_username oder Email-URI)
            email = next(
                (c["val"] for c in claims_list if c["typ"].endswith("emailaddress") or c["typ"] == "preferred_username"),
                None
            )
            user_object["email"] = email

            # Alle Rollen
            user_object["roles"] = [
                c["val"] for c in claims_list if c["typ"] == role_claim_uri
            ]

            # Azure-OID (Object ID)
            oid = next(
                (c["val"] for c in claims_list if c["typ"].endswith("objectidentifier") or c["typ"] == "oid"),
                None
            )
            user_object["oid"] = oid

        except Exception as e:
            logger.warning(f"Failed to decode X-MS-CLIENT-PRINCIPAL: {e}")

    return user_object
