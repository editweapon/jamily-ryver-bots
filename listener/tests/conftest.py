import pytest
from ryver_connector import RyverConfig

@pytest.fixture
def cfg():
    return RyverConfig(org="acme", username="bot", password="pw")
