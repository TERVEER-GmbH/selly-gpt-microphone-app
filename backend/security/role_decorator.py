from functools import wraps
from quart import jsonify, request
from backend.auth.auth_utils import get_authenticated_user_details

def require_role(required_roles):
    """
    Decorator, der den Zugriff nur erlaubt, wenn der Benutzer eine bestimmte Rolle hat.

    :param required_roles: String (eine Rolle) oder Liste von Rollen
    """
    if isinstance(required_roles, str):
        required_roles = [required_roles]

    def decorator(f):
        @wraps(f)
        async def wrapped(*args, **kwargs):
            user = get_authenticated_user_details(request.headers)
            user_roles = user.get("roles", []) if user else []

            # Prüfen, ob eine der erforderlichen Rollen vorhanden ist
            if not any(role in user_roles for role in required_roles):
                return jsonify({
                    "error": "Forbidden: insufficient permissions",
                    "required_roles": required_roles
                }), 403

            return await f(*args, **kwargs)
        return wrapped
    return decorator
