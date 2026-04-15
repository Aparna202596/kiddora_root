# ============================================================================
# KIDDORA — AZURE DEPLOYMENT GUIDE
# Architecture: Azure App Service + PostgreSQL Flexible Server + Redis Cache
#               + Azure Front Door (reverse proxy + load balancing + CDN)
# ============================================================================

# ─────────────────────────────────────────────── PREREQUISITES ───────────────
# Install Azure CLI:  https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
# Login:
#   az login
# Set subscription:
#   az account set --subscription "your-subscription-id"


# ─────────────────────────────────────────────── STEP 1: RESOURCE GROUP ──────
az group create \
  --name kiddora-prod-rg \
  --location uaenorth


# ─────────────────────────────────────────────── STEP 2: AZURE CONTAINER REGISTRY ──
az acr create \
  --resource-group kiddora-prod-rg \
  --name kiddoraregistry \
  --sku Basic \
  --admin-enabled true

# Get credentials
az acr credential show --name kiddoraregistry


# ─────────────────────────────────────────────── STEP 3: BUILD & PUSH IMAGE ──
# From kiddora_root/ on your machine:
az acr build \
  --registry kiddoraregistry \
  --image kiddora:latest \
  --file Dockerfile \
  .


# ─────────────────────────────────────────────── STEP 4: POSTGRESQL ──────────
az postgres flexible-server create \
  --resource-group kiddora-prod-rg \
  --name kiddora-db-server \
  --location uaenorth \
  --admin-user kiddoraadmin \
  --admin-password "YourSecurePassword123!" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 16 \
  --public-access 0.0.0.0

az postgres flexible-server db create \
  --resource-group kiddora-prod-rg \
  --server-name kiddora-db-server \
  --database-name kiddora_db


# ─────────────────────────────────────────────── STEP 5: REDIS CACHE ─────────
az redis create \
  --resource-group kiddora-prod-rg \
  --name kiddora-redis \
  --location uaenorth \
  --sku Basic \
  --vm-size c0

# Get connection string
az redis list-keys \
  --resource-group kiddora-prod-rg \
  --name kiddora-redis


# ─────────────────────────────────────────────── STEP 6: APP SERVICE PLAN ────
az appservice plan create \
  --resource-group kiddora-prod-rg \
  --name kiddora-plan \
  --is-linux \
  --sku B2 \
  --location uaenorth


# ─────────────────────────────────────────────── STEP 7: WEB APP (Docker) ────
az webapp create \
  --resource-group kiddora-prod-rg \
  --plan kiddora-plan \
  --name kiddora-web \
  --deployment-container-image-name kiddoraregistry.azurecr.io/kiddora:latest

# Link ACR
az webapp config container set \
  --resource-group kiddora-prod-rg \
  --name kiddora-web \
  --docker-custom-image-name kiddoraregistry.azurecr.io/kiddora:latest \
  --docker-registry-server-url https://kiddoraregistry.azurecr.io \
  --docker-registry-server-user kiddoraregistry \
  --docker-registry-server-password "$(az acr credential show --name kiddoraregistry --query passwords[0].value -o tsv)"


# ─────────────────────────────────────────────── STEP 8: APP SETTINGS (env vars) ──
az webapp config appsettings set \
  --resource-group kiddora-prod-rg \
  --name kiddora-web \
  --settings \
    DEBUG="False" \
    SECRET_KEY="your-production-secret-key-here" \
    ALLOWED_HOSTS="kiddora-web.azurewebsites.net,kiddora.com" \
    DB_NAME="kiddora_db" \
    DB_USER="kiddoraadmin" \
    DB_PASSWORD="YourSecurePassword123!" \
    DB_HOST="kiddora-db-server.postgres.database.azure.com" \
    DB_PORT="5432" \
    CLOUDINARY_CLOUD_NAME="your-cloud-name" \
    CLOUDINARY_API_KEY="your-api-key" \
    CLOUDINARY_API_SECRET="your-api-secret" \
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend" \
    EMAIL_HOST="smtp.gmail.com" \
    EMAIL_PORT="587" \
    EMAIL_USE_TLS="True" \
    EMAIL_HOST_USER="your@email.com" \
    EMAIL_HOST_PASSWORD="your-email-password" \
    DEFAULT_FROM_EMAIL="noreply@kiddora.com" \
    PAYPAL_CLIENT_ID="your-paypal-client-id" \
    PAYPAL_CLIENT_SECRET="your-paypal-secret" \
    PAYPAL_RETURN_URL="https://kiddora-web.azurewebsites.net/payments/paypal/callback/" \
    PAYPAL_CANCEL_URL="https://kiddora-web.azurewebsites.net/shop/cart/" \
    REDIS_URL="rediss://:your-redis-key@kiddora-redis.redis.cache.windows.net:6380/0" \
    WEBSITES_PORT="8000"


