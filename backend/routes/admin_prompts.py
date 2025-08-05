import io
import logging

from quart import Blueprint, request, jsonify, current_app
from backend.security.role_decorator import require_role
from backend.db.init_clients import cosmos_prompt_db_ready

logger = logging.getLogger('logger')

admin_bp = Blueprint("admin_prompts", __name__, url_prefix="/admin/prompts")


@admin_bp.route("", methods=["GET"])
@require_role("Admin")
async def list_prompts():
    """
    GET /admin/prompts
    Liefert eine Liste aller in der Prompts-Collection gespeicherten Prompts zurück.
    Nur für Admin-User verfügbar.

    Wartet auf erfolgreiche Initialisierung des Cosmos-Prompt-Clients.
    Gibt 404 zurück, wenn kein Prompt-Client konfiguriert ist.
    """
    logger.info("Admin requests list of prompts")
    await cosmos_prompt_db_ready.wait()

    client = current_app.cosmos_prompt_client
    if client is None:
        logger.warning("Prompt-Client nicht konfiguriert – list_prompts bricht ab")
        return jsonify({"error": "Prompt-DB nicht konfiguriert"}), 404

    prompts = await client.list_prompts()
    logger.info("Returning %d prompts", len(prompts))
    return jsonify([p.to_dict() for p in prompts]), 200


@admin_bp.route("", methods=["POST"])
@require_role("Admin")
async def create_prompt():
    """
    POST /admin/prompts
    Legt einen neuen Prompt mit Text, Golden-Answer und optionalen Tags an.
    Nur für Admin-User verfügbar.

    Erwartet JSON payload:
    {
        "text": "<Prompt-Text>",
        "golden_answer": "<Golden-Answer>",
        "tags": ["<Tag1>", "<Tag2>", ...]    // optional
    }

    Validiert Pflichtfelder und gibt 400 bei fehlenden Feldern zurück.
    Gibt 404, wenn kein Prompt-Client konfiguriert ist.
    """
    logger.info("Admin erstellt neuen Prompt")
    await cosmos_prompt_db_ready.wait()

    client = current_app.cosmos_prompt_client
    if client is None:
        logger.warning("Prompt-Client nicht konfiguriert – create_prompt bricht ab")
        return jsonify({"error": "Prompt-DB nicht konfiguriert"}), 404

    data = await request.get_json()
    if not data or "text" not in data or "golden_answer" not in data:
        logger.warning("Fehlende Felder in create_prompt: %s", data)
        return jsonify({"error": "Feld 'text' und 'golden_answer' sind erforderlich"}), 400

    try:
        prompt = await client.create_prompt(
            text=data["text"],
            golden_answer=data["golden_answer"],
            tags=data.get("tags", []),
        )
        logger.info("Prompt '%s' erfolgreich angelegt (ID=%s)", prompt.text, prompt.id)
        return jsonify(prompt.to_dict()), 201

    except Exception:
        logger.exception("Fehler beim Anlegen des Prompts")
        return jsonify({"error": "Could not create prompt"}), 500


@admin_bp.route("/<id>", methods=["PUT"])
@require_role("Admin")
async def update_prompt(id: str):
    """
    PUT /admin/prompts/<id>
    Aktualisiert einen bestehenden Prompt anhand seiner ID.
    Nur für Admin-User verfügbar.

    Erwartet JSON payload:
    {
        "text": "<neuer Prompt-Text>",
        "golden_answer": "<neue Golden-Answer>",
        "tags": ["<Tag1>", "<Tag2>", ...]    // optional
    }

    Validiert Pflichtfelder und gibt 400 bei fehlenden Feldern zurück.
    Gibt 404, wenn Prompt nicht existiert oder kein Prompt-Client konfiguriert ist.
    """
    logger.info("Admin aktualisiert Prompt %s", id)
    await cosmos_prompt_db_ready.wait()

    client = current_app.cosmos_prompt_client
    if client is None:
        logger.warning("Prompt-Client nicht konfiguriert – update_prompt bricht ab")
        return jsonify({"error": "Prompt-DB nicht konfiguriert"}), 404

    data = await request.get_json()
    if not data or "text" not in data or "golden_answer" not in data:
        logger.warning("Fehlende Felder in update_prompt: %s", data)
        return jsonify({"error": "Feld 'text' und 'golden_answer' sind erforderlich"}), 400

    try:
        updated = await client.update_prompt(
            prompt_id=id,
            text=data["text"],
            golden_answer=data["golden_answer"],
            tags=data.get("tags", []),
        )
        logger.info("Prompt %s erfolgreich aktualisiert", id)
        return jsonify(updated.to_dict()), 200

    except Exception as e:
        logger.exception("Fehler beim Aktualisieren des Prompts %s", id)
        return jsonify({"error": str(e)}), 404


