from azure.cosmos.aio import CosmosClient
from azure.cosmos import exceptions

class BaseCosmosClient:
    def __init__(self, endpoint: str, credential: any, database_name: str):
        """
        Shared initialization for Cosmos DB clients.
        """
        try:
            self.client = CosmosClient(endpoint, credential=credential)
            self.database = self.client.get_database_client(database_name)
        except exceptions.CosmosHttpResponseError as e:
            if e.status_code == 401:
                raise ValueError("Invalid CosmosDB credentials") from e
            raise ValueError("Could not connect to CosmosDB endpoint") from e

    async def ensure(self, container_name: str):
        """Verifies that the database and container exist."""
        try:
            await self.database.read()
            container = self.database.get_container_client(container_name)
            await container.read()
            return True, "Container exists"
        except exceptions.CosmosResourceNotFoundError as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)
