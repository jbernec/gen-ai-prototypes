# https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/security/how-to-grant-data-plane-role-based-access?tabs=built-in-definition%2Cpython&pivots=azure-interface-cli#code-try-0

az cosmosdb sql role definition list --resource-group "rg" --account-name "cosm"

az cosmosdb show --resource-group "rg" --name "cosm" --query "{id:id}"

# the principal id is the EntraiDI object id
az cosmosdb sql role assignment create --resource-group "rg" --account-name "cosm" --role-definition-id "/subscriptions/00000000-0000-0000-0000-0000000/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/cosm/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002" --principal-id "44444444-a198-4gggg-gggg-444444444444" --scope "/subscriptions/44444444-ffff-43333-444444/resourceGroups/rgailab/providers/Microsoft.DocumentDB/databaseAccounts/cosm"

az cosmosdb sql role assignment list --resource-group "rg" --account-name "cosm"

# Enable local auth for the cosmosdb account
# This is required to use the CLI to create the database and container
# This is a temporary solution until we can use the EntraiDI to create the database and container
az resource update --resource-group "rg" --name "cosm" --resource-type "Microsoft.DocumentDB/databaseAccounts" --set properties.disableLocalAuth=false