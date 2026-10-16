import pytest

from journey_api.errors import ApiError
from journey_api.phone_auth_routes import (
    hash_password,
    normalized_phone,
    validate_password,
    verify_password,
)


def test_password_hash_is_salted_and_verifiable() -> None:
    first_salt, first_hash = hash_password("test1234")
    second_salt, second_hash = hash_password("test1234")
    assert first_salt != second_salt
    assert first_hash != second_hash
    assert verify_password("test1234", first_salt, first_hash)
    assert not verify_password("wrong1234", first_salt, first_hash)


@pytest.mark.parametrize("value", ["", "12345", "has space", "a" * 12])
def test_invalid_password_is_rejected(value: str) -> None:
    with pytest.raises(ApiError) as caught:
        validate_password(value)
    assert caught.value.code == "PASSWORD_INVALID"


@pytest.mark.parametrize("value", ["123456", "a" * 11])
def test_password_accepts_six_to_eleven_characters(value: str) -> None:
    assert validate_password(value) == value


def test_phone_used_as_temporary_identity_is_normalized() -> None:
    assert normalized_phone("+86 138-0013-8000") == "13800138000"
