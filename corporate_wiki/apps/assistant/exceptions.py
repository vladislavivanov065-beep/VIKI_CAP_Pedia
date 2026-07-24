class AssistantNotConfiguredError(Exception):
    """OPENAI_API_KEY isn't set -- the feature is deliberately optional."""


class AssistantRequestError(Exception):
    """The OpenAI API call itself failed (network, auth, rate limit, ...)."""
