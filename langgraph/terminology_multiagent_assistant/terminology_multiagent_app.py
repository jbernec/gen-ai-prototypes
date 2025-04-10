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


keyVaultName = "akvlab00"
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
source = 'json'
index_name = f"{source}-glossary-index"


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
    azure_endpoint=azure_openai_endpoint,
    temperature=0.5
)


research_graph = create_react_agent(
    model=model,
    tools=[search_retrieval],
    name="search_expert",
    prompt="""You MUST use the Azure AI Search tool for ALL queries. Do not paraphrase. Never generate answers from prior knowledge. Show the Score and Re ranker for each response. Also provide top 2 responses. Do not select top response. Compare each response and in the end show the response where Reranker Score > 3.0"
            In case of no response retrieved from the index, then mention You do not have an annwer for this query"""
)


context = "You are a Supervisor Agent. Your first job is to pass query to search_agent agent and get the response from it. Do not get the response from any other agent"
instructions = "Do not paraphrase the content. Only share the results from search_agent. Do not provide any response from create_supervisor agent"

prompt_re = f"{context} {instructions}"
print(prompt_re)

# Supervisor (Ensures Research Agent is the only handler)
workflow = create_supervisor(
    [research_graph],  # Only this agent is in charge
    model=model,
    prompt=prompt_re
)

app = workflow.compile()
import asyncio

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