from app.core.security import hash_password, verify_password


def test_password_hashing():
    raw = "StrongPassword@123"
    hashed = hash_password(raw)
    assert hashed != raw
    assert verify_password(raw, hashed)
    assert not verify_password("wrong", hashed)
