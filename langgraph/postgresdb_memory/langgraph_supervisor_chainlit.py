from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langgraph_supervisor import  create_supervisor
from langgraph.prebuilt import  create_react_agent
from openai import AzureOpenAI
from langchain.schema.runnable.config import RunnableConfig
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
import time
from langgraph.checkpoint.memory import MemorySaver

try:
    keyVaultName = os.environ["KEY_VAULT_NAME"]
except KeyError:
    # Get input from user if not set
    keyVaultName = input("Please enter your Key Vault name: ")
    # Save for future cells in this session
    os.environ["KEY_VAULT_NAME"] = keyVaultName


keyVaultName = os.environ["KEY_VAULT_NAME"]
KVUri = f"https://{keyVaultName}.vault.azure.net"

credential = DefaultAzureCredential()
client = SecretClient(vault_url=KVUri, credential=credential)

azure_openai_endpoint=client.get_secret(name="aoai-endpoint").value
azure_openai_api_key=client.get_secret(name="aoai-api-key").value
azure_openai_api_version = "2024-02-15-preview"


import urllib.parse
import os

from azure.identity import DefaultAzureCredential

# IMPORTANT! This code is for demonstration purposes only. It's not suitable for use in production. 
# For example, tokens issued by Microsoft Entra ID have a limited lifetime (24 hours by default). 
# In production code, you need to implement a token refresh policy.

def get_connection_uri():

    # Read URI parameters from the environment
    dbhost = client.get_secret(name="postgres-hostname").value 
    dbname = client.get_secret(name="postgres-chatdb").value 
    dbuser = urllib.parse.quote(client.get_secret(name="postgres-dbuser").value)
    sslmode = "require"

    # Use passwordless authentication via DefaultAzureCredential.
    # IMPORTANT! This code is for demonstration purposes only. DefaultAzureCredential() is invoked on every call.
    # In practice, it's better to persist the credential across calls and reuse it so you can take advantage of token
    # caching and minimize round trips to the identity provider. To learn more, see:
    # https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/identity/azure-identity/TOKEN_CACHING.md 
    credential = DefaultAzureCredential()

    # Call get_token() to get a token from Microsft Entra ID and add it as the password in the URI.
    # Note the requested scope parameter in the call to get_token, "https://ossrdbms-aad.database.windows.net/.default".
    password = credential.get_token("https://ossrdbms-aad.database.windows.net/.default").token

    db_uri = f"postgresql://{dbuser}:{password}@{dbhost}/{dbname}?sslmode={sslmode}"
    return db_uri

conn_string = get_connection_uri()


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
index_name = "csv-glossary-index"


def search_retrieval(user_input:str) -> str:
        """
        Search and retrieve answers from Azure AI Search.
        Returns:
            str
        """
        query = user_input
        search_result = ""
        search_client = SearchClient(endpoint=search_endpoint, index_name=index_name, credential=search_credential)
        vector_query = VectorizableTextQuery(text=query, k_nearest_neighbors=2, fields="vector", exhaustive=True)

        r = search_client.search(  
        search_text=query,
        vector_queries=[vector_query],
        select=["id", "notes", "chunk"],
        query_type=QueryType.SEMANTIC,
        semantic_configuration_name='my-semantic-config',
        query_caption=QueryCaptionType.EXTRACTIVE,
        query_answer=QueryAnswerType.EXTRACTIVE,
        top=1
    )
        for result in r:  
            print(f"id: {result['id']}")  
            print(f"notes: {result['notes']}")  
            print(f"Score: {result['@search.score']}")  
            print(f"Content: {result['chunk']}")
            search_result += result['chunk']
        return search_result


connection_kwargs = {
    "autocommit": True,
    "prepare_threshold": 0,
}

from psycopg.errors import UndefinedTable

# Check if the checkpoints table exists and call setup if it doesn't
def setup_checkpointer_table(checkpointer):
    try:
        with checkpointer.conn.cursor() as cur:
            # Check if the checkpoints table exists
            cur.execute("""
                SELECT 1
                FROM information_schema.tables
                WHERE table_name = 'checkpoints';
            """)
            if not cur.fetchone():
                print("Table 'checkpoints' does not exist. Setting up...")
                checkpointer.setup()
            else:
                print("Table 'checkpoints' already exists. Skipping setup.")
    except UndefinedTable:
        print("Error: Table 'checkpoints' does not exist. Setting up...")
        checkpointer.setup()

