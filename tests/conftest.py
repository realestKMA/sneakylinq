import uuid
from datetime import datetime, timedelta

import pytest
from pytest import MonkeyPatch

from chat.lua_scripts import LuaScripts
from src.utils import redis_client
from tests.mocks import MockLuaScript, MockRedisClient


@pytest.fixture(autouse=True)
def use_in_memory_channel_layer(settings):
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }


@pytest.fixture(autouse=True)
def reset_redis_instance_db():
    return MockRedisClient.reset()


@pytest.fixture
def mock_redis_hset(monkeypatch: MonkeyPatch):
    monkeypatch.setattr(redis_client, "hset", MockRedisClient.hset)


@pytest.fixture
def mock_redis_hget(monkeypatch: MonkeyPatch):
    monkeypatch.setattr(redis_client, "hget", MockRedisClient.hget)


@pytest.fixture
def mock_redis_hvals(monkeypatch: MonkeyPatch):
    monkeypatch.setattr(redis_client, "hvals", MockRedisClient.hvals)


@pytest.fixture
def mock_redis_hdel(monkeypatch: MonkeyPatch):
    monkeypatch.setattr(redis_client, "hdel", MockRedisClient.hdel)


@pytest.fixture
def mock_redis_delete(monkeypatch: MonkeyPatch):
    monkeypatch.setattr(redis_client, "delete", MockRedisClient.delete)


@pytest.fixture
def mock_redis_expireat(monkeypatch: MonkeyPatch):
    monkeypatch.setattr(redis_client, "expireat", MockRedisClient.expireat)


@pytest.fixture
def device_data():
    return (
        {
            "did": str(uuid.uuid4()),
            "channel": "channel-001",
            "ttl": (datetime.now() + timedelta(hours=2)).timestamp(),
            "alias": "testalias",
        },
    )[0]


@pytest.fixture
def mock_luascript_set_alias_device(monkeypatch: MonkeyPatch):
    monkeypatch.setattr(LuaScripts, "set_alias_device", MockLuaScript.set_alias_device)


@pytest.fixture
def mock_luascript_get_device_data(monkeypatch: MonkeyPatch):
    monkeypatch.setattr(LuaScripts, "get_device_data", MockLuaScript.get_device_data)
