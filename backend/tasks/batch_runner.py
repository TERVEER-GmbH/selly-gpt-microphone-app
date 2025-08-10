import asyncio
import logging
from quart import current_app
from backend.db.init_clients import cosmos_admin_db_ready

logger = logging.getLogger("logger")

# optionales Throttling zwischen Prompts (sek.)
THROTTLE_SECONDS = 25

async def background_runner():
    await cosmos_admin_db_ready.wait()
    client = current_app.cosmos_admin_client

    while True:
        try:
            pending = await client.list_runs(status="Pending")
            for run in pending:
                # Einheitlich: nutze die zentrale Logik
                asyncio.create_task(
                    client.run_tests(
                        run_id=run.id,
                        prompt_ids=run.prompt_ids,
                        params=run.params,
                        throttle_seconds=THROTTLE_SECONDS
                    )
                )
        except Exception:
            logger.exception("Background‐Runner: unerwarteter Fehler")
        await asyncio.sleep(10)
