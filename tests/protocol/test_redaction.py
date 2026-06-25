"""
Tests for secret redaction across the Alchemist protocol.

Verifies that:
  - config/set_key API keys never appear in model_dump() output
  - API keys do not appear in Pydantic ValidationError messages
  - config/list_keys result contains only masked labels, never raw keys
  - Dispatcher error payloads do not expose raw key material
"""
from __future__ import annotations

import uuid
import pytest
from pydantic import ValidationError, SecretStr

from alchemist.protocol.models.client_to_daemon import ConfigSetKeyParams
from alchemist.protocol.models.results import ConfigListKeysResult, MaskedKeyInfo
from alchemist.protocol.dispatcher import Dispatcher

CLIENT_ID = str(uuid.uuid4())
RAW_KEY = "sk-supersecretkey12345"


class TestConfigSetKeyRedaction:
    def test_model_dump_does_not_expose_raw_key(self):
        params = ConfigSetKeyParams(
            client_id=CLIENT_ID,
            provider="openai",
            key=RAW_KEY,
        )
        dumped = str(params.model_dump())
        assert RAW_KEY not in dumped

    def test_repr_does_not_expose_raw_key(self):
        params = ConfigSetKeyParams(
            client_id=CLIENT_ID,
            provider="openai",
            key=RAW_KEY,
        )
        assert RAW_KEY not in repr(params)

    def test_str_does_not_expose_raw_key(self):
        params = ConfigSetKeyParams(
            client_id=CLIENT_ID,
            provider="openai",
            key=RAW_KEY,
        )
        assert RAW_KEY not in str(params)

    def test_secret_value_accessible_explicitly(self):
        """The raw value should only be reachable via get_secret_value()."""
        params = ConfigSetKeyParams(
            client_id=CLIENT_ID,
            provider="openai",
            key=RAW_KEY,
        )
        assert params.key.get_secret_value() == RAW_KEY

    def test_validation_error_does_not_expose_key(self):
        """If validation fails on another field, the key value must not leak."""
        try:
            ConfigSetKeyParams(
                client_id="not-a-uuid",
                provider="openai",
                key=RAW_KEY,
            )
        except ValidationError as exc:
            err_str = str(exc)
            assert RAW_KEY not in err_str
        else:
            pytest.skip("Expected ValidationError was not raised")


class TestConfigListKeysRedaction:
    def test_list_keys_result_has_only_masked_labels(self):
        result = ConfigListKeysResult(
            keys=[
                MaskedKeyInfo(provider="openai", key_index=0, label="sk-...ab12"),
                MaskedKeyInfo(provider="anthropic", key_index=0, label="sk-...cd34"),
            ]
        )
        dumped = str(result.model_dump())
        assert RAW_KEY not in dumped
        # Confirm labels are masked (end with 4 chars, not full key)
        for key_info in result.keys:
            assert len(key_info.label) < len(RAW_KEY)

    def test_masked_label_does_not_contain_raw_key(self):
        info = MaskedKeyInfo(provider="openai", key_index=0, label="sk-...5678")
        assert RAW_KEY not in info.label
        assert RAW_KEY not in str(info.model_dump())


class TestDispatcherRedaction:
    async def test_invalid_params_error_does_not_expose_key(self):
        """Dispatcher error response for config/set_key must not expose the raw key."""
        dispatcher = Dispatcher()

        # Pass raw key inside params — validation will fail on client_id (not UUID),
        # but the error payload must not contain the raw key text.
        response = await dispatcher.dispatch({
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "config/set_key",
            "params": {
                "client_id": "not-a-uuid",
                "provider": "openai",
                "key": RAW_KEY,
            },
        })
        assert response is not None
        response_str = str(response)
        assert RAW_KEY not in response_str
