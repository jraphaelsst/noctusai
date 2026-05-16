#!/usr/bin/env python3
"""Apply the product's local SQLite development schema.

The canonical production migrations remain the SQL files in migrations/
for Supabase/Postgres. This script creates the equivalent local tables
for DATABASE_BACKEND=sqlite so Phase 5 can be developed without touching
Supabase.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


DEFAULT_DB = Path(__file__).resolve().parents[3] / "tmp" / "dev.sqlite3"


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS status_pagina (
    id TEXT PRIMARY KEY,
    nome_pagina TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'producao',
    descricao TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS invitations (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    invited_by TEXT NOT NULL,
    token TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    expires_at TEXT NOT NULL DEFAULT (datetime('now', '+7 days')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS credentials (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    encrypted_tokens TEXT NOT NULL,
    channel_id TEXT,
    channel_title TEXT,
    scopes TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(org_id, provider)
);

CREATE TABLE IF NOT EXISTS upload_jobs (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    youtube_video_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    privacy_status TEXT NOT NULL DEFAULT 'private',
    category_id TEXT NOT NULL DEFAULT '22',
    source_type TEXT NOT NULL,
    source_url TEXT,
    file_name TEXT NOT NULL,
    file_size_bytes INTEGER,
    status TEXT NOT NULL DEFAULT 'queued',
    progress_percent INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    notify_recipients TEXT NOT NULL DEFAULT '[]',
    created_by TEXT,
    product_code TEXT,
    thumbnail_url TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS video_cache (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    youtube_video_id TEXT NOT NULL,
    title TEXT,
    description TEXT,
    thumbnail_url TEXT,
    published_at TEXT,
    duration TEXT,
    privacy_status TEXT,
    view_count INTEGER NOT NULL DEFAULT 0,
    like_count INTEGER NOT NULL DEFAULT 0,
    comment_count INTEGER NOT NULL DEFAULT 0,
    favorite_count INTEGER NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]',
    category_id TEXT,
    uploaded_via_app INTEGER NOT NULL DEFAULT 0,
    synced_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(org_id, youtube_video_id)
);

CREATE TABLE IF NOT EXISTS notification_recipients (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    whatsapp_number TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (email IS NOT NULL OR whatsapp_number IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS notification_log (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    upload_job_id TEXT REFERENCES upload_jobs(id) ON DELETE CASCADE,
    recipient_id TEXT REFERENCES notification_recipients(id) ON DELETE SET NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    sent_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    raw_sender TEXT,
    direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    -- SQLite treats multiple NULLs as distinct (per the SQL standard) so
    -- the UNIQUE constraint on a nullable column correctly relaxes when
    -- the outbound surface doesn't know the id at insert time.
    provider_message_id TEXT UNIQUE,
    body TEXT NOT NULL,
    authorized INTEGER NOT NULL DEFAULT 0,
    structured_payload TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS waha_response_samples (
    id TEXT PRIMARY KEY,
    sample_key TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    direction TEXT NOT NULL,
    event_type TEXT,
    http_status INTEGER,
    schema_fingerprint TEXT NOT NULL,
    schema_shape TEXT NOT NULL,
    sample_json TEXT NOT NULL,
    handling_notes TEXT,
    observed_count INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_social_wiring_invitations_org ON invitations(org_id);
CREATE INDEX IF NOT EXISTS idx_social_wiring_invitations_token ON invitations(token);
CREATE INDEX IF NOT EXISTS idx_social_wiring_credentials_org ON credentials(org_id);
CREATE INDEX IF NOT EXISTS idx_social_wiring_credentials_provider ON credentials(provider);
CREATE INDEX IF NOT EXISTS idx_yt_upload_jobs_org ON upload_jobs(org_id);
CREATE INDEX IF NOT EXISTS idx_yt_upload_jobs_status ON upload_jobs(org_id, status);
CREATE INDEX IF NOT EXISTS idx_yt_upload_jobs_created ON upload_jobs(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_yt_upload_jobs_product_code ON upload_jobs(org_id, product_code);
CREATE INDEX IF NOT EXISTS idx_yt_video_cache_org ON video_cache(org_id);
CREATE INDEX IF NOT EXISTS idx_yt_video_cache_published ON video_cache(org_id, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_yt_video_cache_uploaded_via_app ON video_cache(org_id, uploaded_via_app);
CREATE INDEX IF NOT EXISTS idx_yt_video_cache_synced ON video_cache(org_id, synced_at DESC);
CREATE INDEX IF NOT EXISTS idx_yt_notification_recipients_org ON notification_recipients(org_id);
CREATE INDEX IF NOT EXISTS idx_yt_notification_recipients_active ON notification_recipients(org_id, is_active);
CREATE INDEX IF NOT EXISTS idx_yt_notification_log_org ON notification_log(org_id);
CREATE INDEX IF NOT EXISTS idx_yt_notification_log_job ON notification_log(upload_job_id);
CREATE INDEX IF NOT EXISTS idx_yt_notification_log_recipient ON notification_log(recipient_id);
CREATE INDEX IF NOT EXISTS idx_yt_conversation_messages_session ON conversation_messages(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_yt_conversation_messages_org_session ON conversation_messages(org_id, session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_yt_conversation_messages_direction ON conversation_messages(direction);
CREATE INDEX IF NOT EXISTS idx_yt_waha_response_samples_source ON waha_response_samples(source);
CREATE INDEX IF NOT EXISTS idx_yt_waha_response_samples_event ON waha_response_samples(event_type);
CREATE INDEX IF NOT EXISTS idx_yt_waha_response_samples_last_seen ON waha_response_samples(last_seen_at DESC);

INSERT OR IGNORE INTO status_pagina (id, nome_pagina, status) VALUES
    ('page-dashboard', 'dashboard', 'producao'),
    ('page-equipe', 'equipe', 'producao'),
    ('page-configuracoes', 'configuracoes', 'producao'),
    ('page-upload', 'upload', 'producao'),
    ('page-videos', 'videos', 'producao');
"""


def main() -> None:
    db_path = Path(os.environ.get("SQLITE_PATH") or DEFAULT_DB)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
    print(f"Applied SQLite dev schema to {db_path}")


if __name__ == "__main__":
    main()
