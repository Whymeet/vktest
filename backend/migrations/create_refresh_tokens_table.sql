-- Migration: Add refresh_tokens table for JWT authentication
-- Created: 2025-12-21
-- Description: Stores active refresh tokens with device info and revocation support

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Token identification
    token_hash VARCHAR(255) NOT NULL UNIQUE,  -- SHA256 hash of the refresh token
    jti VARCHAR(36) NOT NULL UNIQUE,          -- JWT ID (UUID v4)

    -- Device/Session info
    user_agent VARCHAR(500),
    ip_address VARCHAR(45),                   -- IPv6 max length
    device_name VARCHAR(255),

    -- Token validity
    expires_at TIMESTAMP NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at TIMESTAMP,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_token_hash ON refresh_tokens(token_hash);
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_jti ON refresh_tokens(jti);
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_expires_at ON refresh_tokens(expires_at);
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_revoked ON refresh_tokens(revoked);
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_active ON refresh_tokens(user_id, revoked, expires_at);

-- Comments for documentation
COMMENT ON TABLE refresh_tokens IS 'Stores active refresh tokens for JWT authentication with device tracking and revocation support';
COMMENT ON COLUMN refresh_tokens.token_hash IS 'SHA256 hash of the refresh token for secure storage';
COMMENT ON COLUMN refresh_tokens.jti IS 'Unique JWT ID (UUID) to identify the token';
COMMENT ON COLUMN refresh_tokens.revoked IS 'If true, the token has been revoked and cannot be used';
COMMENT ON COLUMN refresh_tokens.last_used_at IS 'Updated every time the token is used to refresh access token';
