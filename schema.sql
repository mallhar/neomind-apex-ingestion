-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Stores organizations/workspaces. The top-level tenant.
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Stores individuals who can log in to Apex.
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_users_tenant_id ON users(tenant_id);

-- Stores encrypted tokens for all integrations linked to a user.
CREATE TABLE integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL, -- 'google_workspace' or 'microsoft_365'
    encrypted_refresh_token BYTEA NOT NULL,
    -- For storing sync tokens for delta queries.
    contacts_sync_token TEXT,
    status TEXT NOT NULL DEFAULT 'active', -- 'active', 'revoked', 'error'
    UNIQUE(user_id, provider)
);
CREATE INDEX idx_integrations_user_id ON integrations(user_id);

-- Stores records of individuals known by a tenant.
CREATE TABLE contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    canonical_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_contacts_tenant_id ON contacts(tenant_id);

-- Links a single contact to their various identifiers (email, Slack ID, etc.).
CREATE TABLE contact_identifiers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    identifier_type TEXT NOT NULL, -- 'email', 'phone'
    identifier_value TEXT NOT NULL,
    UNIQUE(tenant_id, identifier_type, identifier_value)
);
CREATE INDEX idx_contact_identifiers_lookup ON contact_identifiers(tenant_id, identifier_type, identifier_value);