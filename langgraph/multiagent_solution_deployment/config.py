from utils import get_key_vault_client
from azure.search.documents.indexes.models import SemanticSearch
from azure.search.documents.indexes.models import SearchField, SearchFieldDataType, SemanticConfiguration, SemanticPrioritizedFields, SemanticField
from azure.search.documents.indexes.models import (
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    IndexingParameters,
    IndexingParametersConfiguration
)
from azure.core.credentials import AzureKeyCredential

# Initialize Key Vault client
KEY_VAULT_NAME = "akvlab00"  # Replace with your Key Vault name
key_vault_client = get_key_vault_client(KEY_VAULT_NAME)

# Retrieve secrets from Key Vault
AZURE_OPENAI_ENDPOINT = key_vault_client.get_secret("aoai-endpoint").value
AZURE_OPENAI_API_KEY = key_vault_client.get_secret("aoai-api-key").value
AZURE_OPENAI_EMBEDDING_MODEL = key_vault_client.get_secret("aoai-embedding-model").value
SEARCH_ENDPOINT = key_vault_client.get_secret("aisearch-endpoint").value
SEARCH_KEY = key_vault_client.get_secret("aisearch-key").value
DATA_SOURCE_CONNECTION_NAME = "json-terminology-ds"

# Retrieve additional secrets from Key Vault
RESOURCE_ID = key_vault_client.get_secret("ds-resource-id").value

# Azure AI Services Configuration
AZURE_AI_SERVICES_KEY = key_vault_client.get_secret(name="azure-ai-services-key").value
AZURE_AI_SERVICES_ENDPOINT = key_vault_client.get_secret(name="azure-ai-services-endpoint").value

# Static configurations
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = "text-embedding-3-small"
AZURE_OPENAI_VECTOR_DIMENSION = 1536
BLOB_CONTAINER_NAME = "json-data"
INDEX_NAME = "json-terminology-index"

# Add indexer name derived from index name
INDEXER_NAME = f"{INDEX_NAME}-indexer"

# Define the search credential using the SEARCH_KEY
search_credential = AzureKeyCredential(SEARCH_KEY)

# Search index fields
FIELDS = [
    SearchField(name="chunk_id", type=SearchFieldDataType.String, searchable=True, filterable=False, sortable=True, key=True, facetable=False, analyzer_name="keyword"),
    SearchField(name="parent_id", type=SearchFieldDataType.String, searchable=False, filterable=True, sortable=False, key=False, facetable=False),
    SearchField(name="chunk", type=SearchFieldDataType.String, searchable=True, filterable=False, sortable=False, facetable=False, key=False),
    SearchField(name="title", type=SearchFieldDataType.String, searchable=True, sortable=True, filterable=True, facetable=True),
    SearchField(name="text_vector", type=SearchFieldDataType.Collection(SearchFieldDataType.Single), searchable=True, filterable=False, sortable=False, facetable=False, key=False, vector_search_dimensions=AZURE_OPENAI_VECTOR_DIMENSION, vector_search_profile_name="myHnswProfile"),
    SearchField(name="gender", type=SearchFieldDataType.String, searchable=True, sortable=True, filterable=True, facetable=True),
    SearchField(name="definition", type=SearchFieldDataType.String, searchable=True, sortable=True, filterable=True, facetable=True),
    SearchField(name="context", type=SearchFieldDataType.String, searchable=True, sortable=True, filterable=True, facetable=True),
    SearchField(name="note", type=SearchFieldDataType.String, searchable=True, sortable=True, filterable=True, facetable=True),
    SearchField(name="incorrectTerm", type=SearchFieldDataType.String, searchable=True, sortable=True, filterable=True, facetable=True),
    SearchField(name="domain", type=SearchFieldDataType.String, searchable=True, sortable=True, filterable=True, facetable=True),
    SearchField(name="modificationDate", type=SearchFieldDataType.String, searchable=True, sortable=True, filterable=True, facetable=True),
    SearchField(name="source", type=SearchFieldDataType.String, searchable=True, sortable=True, filterable=True, facetable=True),
    SearchField(name="link", type=SearchFieldDataType.String, searchable=True, sortable=True, filterable=True, facetable=True),
    SearchField(name="englishTerm", type=SearchFieldDataType.String, searchable=True, sortable=True, filterable=True, facetable=True),
    SearchField(name="creationDate", type=SearchFieldDataType.String, searchable=True, sortable=True, filterable=True, facetable=True),
]

# Vector search configuration
VECTOR_SEARCH = VectorSearch(
    algorithms=[HnswAlgorithmConfiguration(name="myHnsw")],
    profiles=[VectorSearchProfile(
        name="myHnswProfile",
        algorithm_configuration_name="myHnsw",
        vectorizer_name="myOpenAI"
    )],
    vectorizers=[AzureOpenAIVectorizer(
        vectorizer_name="myOpenAI",
        kind="azureOpenAI",
        parameters=AzureOpenAIVectorizerParameters(
            resource_url=AZURE_OPENAI_ENDPOINT,
            deployment_name=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
            model_name=AZURE_OPENAI_EMBEDDING_MODEL
        )
    )]
)

# Semantic configuration
SEMANTIC_CONFIGURATION = SemanticConfiguration(
    name="my-semantic-config",
    prioritized_fields=SemanticPrioritizedFields(
        title_field=SemanticField(field_name="chunk"),
        content_fields=[
            SemanticField(field_name="chunk"),
            SemanticField(field_name="context"),
            SemanticField(field_name="note"),
            SemanticField(field_name="incorrectTerm")
        ],
        keywords_fields=[
            SemanticField(field_name="chunk"),
            SemanticField(field_name="context"),
            SemanticField(field_name="note"),
            SemanticField(field_name="incorrectTerm")
        ]
    )
)

# Create the semantic search config
semantic_search = SemanticSearch(configurations=[SEMANTIC_CONFIGURATION])

# Indexing Parameters Configuration
INDEX_PARAMETERS = IndexingParameters(
    configuration=IndexingParametersConfiguration(
        data_to_extract="contentAndMetadata",  # Extract both content and metadata
        parsing_mode="jsonArray",  # Parsing mode for JSON array
        document_root="terms/term",  # Root path for documents
        query_timeout=None  # No timeout for queries
    )
)