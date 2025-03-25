import openai
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langgraph_supervisor import  create_supervisor
from langgraph.prebuilt import  create_react_agent
import openai
import os
import azure.identity
from azure.identity import ClientSecretCredential
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
import langgraph
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection
from psycopg2 import connect
import psycopg
from azure.mgmt.postgresqlflexibleservers import PostgreSQLManagementClient
import chainlit as cl
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AIMessageChunk



try:
    keyVaultName = os.environ["KEY_VAULT_NAME"]
except KeyError:
    # Get input from user if not set
    keyVaultName = input("Please enter your Key Vault name: ")
    # Save for future cells in this session
    os.environ["KEY_VAULT_NAME"] = keyVaultName


keyVaultName = "akv-searchindex-llm"
KVUri = f"https://{keyVaultName}.vault.azure.net"

credential = DefaultAzureCredential()
client = SecretClient(vault_url=KVUri, credential=credential)

azure_openai_endpoint=client.get_secret(name="aoai-endpoint").value
azure_openai_api_key=client.get_secret(name="aoai-api-key").value
azure_openai_api_version = "2024-02-15-preview"

import urllib.parse
import os

from azure.identity import DefaultAzureCredential

from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.models import (
    QueryType,
    QueryCaptionType,
    QueryAnswerType
)

search_credential =AzureKeyCredential(client.get_secret(name="aisearch-key").value)
search_endpoint =client.get_secret(name="aisearch-endpoint").value
index_name = "json-glossary-index"


def search_retrieval(user_input: str) -> list:
    """
    Search and retrieve answers from Azure AI Search.
    Returns:
        list of dictionaries containing search results
    """
    print("######################### \n"
          "Search and retrieve answers from Azure AI Search. \n")
    query = user_input
    search_results = []  # Initialize an empty list to store dictionaries
    search_client = SearchClient(endpoint=search_endpoint, index_name=index_name, credential=search_credential)
    vector_query = VectorizableTextQuery(text=query, k_nearest_neighbors=2, fields="text_vector", exhaustive=True)

    r = search_client.search(
        search_text=query,
        vector_queries=[vector_query],
        select=["context", "chunk", "note", "incorrectTerm"],
        query_type=QueryType.SEMANTIC,
        semantic_configuration_name='my-semantic-config',
        query_caption=QueryCaptionType.EXTRACTIVE,
        query_answer=QueryAnswerType.EXTRACTIVE,
        top=5
    )
    for result in r:
        # Convert the result to a dictionary and append it to the list
        result_dict = {
            "incorrectTerm": result.get('incorrectTerm', ''),
            "context": result.get('context', ''),
            "definition": result.get('chunk', ''),
            "note": result.get('note', ''),
            "@search.score": result.get('@search.score', 0),
            "@search.reranker_score": result.get('@search.reranker_score', 0),
            "@search.highlights": result.get('@search.highlights', None),
            "@search.captions": result.get('@search.captions', None),
            "@search.document_debug_info": result.get('@search.document_debug_info', None)
        }
        print(f"Content: {result_dict} \n")
        search_results.append(result_dict)  # Append the dictionary to the list

    return search_results

# The AzureOpenAI class does not exist in the openai package. Use AzureChatOpenAI from langchain_openai instead.
from langchain_openai import AzureChatOpenAI
model = AzureChatOpenAI(
    model="gpt-4o", 
    api_key=azure_openai_api_key, 
    api_version=azure_openai_api_version, 
    azure_endpoint=azure_openai_endpoint
)

from langchain.tools import Tool
search_retrieval_tool = Tool(
    name="AzureSearch",
    func=search_retrieval,
    description="Strictly retrieves data from Azure AI Search Index ."
)


research_graph = create_react_agent(
    model=model,
    tools=[search_retrieval_tool],
    name="search_expert",
    prompt="You MUST use the Azure AI Search tool for ALL queries. Never generate answers from prior knowledge."
)



# Supervisor (Ensures Research Agent is the only handler)
workflow = create_supervisor(
    [research_graph],  # Only this agent is in charge
    model=model,
    prompt=(
        f""" You are a Supervisor Agent. Your first job is to pass query to resarch_graph agent and get the response from it.
        In your first line mention_ This response is from Azure Index, if it is retrieved from Azure Search Index else mention that it is from Internet and mention the source.
        # use {search_retrieval_tool} to retrieve the information from the index.          
        If the index does not contain the relevant information, indicate that you are unable to provide an answer based on the index. 
        Absolutely no external searches or sources are allowed
        Do not paraphrase the index content."""
    )
)

   # Please force your response to be based exclusively on the provided index. Do not search online or access any external sources. 
        # You are restricted to using only the content in the index for answering the question. 

app = workflow.compile()

@cl.on_message
async def on_message(msg: cl.Message):
    # Invoke the workflow with the user's message
    result = app.invoke({
        "messages": [
            {
                "role": "user",
                "content": msg.content
            }
        ]
    })
    # Extract and print the output from the result variable
    final_answer = cl.Message(content="")
    for m in result["messages"]:
        if isinstance(m, AIMessage):
            await final_answer.stream_token(f"🔨 {m.content}") 
        elif isinstance(m, ToolMessage):
            await final_answer.stream_token(f"🤖 {m.content}")
 
        # Stream a blank line after each message
        await final_answer.stream_token("\n\n")
 
    await final_answer.send()
 