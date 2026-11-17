
"""Local development entry point with Mock Agent."""
from backend.app.main import create_app
from backend.services.mock_agent import MockAgentService

app = create_app(agent_service=MockAgentService())
