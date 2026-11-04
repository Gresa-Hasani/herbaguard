"""AI evidence assistant (Phase 5): retrieval, local LLM client, guardrails, citation validation.

The pure modules (``text``, ``guardrails``, ``fusion``, ``prompting``, ``citations``,
``extractive``, ``evaluation``) import nothing from the database or HTTP layers, so the rules that
keep answers grounded can be tested without PostgreSQL or Ollama.
"""
