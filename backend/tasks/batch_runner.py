import asyncio
import logging
from quart import current_app
from backend.db.init_clients import cosmos_admin_db_ready

logger = logging.getLogger("logger")

async def background_runner():
    await cosmos_admin_db_ready.wait()
    client = current_app.cosmos_admin_client

    while True:
        try:
            pending = await client.list_runs(status="Pending")
            for run in pending:
                # Starte im Hintergrund _denselben_ run_tests-Code
                asyncio.create_task(
                    client.run_tests(run.id, run.prompt_ids, run.params)
                )
        except Exception:
            logger.exception("Background‐Runner: unerwarteter Fehler")
        await asyncio.sleep(10)
