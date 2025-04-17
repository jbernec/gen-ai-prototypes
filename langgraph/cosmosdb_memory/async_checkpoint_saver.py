import base64
from typing import Any, AsyncIterator, Dict, Optional, Sequence, Tuple

from azure.cosmos.aio import CosmosClient, DatabaseProxy
from langchain_core.runnables import RunnableConfig
from azure.identity import DefaultAzureCredential
import langgraph
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
)
from pydantic import BaseModel


class AsyncCosmosDBCheckpointSaverConfig(BaseModel):

    DATABASE: str
    ENDPOINT: str
    CHECKPOINTS_CONTAINER: str
    CHECKPOINT_WRITES_CONTAINER: str


class AsyncCosmosDBCheckpointSaver(BaseCheckpointSaver):
    """A checkpoint saver that stores checkpoints in a CosmosDB database."""

    client: CosmosClient
    db: DatabaseProxy

    def __init__(self, credential: DefaultAzureCredential, config: AsyncCosmosDBCheckpointSaverConfig) -> None:
        super().__init__()

        # Initialize Cosmos DB client
        self.client = CosmosClient(url=config.ENDPOINT, credential=credential)
        self.db = self.client.get_database_client(config.DATABASE)

        # Get containers: checkpoints and checkpoint_writes
        self.checkpoints_container = self.db.get_container_client(
            config.CHECKPOINTS_CONTAINER
        )
        self.writes_container = self.db.get_container_client(
            config.CHECKPOINT_WRITES_CONTAINER
        )

    def dumps_typed(self, obj: Any) -> Tuple[str, str]:
        """
        Serializes an object and encodes the serialized data in base64 format.
        Args:
            obj (Any): The object to be serialized.
        Returns:
            Tuple[str, str]: A tuple containing the type of the object as a string and the base64 encoded serialized data.
        """

        type_, serialized_ = self.serde.dumps_typed(obj)
        return type_, base64.b64encode(serialized_).decode("utf-8")

    def loads_typed(self, data: Tuple[str, str]) -> Any:
        """
        Deserialize a tuple containing a string and a base64 encoded string.
        Args:
            data (Tuple[str, str]): A tuple where the first element is a string and the second element is a base64 encoded string.
        Returns:
            Any: The deserialized object.
        """

        return self.serde.loads_typed(
            (data[0], base64.b64decode(data[1].encode("utf-8")))
        )

    def dumps(self, obj: Any) -> str:
        """
        Serializes an object to a base64-encoded string.
        Args:
            obj (Any): The object to serialize.
        Returns:
            str: The base64-encoded string representation of the serialized object.
        """

        return base64.b64encode(self.serde.dumps(obj)).decode("utf-8")

    def loads(self, data: str) -> Any:
        """
        Deserialize a base64 encoded string into a Python object.
        Args:
            data (str): The base64 encoded string to be deserialized.
        Returns:
            Any: The deserialized Python object.
        """

        return self.serde.loads(base64.b64decode(data.encode("utf-8")))

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Get a checkpoint tuple from the database.

        This method retrieves a checkpoint tuple from the CosmosDB database based on the
        provided config. If the config contains a "checkpoint_id" key, the checkpoint with
        the matching thread ID and checkpoint ID is retrieved. Otherwise, the latest checkpoint
        for the given thread ID is retrieved.

        Args:
            config (RunnableConfig): The config to use for retrieving the checkpoint.

        Returns:
            Optional[CheckpointTuple]: The retrieved checkpoint tuple, or None if no matching checkpoint was found.
        """
        assert "configurable" in config
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        if checkpoint_id := get_checkpoint_id(config):
            query = f"SELECT * FROM c WHERE c.thread_id = '{thread_id}' AND c.checkpoint_ns = '{checkpoint_ns}' AND c.checkpoint_id = '{checkpoint_id}'"
        else:
            query = f"SELECT * FROM c WHERE c.thread_id = '{thread_id}' AND c.checkpoint_ns = '{checkpoint_ns}' ORDER BY c.checkpoint_id DESC"

        result = [item async for item in self.checkpoints_container.query_items(query)]
        if result:
            doc = result[0]
            config_values = {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": doc["checkpoint_id"],
            }
            checkpoint = self.loads_typed((doc["type"], doc["checkpoint"]))
            _serialized_writes = self.writes_container.query_items(
                f"SELECT * FROM c WHERE c.thread_id = '{thread_id}' AND c.checkpoint_ns = '{checkpoint_ns}' AND c.checkpoint_id = '{doc['checkpoint_id']}'"
            )
            serialized_writes = [writes async for writes in _serialized_writes]

            pending_writes = [
                (
                    write_doc["task_id"],
                    write_doc["channel"],
                    self.loads_typed((write_doc["type"], write_doc["value"])),
                )
                for write_doc in serialized_writes
            ]
            return CheckpointTuple(
                {"configurable": config_values},
                checkpoint,
                self.loads(doc["metadata"]),
                (
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": doc["parent_checkpoint_id"],
                        }
                    }
                    if doc.get("parent_checkpoint_id")
                    else None
                ),
                pending_writes,
            )

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """List checkpoints from the database.

        This method retrieves a list of checkpoint tuples from the CosmosDB database based
        on the provided config. The checkpoints are ordered by checkpoint ID in descending order (newest first).

        Args:
            config (RunnableConfig): The config to use for listing the checkpoints.
            filter (Optional[Dict[str, Any]]): Additional filtering criteria for metadata. Defaults to None.
            before (Optional[RunnableConfig]): If provided, only checkpoints before the specified checkpoint ID are returned. Defaults to None.
            limit (Optional[int]): The maximum number of checkpoints to return. Defaults to None.

        Yields:
            Iterator[CheckpointTuple]: An iterator of checkpoint tuples.
        """
        query = "SELECT * FROM c"
        if config is not None:
            assert "configurable" in config
            query += f" WHERE c.thread_id = '{config['configurable']['thread_id']}' AND c.checkpoint_ns = '{config['configurable'].get('checkpoint_ns', '')}'"

        if filter:
            for key, value in filter.items():
                query += f" AND c.metadata.{key} = '{value}'"

        if before is not None:
            assert "configurable" in before
            query += (
                f" AND c.checkpoint_id < '{before['configurable']['checkpoint_id']}'"
            )

        query += " ORDER BY c.checkpoint_id DESC"

        if limit is not None:
            query += f" LIMIT {limit}"

        result = self.checkpoints_container.query_items(query)

        async for doc in result:
            checkpoint = self.loads_typed((doc["type"], doc["checkpoint"]))
            yield CheckpointTuple(
                {
                    "configurable": {
                        "thread_id": doc["thread_id"],
                        "checkpoint_ns": doc["checkpoint_ns"],
                        "checkpoint_id": doc["checkpoint_id"],
                    }
                },
                checkpoint,
                self.loads(doc["metadata"]),
                (
                    {
                        "configurable": {
                            "thread_id": doc["thread_id"],
                            "checkpoint_ns": doc["checkpoint_ns"],
                            "checkpoint_id": doc["parent_checkpoint_id"],
                        }
                    }
                    if doc.get("parent_checkpoint_id")
                    else None
                ),
            )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Save a checkpoint to the database.

        This method saves a checkpoint to the CosmosDB database. The checkpoint is associated
        with the provided config and its parent config (if any).

        Args:
            config (RunnableConfig): The config to associate with the checkpoint.
            checkpoint (Checkpoint): The checkpoint to save.
            metadata (CheckpointMetadata): Additional metadata to save with the checkpoint.
            new_versions (ChannelVersions): New channel versions as of this write.

        Returns:
            RunnableConfig: Updated configuration after storing the checkpoint.
        """
        assert "configurable" in config
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"]["checkpoint_ns"]
        checkpoint_id = checkpoint["id"]
        type_, serialized_checkpoint = self.dumps_typed(checkpoint)
        doc = {
            "id": f"{thread_id}_{checkpoint_ns}_{checkpoint_id}",
            "parent_checkpoint_id": config["configurable"].get("checkpoint_id"),
            "type": type_,
            "checkpoint": serialized_checkpoint,
            "metadata": self.dumps(metadata),
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint_id,
        }
        await self.checkpoints_container.upsert_item(doc)
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
    ) -> None:
        """Store intermediate writes linked to a checkpoint.

        This method saves intermediate writes associated with a checkpoint to the CosmosDB database.

        Args:
            config (RunnableConfig): Configuration of the related checkpoint.
            writes (Sequence[Tuple[str, Any]]): List of writes to store, each as (channel, value) pair.
            task_id (str): Identifier for the task creating the writes.
        """
        assert "configurable" in config
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"]["checkpoint_ns"]
        checkpoint_id = config["configurable"]["checkpoint_id"]
        for idx, (channel, value) in enumerate(writes):
            type_, serialized_value = self.dumps_typed(value)
            doc = {
                "id": f"{thread_id}_{checkpoint_ns}_{checkpoint_id}_{task_id}_{idx}",
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
                "task_id": task_id,
                "idx": idx,
                "channel": channel,
                "type": type_,
                "value": serialized_value,
            }
            await self.writes_container.upsert_item(doc)