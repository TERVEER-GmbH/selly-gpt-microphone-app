import csv, json
import uuid
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from .base_cosmos import BaseCosmosClient
from typing import Tuple, List, IO, Optional, Callable, Awaitable

from azure.cosmos.exceptions import CosmosHttpResponseError

from backend.models.prompt import Prompt
from backend.models.testrun import TestRun, TestResult, TestParams

logger = logging.getLogger('logger')

class CosmosAdminClient(BaseCosmosClient):
    def __init__(self, endpoint, credential, database_name,
                 prompt_container="prompts", run_container="testruns", result_container="testresults"):
        super().__init__(endpoint, credential, database_name)
        self.prompt_container = self.database.get_container_client(prompt_container)
        self.run_container    = self.database.get_container_client(run_container)
        self.result_container = self.database.get_container_client(result_container)

    # ------------------------------------------------------------
    # Prompts-CRUD (unchanged)
    # ------------------------------------------------------------


    async def get_prompt(self, prompt_id: str) -> Prompt:
        doc = await self.prompt_container.read_item(
            item=prompt_id,
            partition_key=prompt_id
        )
        return Prompt.from_dict(doc)

    async def list_prompts(self) -> List[Prompt]:
        """
        Gibt alle Prompts als Domain-Modelle zurück und filtert
        automatisch alle Cosmos-Systemfelder raus.
        """
        prompts: List[Prompt] = []
        async for item in self.prompt_container.read_all_items():
            # Prompt.from_dict filtert id, text, golden_answer, tags
            prompts.append(Prompt.from_dict(item))
        return prompts

    async def create_prompt(self, text: str, golden_answer: str, tags: list[str]) -> Prompt:
        p = Prompt.create(text, golden_answer, tags)
        # prompt.id ist schon das Partition-Key-Feld
        await self.prompt_container.upsert_item(p.to_dict())
        return p

    async def update_prompt(self, prompt_id: str, text: str, golden_answer: str, tags: list[str]) -> Prompt:
        # Lade erst das bestehende Dokument
        doc = await self.prompt_container.read_item(item=prompt_id, partition_key=prompt_id)
        # Aktualisiere die Felder
        doc["text"] = text
        doc["golden_answer"] = golden_answer
        doc["tags"] = tags
        # Und upserte es
        await self.prompt_container.upsert_item(doc)
        return Prompt.from_dict(doc)

    async def delete_prompt(self, prompt_id: str) -> None:
        await self.prompt_container.delete_item(item=prompt_id, partition_key=prompt_id)

    async def import_prompts(self, stream: IO, content_type: str) -> Tuple[List[dict], List[Prompt]]:
        """
        Importiere Prompts aus CSV oder JSON.
        Liefert (errors, created_prompts).
        """
        errors: List[dict] = []
        created: List[Prompt] = []

        # 1) Rohdaten einlesen
        if "json" in content_type:
            try:
                data = json.load(stream)
                if not isinstance(data, list):
                    raise ValueError("JSON muss ein Array von Objekten sein")
            except Exception as ex:
                raise ValueError(f"Ungültiges JSON: {ex}")
        else:
            reader = csv.DictReader(stream)
            data = list(reader)

        # 2) Zeilen durchlaufen
        for idx, row in enumerate(data, start=1):
            try:
                # Core-Felder extrahieren
                text   = row.get("text") or row.get("prompt_text")
                golden = row.get("golden_answer")
                if not text or not golden:
                    raise ValueError("Feld 'text' und 'golden_answer' sind erforderlich")

                # Tags parsen
                tags_field = row.get("tags", "")
                tags = (
                    [t.strip() for t in tags_field.split(",")]
                    if isinstance(tags_field, str) and tags_field
                    else row.get("tags", [])
                )

                # ID aus Import beibehalten oder neu generieren
                provided_id = row.get("id")
                if provided_id:
                    # direkt upserten
                    prompt = Prompt(id=provided_id, text=text, golden_answer=golden, tags=tags)
                    await self.prompt_container.upsert_item(prompt.to_dict())
                else:
                    # create_prompt generiert neue ID und speichert
                    prompt = await self.create_prompt(text, golden, tags)

                created.append(prompt)

            except Exception as ex:
                errors.append({"line": idx, "error": str(ex)})

        return errors, created

    # ------------------------------------------------------------
    # TestRuns & TestResults
    # ------------------------------------------------------------

    async def start_run(self, prompt_ids: List[str], params: TestParams) -> str:
        run_id = str(uuid.uuid4())
        run = TestRun(
            id=run_id,
            prompt_ids=prompt_ids,
            params=params,
            status="Pending",
            created_at=datetime.now(timezone.utc).isoformat()
        )
        try:
            # create_item nutzt automatisch `id` als Partition-Key
            await self.run_container.create_item(run.to_dict())
            logger.debug("start_run: Created TestRun %s", run_id)
        except Exception as e:
            logger.exception("start_run: Failed to create TestRun %s", run_id)
            raise
        return run_id

    async def get_run(self, run_id: str) -> TestRun:
        """
        Liefert die Metadaten (ohne embedded results) aus dem Run-Container
        und hängt per list_results die echten Ergebnisse aus testresults an.
        """
        try:
            doc = await self.run_container.read_item(item=run_id, partition_key=run_id)
            run = TestRun.from_dict(doc)
        except Exception as e:
            logger.error("get_run: Fehler beim Lesen von Run %s: %s", run_id, e, exc_info=True)
            raise

        # jetzt die echten Ergebnisse holen
        try:
            run.results = await self.list_results(run_id)
        except Exception:
            # falls list_results schon Exception wirft, abfangen, aber Metadaten liefern wir trotzdem
            logger.warning("get_run: konnte Ergebnisse für Run %s nicht laden, liefere Metadaten ohne results", run_id)
        return run

    async def add_result(self, run_id: str, result: TestResult) -> None:
        """
        Speichert ein einzelnes TestResult im 'testresults'-Container (partition_key = run_id),
        zählt dann die bisherigen Ergebnisse für diesen Run und patched abschließend
        den Status des TestRun im 'testruns'-Container.
        """
        # 1) TestResult speichern
        try:
            doc = result.to_dict()
            # run_id als Partition-Key beilegen
            doc["run_id"] = run_id
            await self.result_container.create_item(
                body=doc,
                #partition_key=run_id
            )
            logger.debug("add_result: Stored TestResult %s for run %s", result.id, run_id)
        except Exception as e:
            logger.error("add_result: Fehler beim Speichern von TestResult %s: %s", result.id, e, exc_info=True)
            raise

        # 2) Anzahl abgeschlossener Ergebnisse abrufen
        try:
            count_query = "SELECT VALUE COUNT(1) FROM c WHERE c.run_id = @run_id"
            params = [{"name": "@run_id", "value": run_id}]
            completed = 0

            # Hier sorgt partition_key=run_id dafür, dass Cosmos nur diese Partition scannt
            iterator = self.result_container.query_items(
                query=count_query,
                parameters=params,
                partition_key=run_id
            )
            async for cnt in iterator:
                completed = cnt

            logger.debug("add_result: Run %s has %d completed results", run_id, completed)
        except Exception as e:
            logger.error("add_result: Fehler beim Zählen der Ergebnisse für Run %s: %s", run_id, e, exc_info=True)
            raise

        # 3) Status des TestRun updaten (Running vs. Done)
        try:
            # Zuerst die Metadaten des Runs holen
            run_doc = await self.run_container.read_item(item=run_id, partition_key=run_id)
            total = len(run_doc.get("prompt_ids", []))
            new_status = "Done" if completed >= total else "Running"

            # Patch-Operation nur für das status-Feld
            await self.run_container.patch_item(
                item=run_id,
                partition_key=run_id,
                patch_operations=[
                    {"op": "replace", "path": "/status", "value": new_status}
                ]
            )
            logger.debug("add_result: Updated status for run %s to %s", run_id, new_status)
        except Exception as e:
            logger.error("add_result: Fehler beim Patchen des Status für Run %s: %s", run_id, e, exc_info=True)
            raise


    async def list_runs(self, status: Optional[str] = None) -> List[TestRun]:
        """
        Liefert Metadaten aller TestRuns zurück (ohne embedded results).
        Filtert optional nach status.
        """
        query = "SELECT * FROM c"
        parameters = []
        if status:
            query += " WHERE c.status = @status"
            parameters = [{"name": "@status", "value": status}]

        runs: List[TestRun] = []
        try:
            iterator = self.run_container.query_items(query=query, parameters=parameters)
            async for doc in iterator:
                runs.append(TestRun.from_dict(doc))
            logger.debug("list_runs: Retrieved %d runs (status=%s)", len(runs), status)
            return runs
        except CosmosHttpResponseError as e:
            logger.error("list_runs: Cosmos query failed: %s", e, exc_info=True)
            raise

    async def update_run(self, run: TestRun) -> None:
        """
        Vollständiges Upsert eines TestRun (inkl. embedded results).
        """
        # serialisieren
        try:
            item = asdict(run)
            item["params"]  = asdict(run.params)
            item["results"] = [r.to_dict() for r in run.results]
        except Exception as e:
            logger.exception("update_run: Serialisierung fehlgeschlagen für run %s", run.id)
            raise

        # upsert
        try:
            await self.run_container.upsert_item(item)
            logger.debug("update_run: Upserted run %s (status=%s, %d results)", run.id, run.status, len(run.results))
        except CosmosHttpResponseError as e:
            logger.error("update_run: CosmosDB-Fehler beim Upsert von run %s: %s", run.id, e, exc_info=True)
            raise
        except Exception:
            logger.exception("update_run: Unerwarteter Fehler beim Upsert von run %s", run.id)
            raise

    async def list_results(self, run_id: str) -> List[TestResult]:
        """
        Holt alle TestResult-Dokumente für einen Run aus dem result_container
        (Partition-Key = run_id).
        """
        query = "SELECT * FROM c WHERE c.run_id = @run_id"
        params = [{"name": "@run_id", "value": run_id}]
        results: List[TestResult] = []
        try:
            iterator = self.result_container.query_items(
                query=query,
                parameters=params,
                partition_key=run_id
            )
            results: List[TestResult] = []
            async for doc in iterator:
                results.append(TestResult.from_dict(doc))
            logger.debug("list_results: Gefunden %d Ergebnisse für Run %s", len(results), run_id)
            return results
        except Exception as e:
            logger.error("list_results: Fehler beim Lesen der Ergebnisse für Run %s: %s", run_id, e, exc_info=True)
            raise

    async def run_tests(self,
                        run_id: str,
                        prompt_ids: List[str],
                        params: TestParams,
                        *,
                        on_result: Callable[[TestResult], Awaitable[None]] | None = None
                       ) -> None:
        """
        Abarbeiten eines Runs (synchron oder im Hintergrund).
        - setzt status=Running
        - feuert für jeden Prompt call_ai_model ab
        - speichert jedes Ergebnis via add_result()
        - am Ende status=Done
        - optionaler on_result Hook wird nach jedem einzelnen TestResult aufgerufen
        """
        from backend.services.ai_client import call_ai_model  # zykluseitig hier importieren

        # 1) Running markieren
        await self.run_container.patch_item(
            item=run_id,
            partition_key=run_id,
            patch_operations=[{"op": "replace", "path": "/status", "value": "Running"}]
        )

        # 2) pro Prompt
        for pid in prompt_ids:
            try:
                prompt = await self.get_prompt(pid)
                try:
                    ai_resp = await call_ai_model(prompt.text, params)
                except Exception as e:
                    ai_resp = f"ERROR: {e}"
                    logger.error("run_tests: AI-Call für %s fehlgeschlagen: %s", pid, e)
                result = TestResult(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    prompt_id=prompt.id,
                    prompt_text=prompt.text,
                    ai_response=ai_resp,
                    golden_answer=prompt.golden_answer
                )

                # 3) Ergebnis speichern
                await self.add_result(run_id, result)

                # 4) Hook (z.B. Websocket, Live-UI-Update)
                if on_result:
                    await on_result(result)

            except Exception:
                logger.exception("run_tests: Unerwarteter Fehler bei Prompt %s", pid)

        # 5) Done markieren
        await self.run_container.patch_item(
            item=run_id,
            partition_key=run_id,
            patch_operations=[{"op": "replace", "path": "/status", "value": "Done"}]
        )
