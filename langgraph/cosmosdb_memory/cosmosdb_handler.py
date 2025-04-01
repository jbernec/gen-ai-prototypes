# https://www.kaggle.com/code/pilarpieiro/example-cosmosdb-checkpointer-for-langgraph

# Add CosmosDB handler
from azure.cosmos import CosmosClient, exceptions, PartitionKey


class CosmosDBHandler:
    
    def __init__(self, endpoint, credential, database_name, collection):
        # self.client = CosmosClient(endpoint, {"masterKey": key})
        self.client = CosmosClient(endpoint, credential)
        self.database_name = database_name
        self.container_name = collection

        try:
            self.database = self.client.create_database(self.database_name)
        except exceptions.CosmosResourceExistsError:
            self.database = self.client.get_database_client(self.database_name)

        try:
            self.container = self.database.create_container(
                id=self.container_name, partition_key=PartitionKey()
            )
        except exceptions.CosmosResourceExistsError:
            self.container = self.database.get_container_client(self.container_name)
        except exceptions.CosmosHttpResponseError as e:
            print("Caught an error. {0}".format(e.message))

    def __enter__(self):
        return self

    def __exit__(self, endpoint, collection, traceback):
        self.client = None

    def update_conversation(self, item):
        self.container.upsert_item(body=item)
    