import base64
import json
import logging

logger = logging.getLogger('logger')

def get_authenticated_user_details(request_headers) -> dict:
    """
    Liest EasyAuth-Header (X-MS-CLIENT-PRINCIPAL…)
    oder im DEV-Modus sample_user aus.
    Gibt ein user_object zurück mit den Keys:
      user_principal_id, user_name, auth_provider, auth_token,
      client_principal_b64, aad_id_token,
      display_name, email, roles, oid, claims (raw list)
    """
    # DEV-Fallback, wenn EasyAuth-Header fehlen
    principal_b64 = request_headers.get("X-MS-CLIENT-PRINCIPAL")
    if not principal_b64:
        from . import sample_user
        raw = sample_user.sample_user
        principal_b64 = raw.get("X-MS-CLIENT-PRINCIPAL")
        headers = raw
    else:
        headers = request_headers

    user_object = {
        "user_principal_id": headers.get("X-MS-CLIENT-PRINCIPAL-ID"),
        "user_name":         headers.get("X-MS-CLIENT-PRINCIPAL-NAME"),
        "auth_provider":     headers.get("X-MS-CLIENT-PRINCIPAL-IDP"),
        "auth_token":        headers.get("X-MS-TOKEN-AAD-ID-TOKEN"),
        "client_principal_b64": headers.get("X-MS-CLIENT-PRINCIPAL"),
        "aad_id_token":         headers.get("X-MS-TOKEN-AAD-ID-TOKEN"),
        # werden weiter unten überschrieben, falls vorhanden:
        "display_name": None,
        "email":        None,
        "roles":        [],
        "oid":          None,
        "claims":       []
    }

    # dekodiere den Principal
    try:
        decoded = base64.b64decode(principal_b64).decode("utf-8")
        principal = json.loads(decoded)
    except Exception as e:
        logger.warning("Konnte X-MS-CLIENT-PRINCIPAL nicht dekodieren: %s", e)
        return user_object

    # Top-Level-Felder aus dem Principal
    # (EasyAuth v2 liefert hier bereits:
    #   userRoles, identityProvider, userId, userDetails)
    user_object.update({
        "user_principal_id":   principal.get("userId") or user_object["user_principal_id"],
        "user_name":           principal.get("userDetails") or user_object["user_name"],
        "auth_provider":       principal.get("identityProvider") or user_object["auth_provider"],
    })

    # Claims-Liste als Rohdaten mitliefern
    claims: list[dict] = principal.get("claims", [])
    user_object["claims"] = claims

    # 1) Direkte Rolle(n), wenn EasyAuth sie bereitstellt
    roles = principal.get("userRoles")
    if roles is None:
        # 2) Fallback: suche in den claims nach typ == role_typ
        role_typ = principal.get("role_typ")
        if role_typ:
            roles = [c["val"] for c in claims if c.get("typ") == role_typ]
    user_object["roles"] = roles or []

    # Anzeigename (falls extra)
    name_typ = principal.get("name_typ")
    if name_typ:
        user_object["display_name"] = next((c["val"] for c in claims if c.get("typ") == name_typ), None)

    # E-Mail (preferred_username oder claim endet auf emailaddress)
    email = next(
        (c["val"] for c in claims
            if c.get("typ") == "preferred_username"
            or c.get("typ", "").endswith("emailaddress")),
        None
    )
    user_object["email"] = email

    # Object ID (oid)
    oid = next(
        (c["val"] for c in claims
            if c.get("typ", "").endswith("objectidentifier")
            or c.get("typ") == "oid"),
        None
    )
    user_object["oid"] = oid

    logger.warning(user_object)

    return user_object
