import csv, json
from .base_cosmos import BaseCosmosClient
from typing import Tuple, List, IO
from backend.models.prompt import Prompt

class CosmosPromptClient(BaseCosmosClient):
    def __init__(self, endpoint, credential, database_name, container_name='Prompts'):
        super().__init__(endpoint, credential, database_name)
        self.container = self.database.get_container_client(container_name)

    async def list_prompts(self) -> List[Prompt]:
        """
        Gibt alle Prompts als Domain-Modelle zurück und filtert
        automatisch alle Cosmos-Systemfelder raus.
        """
        prompts: List[Prompt] = []
        async for item in self.container.read_all_items():
            # Prompt.from_dict filtert id, text, golden_answer, tags
            prompts.append(Prompt.from_dict(item))
        return prompts

    async def create_prompt(self, text: str, golden_answer: str, tags: list[str]) -> Prompt:
        p = Prompt.create(text, golden_answer, tags)
        # prompt.id ist schon das Partition-Key-Feld
        await self.container.upsert_item(p.to_dict())
        return p

    async def update_prompt(self, prompt_id: str, text: str, golden_answer: str, tags: list[str]) -> Prompt:
        # Lade erst das bestehende Dokument
        doc = await self.container.read_item(item=prompt_id, partition_key=prompt_id)
        # Aktualisiere die Felder
        doc["text"] = text
        doc["golden_answer"] = golden_answer
        doc["tags"] = tags
        # Und upserte es
        await self.container.upsert_item(doc)
        return Prompt.from_dict(doc)

    async def delete_prompt(self, prompt_id: str) -> None:
        await self.container.delete_item(item=prompt_id, partition_key=prompt_id)

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
                    await self.container.upsert_item(prompt.to_dict())
                else:
                    # create_prompt generiert neue ID und speichert
                    prompt = await self.create_prompt(text, golden, tags)

                created.append(prompt)

            except Exception as ex:
                errors.append({"line": idx, "error": str(ex)})

        return errors, created