# ─────────────────────────────────────────────── STEP 9: AZURE FRONT DOOR ────
# Front Door acts as: CDN + Reverse Proxy + Load Balancer + WAF
# (Replaces Nginx for Azure-hosted apps)

az afd profile create \
  --resource-group kiddora-prod-rg \
  --profile-name kiddora-frontdoor \
  --sku Standard_AzureFrontDoor

az afd endpoint create \
  --resource-group kiddora-prod-rg \
  --profile-name kiddora-frontdoor \
  --endpoint-name kiddora

az afd origin-group create \
  --resource-group kiddora-prod-rg \
  --profile-name kiddora-frontdoor \
  --origin-group-name kiddora-origins \
  --probe-request-type GET \
  --probe-protocol Http \
  --probe-interval-in-seconds 30 \
  --probe-path "/shop/" \
  --sample-size 4 \
  --successful-samples-required 3

az afd origin create \
  --resource-group kiddora-prod-rg \
  --profile-name kiddora-frontdoor \
  --origin-group-name kiddora-origins \
  --origin-name kiddora-web-origin \
  --host-name kiddora-web.azurewebsites.net \
  --origin-host-header kiddora-web.azurewebsites.net \
  --http-port 80 \
  --https-port 443 \
  --priority 1 \
  --weight 1000

az afd route create \
  --resource-group kiddora-prod-rg \
  --profile-name kiddora-frontdoor \
  --endpoint-name kiddora \
  --route-name kiddora-route \
  --origin-group kiddora-origins \
  --supported-protocols Http Https \
  --https-redirect Enabled \
  --patterns-to-match "/*"

# Static files caching rule (cache /static/ for 1 day)
az afd rule-set create \
  --resource-group kiddora-prod-rg \
  --profile-name kiddora-frontdoor \
  --rule-set-name CachingRules

az afd rule create \
  --resource-group kiddora-prod-rg \
  --profile-name kiddora-frontdoor \
  --rule-set-name CachingRules \
  --rule-name StaticCache \
  --order 1 \
  --match-variable RequestUri \
  --operator BeginsWith \
  --match-values "/static/" \
  --action-name RouteConfigurationOverride \
  --cache-duration "1.00:00:00" \
  --query-string-caching-behavior IgnoreQueryString


# ─────────────────────────────────────────────── STEP 10: AUTO-SCALING ───────
az monitor autoscale create \
  --resource-group kiddora-prod-rg \
  --resource kiddora-plan \
  --resource-type Microsoft.Web/serverfarms \
  --name kiddora-autoscale \
  --min-count 1 \
  --max-count 3 \
  --count 1

az monitor autoscale rule create \
  --resource-group kiddora-prod-rg \
  --autoscale-name kiddora-autoscale \
  --condition "CpuPercentage > 70 avg 5m" \
  --scale out 1

az monitor autoscale rule create \
  --resource-group kiddora-prod-rg \
  --autoscale-name kiddora-autoscale \
  --condition "CpuPercentage < 30 avg 10m" \
  --scale in 1


# ─────────────────────────────────────────────── STEP 11: ENABLE CI/CD ───────
# Auto-deploy on push to main branch
az webapp deployment source config \
  --resource-group kiddora-prod-rg \
  --name kiddora-web \
  --repo-url "https://github.com/yourusername/kiddora" \
  --branch main \
  --git-token "your-github-token"

# OR: manual redeploy after push to ACR
az acr build --registry kiddoraregistry --image kiddora:latest .
az webapp restart --resource-group kiddora-prod-rg --name kiddora-web