@admin_bp.route("/<id>", methods=["DELETE"])
@require_role("Admin")
async def delete_prompt(id: str):
    """
    DELETE /admin/prompts/<id>
    Löscht den Prompt mit der angegebenen ID.
    Nur für Admin-User verfügbar.

    Gibt 404 zurück, wenn Prompt nicht existiert oder kein Prompt-Client konfiguriert ist.
    """
    logger.info("Admin löscht Prompt %s", id)
    await cosmos_prompt_db_ready.wait()

    client = current_app.cosmos_prompt_client
    if client is None:
        logger.warning("Prompt-Client nicht konfiguriert – delete_prompt bricht ab")
        return jsonify({"error": "Prompt-DB nicht konfiguriert"}), 404

    try:
        await client.delete_prompt(prompt_id=id)
        logger.info("Prompt %s erfolgreich gelöscht", id)
        return "", 204

    except Exception as e:
        logger.exception("Fehler beim Löschen des Prompts %s", id)
        return jsonify({"error": str(e)}), 404

@admin_bp.route("/import", methods=["POST"])
@require_role("Admin")
async def import_prompts():
    """
    POST /admin/prompts/import
    Importiert Prompts aus einer hochgeladenen CSV- oder JSON-Datei.
    Nur für Admin-User verfügbar.

    Erwartet multipart/form-data mit Feld 'file'.
    Unterstützte Formate:
      - CSV mit Spalten: id (optional), prompt_text, golden_answer, tags (optional)
      - JSON-Array von Objekten mit keys: text, golden_answer, tags (optional)

    Liefert im JSON-Response:
      {
        "errors": [ { "line": <Zeilennummer>, "error": "<Fehlermeldung>" }, … ],
        "created": [ <Liste neu angelegter Prompts> ]
      }
    """
    logger.info("Admin importiert Prompts via Datei-Upload")
    await cosmos_prompt_db_ready.wait()

    client = current_app.cosmos_prompt_client
    if client is None:
        logger.warning("Prompt-Client nicht konfiguriert – import_prompts bricht ab")
        return jsonify({"error": "Prompt-DB nicht konfiguriert"}), 404

    upload = (await request.files).get("file")
    if not upload:
        logger.warning("Kein File-Upload in import_prompts")
        return jsonify({"error": "Keine Datei hochgeladen. Feldname muss 'file' sein."}), 400

    try:
        # direkt aus dem SpooledTemporaryFile lesen (synchron)
        raw_bytes = upload.stream.read()
        text = raw_bytes.decode("utf-8")

        # StringIO für CSV/JSON
        stream = io.StringIO(text)
        content_type = upload.content_type or ""

        # Aufruf des Client-Importers
        errors, created_prompts = await client.import_prompts(stream, content_type)

    except ValueError as ex:
        logger.warning("Import-Fehler: %s", ex)
        return jsonify({"error": str(ex)}), 400

    except Exception:
        logger.exception("Unbekannter Fehler beim Import")
        return jsonify({"error": "Import fehlgeschlagen"}), 500

    status_code = 400 if errors else 201
    logger.info("Import abgeschlossen: %d erstellt, %d Fehler", len(created_prompts), len(errors))

    return jsonify({
        "errors": errors,
        "created": [p.to_dict() for p in created_prompts]
    }), status_code
