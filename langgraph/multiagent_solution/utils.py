import os
from azure.core.credentials import AzureKeyCredential
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexerClient
from azure.search.documents.indexes.models import (
    SearchIndexerDataContainer,
    SearchIndexerDataSourceConnection,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    SearchIndex,
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticField,
    SemanticSearch,
    SplitSkill,
    AzureOpenAIEmbeddingSkill,
    InputFieldMappingEntry,
    OutputFieldMappingEntry,
    SearchIndexerSkillset,
    SearchIndexerIndexProjection,
    SearchIndexerIndexProjectionSelector,
    SearchIndexerIndexProjectionsParameters,
    IndexProjectionMode,
    AIServicesAccountKey,
    SearchIndexer
)

def get_key_vault_client(key_vault_name):
    """Initialize Key Vault client."""
    kv_uri = f"https://{key_vault_name}.vault.azure.net"
    credential = DefaultAzureCredential()
    return SecretClient(vault_url=kv_uri, credential=credential)

def create_data_source(indexer_client, blob_container_name, resource_id, data_source_connection_name):
    """Create Azure AI Search data source."""
    indexer_container = SearchIndexerDataContainer(name=blob_container_name)
    data_source_connection = SearchIndexerDataSourceConnection(
        name=data_source_connection_name,
        type="azureblob",
        connection_string=resource_id,
        container=indexer_container
    )
    return indexer_client.create_or_update_data_source_connection(data_source_connection=data_source_connection)

def create_search_index(index_client, index_name, azure_openai_vector_dimension, fields, scoring_profiles, azure_openai_endpoint, azure_openai_embedding_deployment, azure_openai_embedding_model, semantic_search, vector_search=None):
    """Create Azure AI Search index with additional configurations."""
    if vector_search is None:
        vector_search = VectorSearch(
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
                    resource_url=azure_openai_endpoint,
                    deployment_name=azure_openai_embedding_deployment,
                    model_name=azure_openai_embedding_model
                )
            )]
        )

    index = SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
        scoring_profiles=scoring_profiles,
        semantic_search=semantic_search
    )
    return index_client.create_or_update_index(index=index)

def create_skillset(skillset_name, azure_openai_endpoint, azure_openai_embedding_deployment, azure_openai_embedding_model, azure_openai_vector_dimension, azure_openai_api_key, azure_ai_services_key, azure_ai_services_endpoint, index_name):
    """Create skillset for Azure AI Search with additional configurations."""
    split_skill = SplitSkill(
        description="Split skill to chunk documents",
        text_split_mode="pages",
        default_language_code="en",
        context="/document",
        maximum_page_length=2000,
        page_overlap_length=500,
        maximum_pages_to_take=0,
        unit="characters",
        inputs=[InputFieldMappingEntry(name="text", source="/document/definition")],
        outputs=[OutputFieldMappingEntry(name="textItems", target_name="pages")]
    )
    embedding_skill = AzureOpenAIEmbeddingSkill(
        description="Skill to generate embeddings",
        context="/document/pages/*",
        resource_url=azure_openai_endpoint,
        deployment_name=azure_openai_embedding_deployment,
        model_name=azure_openai_embedding_model,
        dimensions=azure_openai_vector_dimension,
        api_key=azure_openai_api_key,
        inputs=[InputFieldMappingEntry(name="text", source="/document/pages/*")],
        outputs=[OutputFieldMappingEntry(name="embedding", target_name="text_vector")]
    )

    index_projections = SearchIndexerIndexProjection(
        selectors=[
            SearchIndexerIndexProjectionSelector(
                target_index_name=index_name,
                parent_key_field_name="parent_id",
                source_context="/document/pages/*",
                mappings=[
                    InputFieldMappingEntry(name="text_vector", source="/document/pages/*/text_vector"),
                    InputFieldMappingEntry(name="chunk", source="/document/pages/*"),
                    InputFieldMappingEntry(name="title", source="/document/title"),
                    InputFieldMappingEntry(name="gender", source="/document/gender"),
                    InputFieldMappingEntry(name="definition", source="/document/definition"),
                    InputFieldMappingEntry(name="incorrectTerm", source="/document/incorrectTerm"),
                    InputFieldMappingEntry(name="domain", source="/document/domain"),
                    InputFieldMappingEntry(name="englishTerm", source="/document/englishTerm"),
                    InputFieldMappingEntry(name="creationDate", source="/document/creationDate"),
                    InputFieldMappingEntry(name="modificationDate", source="/document/modificationDate"),
                    InputFieldMappingEntry(name="source", source="/document/source"),
                    InputFieldMappingEntry(name="link", source="/document/link"),
                    InputFieldMappingEntry(name="context", source="/document/context"),
                    InputFieldMappingEntry(name="note", source="/document/note"),
                ]
            )
        ],
        parameters=SearchIndexerIndexProjectionsParameters(
            projection_mode=IndexProjectionMode.SKIP_INDEXING_PARENT_DOCUMENTS
        )
    )

    skills = [split_skill, embedding_skill]

    return SearchIndexerSkillset(
        name=skillset_name,
        description="Skillset to chunk documents and generate embeddings",
        skills=skills,
        index_projection=index_projections,
        cognitive_services_account=AIServicesAccountKey(key=azure_ai_services_key, subdomain_url=azure_ai_services_endpoint)
    )

def create_indexer(indexer_client, indexer_name, skillset_name, index_name, data_source_name, index_parameters):
    """Create Azure AI Search indexer with additional configurations."""
    indexer = SearchIndexer(
        name=indexer_name,
        description="Indexer to orchestrate the document indexing and embedding generation",
        skillset_name=skillset_name,
        target_index_name=index_name,
        data_source_name=data_source_name,
        parameters=index_parameters
    )
    return indexer_client.create_or_update_indexer(indexer=indexer)