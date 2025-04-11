from azure.search.documents import SearchClient
from azure.search.documents.models import (
    QueryType,
    QueryCaptionType,
    QueryAnswerType,
    VectorizableTextQuery
)
from azure.core.credentials import AzureKeyCredential
from config import SEARCH_KEY, search_credential, SEARCH_ENDPOINT

def custom_hybrid_semantic_search(search_endpoint, index_name, search_credential, query, vector_field="text_vector", top_k=3):
    """
    Perform a custom hybrid search with semantic reranking.

    Parameters:
        search_endpoint (str): The Azure Search endpoint.
        index_name (str): The name of the search index.
        search_credential (AzureKeyCredential): The Azure Search credential.
        query (str): The search query.
        vector_field (str): The field for vector search. Default is "text_vector".
        top_k (int): The number of top results to return. Default is 3.

    Returns:
        None: Prints the search results and semantic answers.
    """
    search_client = SearchClient(endpoint=search_endpoint, index_name=index_name, credential=search_credential)

    # Define the vector query
    vector_query = VectorizableTextQuery(
        text=query,
        k_nearest_neighbors=5,
        fields=vector_field,
        exhaustive=True
    )

    # Perform the hybrid search with semantic reranking
    results = search_client.search(
        search_text=query,
        vector_queries=[vector_query],
        select=["context", "chunk", "note", "incorrectTerm"],
        query_type=QueryType.SEMANTIC,
        semantic_configuration_name="my-semantic-config",
        query_caption=QueryCaptionType.EXTRACTIVE,
        query_answer=QueryAnswerType.EXTRACTIVE,
        top=top_k
    )

    # Extract and print semantic answers
    semantic_answers = results.get_answers()
    if semantic_answers:
        for answer in semantic_answers:
            if answer.highlights:
                print(f"Semantic Answer: {answer.highlights}")
            else:
                print(f"Semantic Answer: {answer.text}")
            print(f"Semantic Answer Score: {answer.score}\n")

    # Print the search results
    for result in results:
        print(f"Reranker Score: {result['@search.reranker_score']}")
        print(f"Content: {result['chunk']}")
        print(f"Context: {result['context']}")
        print(f"Note: {result['note']}")
        print(f"Incorrect Term: {result['incorrectTerm']}")

        captions = result.get("@search.captions", [])
        if captions:
            caption = captions[0]
            if caption.highlights:
                print(f"Caption: {caption.highlights}\n")
            else:
                print(f"Caption: {caption.text}\n")

if __name__ == "__main__":
    # Define required parameters
    search_endpoint = SEARCH_ENDPOINT  # Replace with your Azure Search endpoint
    index_name = "json-terminology-index"  # Replace with your index name
    query = "What is Agile?"  # Replace with your search query

    # Execute the custom hybrid semantic search function
    custom_hybrid_semantic_search(
        search_endpoint=search_endpoint,
        index_name=index_name,
        search_credential=search_credential,  # Use the correct search credential from the config file
        query=query
    )