# # Create a direct connection
# conn = psycopg.connect(conn_string)

# # Create PostgresSaver instance directly
# checkpointer = PostgresSaver(conn)

# setup_checkpointer_table(checkpointer)

# Function to get connection with retry logic
def get_postgres_connection(max_retries=3, retry_delay=2):
    retry_count = 0
    while retry_count < max_retries:
        try:
            # Add connect_timeout parameter
            conn_string_with_timeout = f"{conn_string}&connect_timeout=10"
            print(f"Attempting database connection (attempt {retry_count + 1}/{max_retries})...")
            return psycopg.connect(conn_string_with_timeout)
        except psycopg.Error as e:
            retry_count += 1
            print(f"Connection error: {str(e)}")
            if retry_count < max_retries:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 1.5  # Exponential backoff
            else:
                print("Max retries reached. Could not connect to PostgreSQL.")
                return None

# Try to connect with retries
conn = get_postgres_connection()

# Create checkpointer with fallback to memory if connection fails
if conn:
    print("Successfully connected to PostgreSQL database.")
    checkpointer = PostgresSaver(conn)
    try:
        setup_checkpointer_table(checkpointer)
    except Exception as e:
        print(f"Error setting up checkpointer table: {str(e)}")
        print("Using in-memory checkpointer instead.")
        checkpointer = MemorySaver()
else:
    print("Using in-memory checkpointer for this session.")
    checkpointer = MemorySaver()

# # Ensure the connection is active before using it
# def ensure_connection(checkpointer):
#     if checkpointer.conn.closed:
#         print("Reconnecting to the database...")
#         checkpointer.conn = psycopg.connect(conn_string)

# Ensure the connection is active before using it
def ensure_connection(checkpointer):
    if isinstance(checkpointer, PostgresSaver):
        if checkpointer.conn.closed:
            print("Reconnecting to the database...")
            new_conn = get_postgres_connection()
            if new_conn:
                checkpointer.conn = new_conn
            else:
                print("WARNING: Could not reconnect to database")
    # If using MemorySaver, no connection needs to be maintained

model = AzureChatOpenAI(
    model="gpt-4o", 
    api_key=azure_openai_api_key, 
    api_version=azure_openai_api_version, 
    azure_endpoint=azure_openai_endpoint
)

research_graph = create_react_agent(
    model=model,
    tools=[search_retrieval],
    name="search_expert",
    prompt="You are a world class researcher with access to an azure index. Use only the index response to respond.",
)

# Create supervisor workflow
supervisor = create_supervisor(
    agents=[research_graph],
    model=model,
    prompt=(
        "You are a team supervisor managing a search expert agent. Analyze the user input and delegate to the appropriate agent:\n"
        "Use the research_agent only to respond.\n"
        "If the user asks a question, respond with the answer from the research agent.\n"
        "If the user asks for a summary, respond with the summary from the research agent.\n"
        "If the user asks for a definition, respond with the definition from the research agent.\n"
        "Do not respond with any other information.\n"
    )
)

# Compile and run the workflow
####
graph = supervisor.compile(checkpointer=checkpointer)

