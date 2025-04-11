from langgraph.multiagent_solution.config import *
from utils import (
    get_key_vault_client,
    create_data_source,
    create_search_index,
    create_skillset,
    create_indexer
)
from azure.search.documents.indexes import SearchIndexerClient
from azure.core.credentials import AzureKeyCredential

# Initialize clients
key_vault_client = get_key_vault_client(KEY_VAULT_NAME)
indexer_client = SearchIndexerClient(endpoint=SEARCH_ENDPOINT, credential=AzureKeyCredential(SEARCH_KEY))

# Create data source
data_source = create_data_source(
    indexer_client=indexer_client,
    blob_container_name=BLOB_CONTAINER_NAME,
    resource_id=RESOURCE_ID,
    data_source_connection_name=DATA_SOURCE_CONNECTION_NAME
)
print(f"Data source created: {data_source.name}")

# Create search index
search_index = create_search_index(
    index_client=indexer_client,
    index_name=INDEX_NAME,
    azure_openai_vector_dimension=AZURE_OPENAI_VECTOR_DIMENSION,
    fields=FIELDS,
    vector_search=VECTOR_SEARCH,
    scoring_profiles=[],
    semantic_search=semantic_search
)
print(f"Search index created: {search_index.name}")

# Create skillset
skillset = create_skillset(
    skillset_name=f"{INDEX_NAME}-skillset",
    azure_openai_endpoint=AZURE_OPENAI_ENDPOINT,
    azure_openai_embedding_deployment=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    azure_openai_embedding_model=AZURE_OPENAI_EMBEDDING_MODEL,
    azure_openai_vector_dimension=AZURE_OPENAI_VECTOR_DIMENSION,
    azure_openai_api_key=AZURE_OPENAI_API_KEY,
    azure_ai_services_key=SEARCH_KEY,
    azure_ai_services_endpoint=SEARCH_ENDPOINT
)
indexer_client.create_or_update_skillset(skillset)
print(f"Skillset created: {skillset.name}")

# Create indexer
indexer_name = f"{INDEX_NAME}-indexer"
indexer = create_indexer(
    indexer_client=indexer_client,
    indexer_name=indexer_name,
    skillset_name=skillset.name,
    index_name=INDEX_NAME,
    data_source_name=data_source.name,
    index_parameters={}
)
print(f"Indexer created: {indexer.name}")