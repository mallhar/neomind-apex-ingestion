-- =============================================================================
-- Apex Ingestion Platform: Initial Database Setup
-- Version: 1.0
-- Description: This single script creates all tables, indexes, extensions,
--              and Row Level Security (RLS) policies for the MVP.
-- =============================================================================

-- Step 1: Enable Required Extensions
-- -----------------------------------------------------------------------------
-- Enable pgvector for semantic search capabilities in the future.
CREATE EXTENSION IF NOT EXISTS vector;


-- Step 2: Create Core Tables
-- -----------------------------------------------------------------------------

-- Stores organizations/workspaces. This is the top-level tenant.
CREATE TABLE public.tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE public.tenants IS 'Top-level tenant entity for multi-tenancy.';

-- Stores individual users who can log in to the Apex platform.
CREATE TABLE public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE public.users IS 'Stores individual user accounts, linked to a tenant.';
CREATE INDEX idx_users_tenant_id ON public.users(tenant_id);

-- Stores encrypted tokens and metadata for all third-party integrations.
-- A tenant_id is denormalized here for efficient RLS policy application.
CREATE TABLE public.integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    provider TEXT NOT NULL, -- e.g., 'google_workspace' or 'microsoft_365'
    encrypted_refresh_token BYTEA NOT NULL,
    contacts_sync_token TEXT,
    status TEXT NOT NULL DEFAULT 'active', -- 'active', 'revoked', 'error'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, provider)
);
COMMENT ON TABLE public.integrations IS 'Stores encrypted credentials and sync state for third-party integrations.';
CREATE INDEX idx_integrations_user_id ON public.integrations(user_id);
CREATE INDEX idx_integrations_tenant_id ON public.integrations(tenant_id);


-- Stores records of individuals known by a tenant (their address book).
CREATE TABLE public.contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    canonical_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE public.contacts IS 'A tenant''s address book of known individuals.';
CREATE INDEX idx_contacts_tenant_id ON public.contacts(tenant_id);

-- Links a single contact to their various identifiers (e.g., email, phone).
CREATE TABLE public.contact_identifiers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID NOT NULL REFERENCES public.contacts(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    identifier_type TEXT NOT NULL, -- 'email', 'phone', etc.
    identifier_value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, identifier_type, identifier_value)
);
COMMENT ON TABLE public.contact_identifiers IS 'Links a contact to their various unique identifiers like email or phone.';
CREATE INDEX idx_contact_identifiers_lookup ON public.contact_identifiers(tenant_id, identifier_type, identifier_value);


-- Step 3: Apply Row Level Security (RLS) Policies
-- -----------------------------------------------------------------------------
-- This provides a critical last line of defense for multi-tenant data isolation.
-- All policies rely on a session variable 'app.current_tenant_id' being set
-- by the application before each transaction.

-- Enable RLS and apply policy for the 'users' table.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "tenant_isolation_policy"
    ON public.users
    FOR ALL
    USING (tenant_id = (current_setting('app.current_tenant_id', true))::UUID);

-- Enable RLS and apply policy for the 'integrations' table.
ALTER TABLE public.integrations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "tenant_isolation_policy"
    ON public.integrations
    FOR ALL
    USING (tenant_id = (current_setting('app.current_tenant_id', true))::UUID);

-- Enable RLS and apply policy for the 'contacts' table.
ALTER TABLE public.contacts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "tenant_isolation_policy"
    ON public.contacts
    FOR ALL
    USING (tenant_id = (current_setting('app.current_tenant_id', true))::UUID);

-- Enable RLS and apply policy for the 'contact_identifiers' table.
ALTER TABLE public.contact_identifiers ENABLE ROW LEVEL SECURITY;
CREATE POLICY "tenant_isolation_policy"
    ON public.contact_identifiers
    FOR ALL
    USING (tenant_id = (current_setting('app.current_tenant_id', true))::UUID);

-- =============================================================================
-- End of Script
-- =============================================================================