@cl.on_message
async def main(message: cl.Message):
    ensure_connection(checkpointer)  # Ensure the connection is active
    
    # Create messages for each agent
    supervisor_msg = cl.Message(
    author="👨‍💼 Supervisor", 
    content="Analyzing your request...",
    elements=[cl.Image(url="https://img.icons8.com/color/48/000000/manager.png")]
)
    await supervisor_msg.send()
    
    research_msg = cl.Message(
    author="🔍 Research Agent",
    content="",
    elements=[cl.Image(url="https://img.icons8.com/color/48/000000/search.png")]
)
    
    # Show thinking indicator
    thinking = cl.Text(content="🔍 Processing your request...", name="thinking")
    await thinking.send(for_id=message.id)
    
    try:
        config = {"configurable": {"thread_id": "1"}}
        
        for chunk in graph.stream(
            {"messages": [HumanMessage(content=message.content)]},
            config,
            stream_mode="values",
        ):
            # Print for debugging
            print(f"Received chunk: {chunk}")
            
            # Extract step name and messages
            step_name = chunk.get("step_name", "")
            messages = chunk.get("messages", [])
            
            if messages and len(messages) > 0:
                last_message = messages[-1]
                
                # Handle supervisor messages
                if "supervisor" in step_name and isinstance(last_message, (AIMessage, AIMessageChunk)):
                    supervisor_msg.content = last_message.content
                    await supervisor_msg.update()
                
                # Handle research agent messages
                elif "search_expert" in step_name and isinstance(last_message, (AIMessage, AIMessageChunk)):
                    research_msg.content = last_message.content
                    # Only send if it has content
                    if not research_msg.sent and research_msg.content.strip():
                        await research_msg.send()
                    elif research_msg.sent:
                        await research_msg.update()
    
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(error_msg)
        supervisor_msg.content = error_msg
        await supervisor_msg.update()
    finally:
        await thinking.remove()

###
# @cl.on_message
# async def main(message: cl.Message):
#     ensure_connection(checkpointer)  # Ensure the connection is active
    
#     # Create a single response message
#     response = cl.Message(content="")
#     await response.send()
    
#     # Show thinking indicator
#     thinking = cl.Text(content="🔍 Processing your request...", name="thinking")
#     await thinking.send(for_id=message.id)
    
#     try:
#         config = {"configurable": {"thread_id": "1"}}
        
#         # Switch to values mode which provides more consistent structure
#         for chunk in graph.stream(
#             {"messages": [HumanMessage(content=message.content)]},
#             config,
#             stream_mode="values",
#         ):
#             # Print chunk structure to console for debugging
#             print(f"Received chunk: {chunk}")
            
#             # Extract messages from values structure
#             if "messages" in chunk and chunk["messages"]:
#                 messages = chunk["messages"]
#                 # Get the last message in the list
#                 last_message = messages[-1]
#                 if isinstance(last_message, (AIMessage, AIMessageChunk)):
#                     response.content = last_message.content
#                     await response.update()
#     except Exception as e:
#         # Display any errors to help with debugging
#         error_msg = f"Error: {str(e)}"
#         print(error_msg)  # Log to console
#         response.content = error_msg
#         await response.update()
#     finally:
#         # Always remove the thinking indicator
#         await thinking.remove()
####
# #ensure_connection(checkpointer)  # Ensure the connection is active
# config = {"configurable": {"thread_id": "1", "user_id": "charles.chinny@lg.com"}}

# @cl.on_chat_resume
# async def on_chat_resume(thread):
#     pass

# @cl.on_message
# async def main(message: cl.Message):
#     ensure_connection(checkpointer)  # Ensure the connection is active
#     answer = cl.Message(content="")
#     await answer.send()

#     config = {"configurable": {"thread_id": "1", "user_id": "charles.chinny@lg.com"}}

#     for msg, _ in graph.stream(
#         {"messages": [HumanMessage(content=message.content)]},
#         config,
#         stream_mode="messages",
#     ):
#         if isinstance(msg, AIMessageChunk):
#             answer.content += msg.content  # type: ignore
#             await answer.update()

# while True:
#     # Get user input
#     try:
#         user_input = input("User: ")
#         if user_input.lower() in ["quit", "exit", "q"]:
#             print("Goodbye!")
#             break
#         inputs = {"messages": [{"role": "user", "content": user_input}]}
#         results = graph.stream(input=inputs, config=config, stream_mode="values")
#         for result in results:
#             print("Assistant:", result["messages"][-1].pretty_print())
#     except:
#         # fallback if input() is not available
#         user_input = "What do you know about LangGraph?"
#         print("User: " + user_input)
#         inputs = {"messages": [{"role": "user", "content": user_input}]}
#         results = graph.stream(input=inputs, config=config, stream_mode="values")
#         for result in results:
#             print("Assistant:", result["messages"][-1].pretty_print())
#         break

