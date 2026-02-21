
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from open_webui.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def mock_redis():
    mock = MagicMock()
    app.state.redis = mock
    yield mock
    app.state.redis = None

def test_get_load_stats_empty(client, mock_redis):
    """
    Test that /api/load-stats returns empty or zero stats when no jobs are running.
    """
    app.state.config.OLLAMA_BASE_URLS = ["http://localhost:11434"]
    
    # Mock redis get to return None (no active jobs)
    mock_redis.get.return_value = None
    
    response = client.get("/api/load-stats")
    
    # Needs to be implemented first, so we expect 404 now, but eventually 200
    # For TDD, we assert what we WANT.
    assert response.status_code == 200
    assert response.json() == {"http://localhost:11434": 0}

@patch("open_webui.routers.ollama.send_post_request")
def test_active_job_tracking_increment_decrement(mock_send_post, client, mock_redis):
    """
    Test that active job count increments before request and decrements after.
    We'll simulate this by mocking send_post_request and checking side effects if possible,
    or better, we inspect the implementation of the router wrapper.
    However, since we are testing endpoints, we trigger a generation.
    """
    app.state.config.OLLAMA_BASE_URLS = ["http://localhost:11434"]
    
    # Mock send_post_request to just return a simple valid response
    mock_send_post.return_value = {"response": "mocked"}
    
    # We need to verify that during the execution of the request, Redis was called.
    # Since we can't easily "pause" the request in a unit test without complex async locking,
    # we will rely on checking if redis.incr and redis.decr/incrby(-1) were called.
    
    response = client.post(
        "/ollama/api/generate",
        json={"model": "test-model", "prompt": "hello"},
        headers={"Authorization": "Bearer test-token"}
    )
    
    # Note: Authorization might fail if we don't mock user. 
    # For TDD simplicity, let's assume we bypass auth or provides valid mocked auth.
    # If this fails due to auth, we'll fix the test setup.
    
    # Verify Redis calls
    # Expect incr active_jobs:http://localhost:11434
    # Expect decr active_jobs:http://localhost:11434
    
    # This assertion might fail now because the code isn't there.
    assert mock_redis.incr.called
    assert mock_redis.decr.called
