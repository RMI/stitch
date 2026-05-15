# stitch-llm

FastAPI companion service for generating validated LLM suggestions for missing
Stitch oil and gas field values.

The service calls the Stitch API through `stitch-client`, uses configured
bearer auth for downstream API access, and calls Azure OpenAI Responses API for
structured field suggestions.
