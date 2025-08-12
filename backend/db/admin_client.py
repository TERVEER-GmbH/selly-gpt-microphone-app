import csv, json
import uuid
import logging
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from .base_cosmos import BaseCosmosClient
from typing import Tuple, List, IO, Optional, Callable, Awaitable, Any, Dict

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
            await self.result_container.create_item(body=doc)
            logger.debug("add_result: Stored TestResult %s for run %s", result.id, run_id)
        except Exception as e:
            logger.error("add_result: Fehler beim Speichern von TestResult %s: %s", result.id, e, exc_info=True)
            raise

        # 2) Anzahl abgeschlossener Ergebnisse abrufen
        try:
            count_query = "SELECT VALUE COUNT(1) FROM c WHERE c.run_id = @run_id"
            # Hier sorgt partition_key=run_id dafür, dass Cosmos nur diese Partition scannt
            iterator = self.result_container.query_items(
                query=count_query,
                parameters=[{"name": "@run_id", "value": run_id}],
                partition_key=run_id
            )
            completed = 0
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
                patch_operations=[{"op": "replace", "path": "/status", "value": new_status}]
            )
            logger.debug("add_result: Updated status for run %s to %s", run_id, new_status)
        except Exception as e:
            logger.error("add_result: Fehler beim Patchen des Status für Run %s: %s", run_id, e, exc_info=True)
            raise

    async def list_runs(self,
                        status: Optional[str] = None,
                        offset: Optional[int] = None,
                        limit: Optional[int] = None) -> List[TestRun]:
        """
        Liefert Metadaten aller TestRuns (ohne embedded results).
        Optional: Pagination via OFFSET/LIMIT, sortiert nach created_at DESC.
        """
        # Basisquery
        query = "SELECT * FROM c"
        parameters: List[Dict[str, Any]] = []
        if status:
            query += " WHERE c.status = @status"
            parameters.append({"name": "@status", "value": status})

        query += " ORDER BY c.created_at DESC"

        # OFFSET/LIMIT nur anhängen, wenn gewünscht
        if offset is not None or limit is not None:
            off = int(offset or 0)
            lim = int(limit or 1000)  # sane default
            query += f" OFFSET {off} LIMIT {lim}"

        runs: List[TestRun] = []
        try:
            iterator = self.run_container.query_items(query=query, parameters=parameters)
            async for doc in iterator:
                runs.append(TestRun.from_dict(doc))
            logger.debug("list_runs: Retrieved %d runs (status=%s, offset=%s, limit=%s)",
                        len(runs), status, offset, limit)
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

    async def list_results(self,
                        run_id: str,
                        offset: Optional[int] = None,
                        limit: Optional[int] = None) -> List[TestResult]:
        """
        Holt TestResult-Dokumente für einen Run (Partition-Key = run_id),
        optional paginiert, sortiert nach timestamp DESC (ISO8601).
        """
        query = "SELECT * FROM c WHERE c.run_id = @run_id ORDER BY c.timestamp DESC"
        params = [{"name": "@run_id", "value": run_id}]

        if offset is not None or limit is not None:
            off = int(offset or 0)
            lim = int(limit or 1000)
            query += f" OFFSET {off} LIMIT {lim}"

        results: List[TestResult] = []
        try:
            iterator = self.result_container.query_items(
                query=query,
                parameters=params,
                partition_key=run_id
            )
            async for doc in iterator:
                results.append(TestResult.from_dict(doc))
            logger.debug("list_results: %d Ergebnisse für Run %s (offset=%s, limit=%s)",
                        len(results), run_id, offset, limit)
            return results
        except Exception as e:
            logger.error("list_results: Fehler beim Lesen der Ergebnisse für Run %s: %s", run_id, e, exc_info=True)
            raise

    _SCORE_FIELDS = {
        "relevance",
        "factual_accuracy",
        "completeness",
        "tone",
        "comprehensibility",
    }
    _COMMENT_FIELDS = {
        "relevance_comment",
        "factual_accuracy_comment",
        "completeness_comment",
        "tone_comment",
        "comprehensibility_comment",
        "overall_comment",
    }
    _EDITABLE_TEXT_FIELDS = {
        # optional: erlaube gezielt Korrektur der Texte
        "ai_response",
        "golden_answer",
    }

    def _normalize_update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Erlaubte Felder extrahieren und Werte normalisieren.
        Scores werden auf 1–5 gerundet/geclamp’t.
        Kommentare werden zu Strings getrimmt.
        """
        if not isinstance(payload, dict):
            return {}

        def clamp15(v):
            try:
                n = float(v)
            except Exception:
                return 3
            n = round(n)
            return max(1, min(5, int(n)))

        allowed_num = {
            "relevance",
            "factual_accuracy",
            "completeness",
            "tone",
            "comprehensibility",
        }
        allowed_str = {
            "relevance_comment",
            "factual_accuracy_comment",
            "completeness_comment",
            "tone_comment",
            "comprehensibility_comment",
            "overall_comment",
        }

        out: Dict[str, Any] = {}
        for k, v in payload.items():
            if k in allowed_num:
                out[k] = clamp15(v)
            elif k in allowed_str:
                out[k] = (v or "")
                if isinstance(out[k], str):
                    out[k] = out[k].strip()
                else:
                    out[k] = str(out[k]).strip()
        return out


    async def patch_result(self, run_id: str, result_id: str, payload: Dict[str, Any]) -> TestResult:
        """
        Aktualisiert ein TestResult-Dokument (Partition: run_id) in einem Schritt:
        - Dokument lesen
        - erlaubte Felder mergen
        - upsert_item (ein Schreibvorgang, kein 10-Ops-Limit wie bei Patch)
        """
        try:
            updates = self._normalize_update(payload)
            # Wenn nichts zu ändern ist, Original zurückgeben
            if not updates:
                doc = await self.result_container.read_item(item=result_id, partition_key=run_id)
                return TestResult.from_dict(doc)

            # 1) Bestehendes Dokument holen
            doc = await self.result_container.read_item(item=result_id, partition_key=run_id)

            # 2) Merge der Updates
            for k, v in updates.items():
                doc[k] = v

            # Partition-Key sicherstellen
            doc["run_id"] = run_id
            doc["id"] = result_id

            # 3) Upsert/Replace (ein Request)
            # Beides geht, upsert ist am einfachsten:
            await self.result_container.upsert_item(doc)
            # alternativ:
            # await self.result_container.replace_item(item=result_id, body=doc, partition_key=run_id)

            return TestResult.from_dict(doc)

        except Exception as e:
            logger.error(
                "patch_result: Fehler beim Upsert von %s/%s: %s",
                run_id, result_id, e, exc_info=True
            )
            raise

    async def compute_run_metrics(self, run_id: str) -> Dict[str, Any]:
        """
        Aggregiert Metriken für einen Run:
        - count: Anzahl Ergebnisse
        - category_averages: Mittelwerte pro Kategorie
        - avg_subscore: Mittelwert der Prompt-Subscores (Subscore = Mittel der 5 Kategorien)
        - overall_score: Mittelwert der Prompt-Gesamtscores (Produkt der 5 Kategorien) [Legacy]
        - product_score_avg: arithm. Mittel der rohen Produkte (1..3125, kann 0 sein falls Felder fehlen)
        - product_score_norm_avg: arithm. Mittel der normierten Produkte (fünftte Wurzel, ideal 1..5, kann 0 sein)
        """
        results = await self.list_results(run_id)
        n = len(results)
        if n == 0:
            return {
                "count": 0,
                "category_averages": {
                    "relevance": 0.0,
                    "factual_accuracy": 0.0,
                    "completeness": 0.0,
                    "tone": 0.0,
                    "comprehensibility": 0.0,
                },
                "avg_subscore": 0.0,
                "overall_score": 0.0,          # legacy
                "product_score_avg": 0.0,
                "product_score_norm_avg": 0.0,
            }

        sum_relevance = sum(float(getattr(r, "relevance", 0) or 0) for r in results)
        sum_factual   = sum(float(getattr(r, "factual_accuracy", 0) or 0) for r in results)
        sum_complete  = sum(float(getattr(r, "completeness", 0) or 0) for r in results)
        sum_tone      = sum(float(getattr(r, "tone", 0) or 0) for r in results)
        sum_comp      = sum(float(getattr(r, "comprehensibility", 0) or 0) for r in results)

        subscores = []
        products_raw = []
        products_norm = []

        for r in results:
            rel  = float(getattr(r, "relevance", 0) or 0)
            fact = float(getattr(r, "factual_accuracy", 0) or 0)
            comp = float(getattr(r, "completeness", 0) or 0)
            tone = float(getattr(r, "tone", 0) or 0)
            compr= float(getattr(r, "comprehensibility", 0) or 0)

            sub = (rel + fact + comp + tone + compr) / 5.0
            subscores.append(sub)

            prod = rel * fact * comp * tone * compr  # kann 0 sein (wenn alte 0.0-Defaults)
            products_raw.append(prod)

            # Normierung auf 1..5 gedacht; wenn prod==0 -> 0
            prod_norm = prod ** (1.0 / 5.0) if prod > 0 else 0.0
            products_norm.append(prod_norm)

        return {
            "count": n,
            "category_averages": {
                "relevance":         sum_relevance / n,
                "factual_accuracy":  sum_factual / n,
                "completeness":      sum_complete / n,
                "tone":              sum_tone / n,
                "comprehensibility": sum_comp / n,
            },
            "avg_subscore":           sum(subscores) / n,
            "overall_score":          sum(products_raw) / n,   # legacy beibehalten
            "product_score_avg":      sum(products_raw) / n,
            "product_score_norm_avg": sum(products_norm) / n,
        }

    async def run_tests(self,
                        run_id: str,
                        prompt_ids: List[str],
                        params: TestParams,
                        *,
                        on_result: Callable[[TestResult], Awaitable[None]] | None = None,
                        throttle_seconds: float = 0.0
                       ) -> None:
        """
        Abarbeiten eines Runs (synchron oder im Hintergrund).
        - setzt status=Running
        - feuert für jeden Prompt call_ai_model ab
        - speichert jedes Ergebnis via add_result()
        - am Ende status=Done
        - optionaler on_result Hook wird nach jedem einzelnen TestResult aufgerufen
        """
        # Lazy imports, um Zyklen zu vermeiden
        from backend.services.ai_client import call_ai_model
        from backend.services.comparator import compare_answers

        # Running
        await self.run_container.patch_item(
            item=run_id,
            partition_key=run_id,
            patch_operations=[{"op": "replace", "path": "/status", "value": "Running"}]
        )

        for pid in prompt_ids:
            try:
                prompt = await self.get_prompt(pid)

                # 1) AI
                try:
                    ai_resp = await call_ai_model(prompt.text, params)
                except Exception as e:
                    ai_resp = f"ERROR: {e}"
                    logger.error("run_tests: AI-Call für %s fehlgeschlagen: %s", pid, e)

                # 2) Compare (robust: bei Fehler trotzdem Result speichern)
                comp = None
                try:
                    comp = await compare_answers(prompt.text, ai_resp, prompt.golden_answer, params)
                except Exception as e:
                    logger.error("run_tests: compare_answers fehlgeschlagen für %s: %s", pid, e)

                # 3) Result
                result = TestResult(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    prompt_id=prompt.id,
                    prompt_text=prompt.text,
                    ai_response=ai_resp,
                    golden_answer=prompt.golden_answer,
                    timestamp=datetime.utcnow()
                )

                if comp:
                    result.relevance                 = comp.relevance
                    result.relevance_comment         = comp.relevance_comment
                    result.factual_accuracy          = comp.factual_accuracy
                    result.factual_accuracy_comment  = comp.factual_accuracy_comment
                    result.completeness              = comp.completeness
                    result.completeness_comment      = comp.completeness_comment
                    result.tone                      = comp.tone
                    result.tone_comment              = comp.tone_comment
                    result.comprehensibility         = comp.comprehensibility
                    result.comprehensibility_comment = comp.comprehensibility_comment
                    result.overall_comment           = comp.overall_comment

                # 4) speichern
                await self.add_result(run_id, result)

                 # 5) Callback
                if on_result:
                    await on_result(result)

                # 6) Throttling (z.B. Rate-Limits)
                if throttle_seconds > 0:
                    await asyncio.sleep(throttle_seconds)

            except Exception:
                logger.exception("run_tests: Unerwarteter Fehler bei Prompt %s", pid)

        # Done
        await self.run_container.patch_item(
            item=run_id, partition_key=run_id,
            patch_operations=[{"op": "replace", "path": "/status", "value": "Done"}]
        )
