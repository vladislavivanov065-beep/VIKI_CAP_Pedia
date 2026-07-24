class AssistantNotConfiguredError(Exception):
    """OPENAI_API_KEY isn't set -- the feature is deliberately optional."""


class AssistantDisabledError(Exception):
    """An administrator turned the feature off site-wide."""


class AssistantRequestError(Exception):
    """The OpenAI API call itself failed (network, auth, rate limit, ...)."""
