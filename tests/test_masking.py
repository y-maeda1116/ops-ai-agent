"""mask_sensitive（機密情報マスキング）のテスト。"""

from ops_ai_agent.domain.masking import mask_sensitive


def test_masks_aws_access_key():
    text = "failed with key AKIAIOSFODNN7EXAMPLE in us-east-1"
    masked = mask_sensitive(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in masked
    assert "***MASKED***" in masked


def test_masks_jwt():
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    masked = mask_sensitive(f"auth header: {jwt}")
    assert jwt not in masked


def test_masks_slack_token():
    masked = mask_sensitive("token=xoxb-fixture-not-a-real-token")
    assert "xoxb-" not in masked.replace("***MASKED***", "")


def test_masks_bearer_token():
    masked = mask_sensitive("Authorization: Bearer sk-abc123def456")
    assert "sk-abc123def456" not in masked
    assert "Bearer" in masked


def test_masks_private_key_block():
    text = (
        "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg\nmore\nlines\n"
        "-----END PRIVATE KEY-----"
    )
    masked = mask_sensitive(f"config: {text}")
    assert "MIIEvQIBADANBg" not in masked


def test_masks_email():
    masked = mask_sensitive("notify user.taro@example.co.jp about it")
    assert "user.taro@example.co.jp" not in masked


def test_masks_cred_query_params():
    masked = mask_sensitive("GET /api?password=s3cret&api_key=xyz123&page=2")
    assert "s3cret" not in masked
    assert "xyz123" not in masked
    assert "page=2" in masked  # 通常パラメータは残す


def test_plain_text_untouched():
    text = "2026-10-03 ERROR api-gateway upstream timeout after 30s"
    assert mask_sensitive(text) == text


def test_multiple_secrets_all_masked():
    text = "AKIAIOSFODNN7EXAMPLE and user@example.com leaked"
    masked = mask_sensitive(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in masked
    assert "user@example.com" not in masked
