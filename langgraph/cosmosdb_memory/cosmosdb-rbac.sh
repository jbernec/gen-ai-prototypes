#!/bin/bash
# filepath: c:\source\github\gen-ai-prototypes\langgraph\cosmosdb_memory\cosmosdb-rbac.sh

# Get Key Vault name from environment variable, or prompt if not set
if [ -z "${KEY_VAULT_NAME}" ]; then
    echo "KEY_VAULT_NAME environment variable is not set."
    read -p "Please enter your Key Vault name: " KEY_VAULT_NAME
    # Export for subsequent commands in this session
    export KEY_VAULT_NAME
fi

echo "Using Key Vault: $KEY_VAULT_NAME"

# Retrieve values from Key Vault
SUBSCRIPTION_ID=$(az keyvault secret show --name "subscription-id" --vault-name "$KEY_VAULT_NAME" --query value -o tsv)
RESOURCE_GROUP=$(az keyvault secret show --name "resource-group" --vault-name "$KEY_VAULT_NAME" --query value -o tsv)
COSMOS_ACCOUNT=$(az keyvault secret show --name "cosmos-account" --vault-name "$KEY_VAULT_NAME" --query value -o tsv)
PRINCIPAL_ID=$(az keyvault secret show --name "principal-id" --vault-name "$KEY_VAULT_NAME" --query value -o tsv)
ROLE_DEFINITION_ID=$(az keyvault secret show --name "role-definition-id" --vault-name "$KEY_VAULT_NAME" --query value -o tsv)

echo "Using parameters from Key Vault:"
echo "Subscription: $SUBSCRIPTION_ID"
echo "Resource Group: $RESOURCE_GROUP"
echo "Cosmos DB Account: $COSMOS_ACCOUNT"

# List role definitions
az cosmosdb sql role definition list --resource-group "$RESOURCE_GROUP" --account-name "$COSMOS_ACCOUNT"

# List role assignments
az cosmosdb sql role assignment list --resource-group "$RESOURCE_GROUP" --account-name "$COSMOS_ACCOUNT"

# Enable local auth (if needed)
az resource update \
  --resource-group "$RESOURCE_GROUP" \
  --name "$COSMOS_ACCOUNT" \
  --resource-type "Microsoft.DocumentDB/databaseAccounts" \
  --set properties.disableLocalAuth=false

# Enable NoSQL Vector Search
az cosmosdb update --resource-group "$RESOURCE_GROUP" --name "$COSMOS_ACCOUNT" --capabilities EnableNoSQLVectorSearch

# For custom role definition for data plane - read from a file which could also be parameterized
# https://community.cdata.com/data-sources-91/steps-to-create-a-custom-role-with-rbac-permissions-on-azure-to-manage-an-azure-cosmos-db-for-nosql-account-1121
# https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/security/how-to-grant-data-plane-role-based-access?tabs=custom-definition%2Ccsharp&pivots=azure-interface-cli

CUSTOM_ROLE_FILE="cosmosdb-data-role.json"
az cosmosdb sql role definition create --resource-group "$RESOURCE_GROUP" --account-name "$COSMOS_ACCOUNT" --body "@$CUSTOM_ROLE_FILE"

# Grab the role definition id from the output of the previous command

# Get Cosmos DB account resource ID to be used as value for the CosmosDB scope parameter
az cosmosdb show --resource-group "$RESOURCE_GROUP" --name "$COSMOS_ACCOUNT" --query "{id:id}"

# Create role assignment
SCOPE="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.DocumentDB/databaseAccounts/$COSMOS_ACCOUNT"

# Principal ID is the object ID of the user or service principal

az cosmosdb sql role assignment create \
  --resource-group "$RESOURCE_GROUP" \
  --account-name "$COSMOS_ACCOUNT" \
  --role-definition-id "$ROLE_DEFINITION_ID" \
  --principal-id "$PRINCIPAL_ID" \
  --scope "$SCOPE"