import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.api.exceptions import InternalServerError, ValidationError
from main import create_app


@pytest.mark.unit
@pytest.mark.fast
class TestExceptionHandlerLogging:
    @pytest.fixture
    def client(self):
        app = create_app(enable_startup_migrations=False)

        @app.get("/test-500")
        async def force_500():
            raise InternalServerError("forced 500 error")

        @app.get("/test-400")
        async def force_400():
            raise ValidationError("forced 400 error")

        return TestClient(app)

    def test_5xx_logs_error(self, client):
        with patch('main.logger') as mock_logger:
            response = client.get("/test-500")

            assert response.status_code == 500

            handler_calls = [
                c for c in mock_logger.error.call_args_list
                if c.args and len(c.args) > 0 and c.args[0] == "sync_server_exception"
            ]
            assert len(handler_calls) == 1
            call = handler_calls[0]

            assert call.kwargs.get("code") == "INTERNAL_SERVER_ERROR"
            assert call.kwargs.get("status_code") == 500
            assert call.kwargs.get("exc_info") is True

    def test_4xx_logs_warning(self, client):
        with patch('main.logger') as mock_logger:
            response = client.get("/test-400")

            assert response.status_code == 400

            handler_calls = [
                c for c in mock_logger.warning.call_args_list
                if c.args and len(c.args) > 0 and c.args[0] == "sync_server_exception"
            ]
            assert len(handler_calls) == 1
            call = handler_calls[0]

            assert call.kwargs.get("code") == "VALIDATION_ERROR"
            assert call.kwargs.get("status_code") == 400
            assert "exc_info" not in call.kwargs

    def test_exception_response_format_preserved(self, client):
        response = client.get("/test-500")

        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert data["error"]["message"] == "forced 500 error"
        assert "details" not in data["error"]

    def test_x_request_id_in_response_when_available(self, client):
        response = client.get("/test-500", headers={"X-Request-Id": "test-req-id-123"})

        assert response.status_code == 500
        data = response.json()
        assert data.get("request_id") == "test-req-id-123"
