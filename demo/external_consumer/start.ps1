param(
    [int]$Port = 3000,
    [string]$UpstreamApi = "http://127.0.0.1:8080"
)

$env:AGENT_MATERIAL_API_BASE_URL = $UpstreamApi
conda run -n agno-assist python -m uvicorn demo.external_consumer.app:app --host 127.0.0.1 --port $Port
