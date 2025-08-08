import asyncio
import logging
from azure.identity.aio import DefaultAzureCredential
from quart import current_app

from backend.settings import app_settings
from backend.db.conversation_client import CosmosConversationClient
from backend.db.admin_client import CosmosAdminClient

logger = logging.getLogger('logger')

cosmos_history_db_ready = asyncio.Event()
cosmos_admin_db_ready = asyncio.Event()

async def init_cosmos_history_client():
    current_app.cosmos_conversation_client = None
    if app_settings.chat_history:
        try:
            cosmos_endpoint = (
                f"https://{app_settings.chat_history.account}.documents.azure.com:443/"
            )

            if not app_settings.chat_history.account_key:
                async with DefaultAzureCredential() as cred:
                    credential = cred

            else:
                credential = app_settings.chat_history.account_key

            current_app.cosmos_conversation_client = CosmosConversationClient(
                endpoint=cosmos_endpoint,
                credential=credential,
                database_name=app_settings.chat_history.database,
                container_name=app_settings.chat_history.conversations_container,
                enable_message_feedback=app_settings.chat_history.enable_feedback,
            )
        except Exception as e:
            logger.exception("Failed to initialize History DB client", e)
            current_app.cosmos_conversation_client = None
            raise e
    else:
        logger.debug("History DB not configured")

    return current_app.cosmos_conversation_client

async def init_cosmos_admin_client():
    current_app.cosmos_admin_client = None
    if app_settings.admin_db:
        try:
            endpoint = f"https://{app_settings.admin_db.account}.documents.azure.com:443/"
            # Auth wählen
            if app_settings.admin_db.account_key:
                credential = app_settings.admin_db.account_key
            else:
                async with DefaultAzureCredential() as cred:
                    credential = cred

            current_app.cosmos_admin_client = CosmosAdminClient(
                endpoint=endpoint,
                credential=credential,
                database_name=app_settings.admin_db.database,
                prompt_container=app_settings.admin_db.prompt_container,
                run_container=app_settings.admin_db.run_container,
                result_container=app_settings.admin_db.result_container,
            )
        except Exception as e:
            logger.exception("Failed to initialize Admin DB client")
            raise
    else:
        logger.debug("Admin DB not configured")
    return current_app.cosmos_admin_client
