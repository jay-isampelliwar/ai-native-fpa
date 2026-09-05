-- AI Native Financial Planner - target schema
-- Money is NUMERIC(14,2). Never float, never int paise.
-- Every user-owned table carries user_id and is indexed on it, because every read is ownership-scoped.
-- Primary keys are prefixed TEXT so a key can be quoted directly as an evidence_id.

CREATE TYPE frequency AS ENUM ('monthly', 'quarterly', 'half_yearly', 'annual');
CREATE TYPE sip_status AS ENUM ('active', 'paused', 'stopped');
CREATE TYPE deposit_kind AS ENUM ('fd', 'rd');
CREATE TYPE holding_kind AS ENUM ('stock', 'mutual_fund');
CREATE TYPE approval_status AS ENUM ('pending', 'approved', 'rejected', 'expired');

-- ---------------------------------------------------------------- Phase 2a

CREATE TABLE users (
    id              BIGINT PRIMARY KEY,
    display_name    TEXT        NOT NULL,
    timezone        TEXT        NOT NULL DEFAULT 'Asia/Kolkata',
    currency        TEXT        NOT NULL DEFAULT 'INR',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE income_records (
    id              TEXT PRIMARY KEY,
    user_id         BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    label           TEXT        NOT NULL,
    amount          NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
    frequency       frequency   NOT NULL DEFAULT 'monthly',
    source          TEXT        NOT NULL DEFAULT 'salary',
    active          BOOLEAN     NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON income_records (user_id) WHERE active;

CREATE TABLE expense_records (
    id              TEXT PRIMARY KEY,
    user_id         BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    label           TEXT        NOT NULL,
    amount          NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
    frequency       frequency   NOT NULL DEFAULT 'monthly',
    category        TEXT        NOT NULL DEFAULT 'general',
    active          BOOLEAN     NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON expense_records (user_id) WHERE active;

-- A dated single spend. description arrives from a bank and is untrusted text.
CREATE TABLE expense_transactions (
    id              TEXT PRIMARY KEY,
    user_id         BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    occurred_on     DATE        NOT NULL,
    amount          NUMERIC(14,2) NOT NULL,
    category        TEXT        NOT NULL,
    merchant        TEXT        NOT NULL DEFAULT '',
    description     TEXT        NOT NULL DEFAULT '',
    import_batch_id TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON expense_transactions (user_id, occurred_on DESC);
CREATE INDEX ON expense_transactions (user_id, category, occurred_on DESC);

CREATE TABLE liabilities (
    id                      TEXT PRIMARY KEY,
    user_id                 BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    label                   TEXT        NOT NULL,
    lender                  TEXT        NOT NULL DEFAULT '',
    principal_outstanding   NUMERIC(14,2) NOT NULL CHECK (principal_outstanding >= 0),
    interest_rate_percent   NUMERIC(6,3)  NOT NULL CHECK (interest_rate_percent >= 0),
    tenure_months           INTEGER     NOT NULL CHECK (tenure_months > 0),
    opened_on               DATE,
    active                  BOOLEAN     NOT NULL DEFAULT true,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON liabilities (user_id) WHERE active;

-- Contractual outflow. Separate from expenses because it cannot be paused.
CREATE TABLE emi_records (
    id                      TEXT PRIMARY KEY,
    user_id                 BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    liability_id            TEXT        NOT NULL REFERENCES liabilities(id) ON DELETE CASCADE,
    label                   TEXT        NOT NULL,
    amount                  NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    frequency               frequency   NOT NULL DEFAULT 'monthly',
    interest_rate_percent   NUMERIC(6,3)  NOT NULL,
    remaining_months        INTEGER     NOT NULL CHECK (remaining_months >= 0),
    active                  BOOLEAN     NOT NULL DEFAULT true,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON emi_records (user_id) WHERE active;
CREATE INDEX ON emi_records (liability_id);

-- A standing instruction, not an asset class. Its units live in holdings.
CREATE TABLE sip_records (
    id              TEXT PRIMARY KEY,
    user_id         BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    scheme_name     TEXT        NOT NULL,
    folio_id        TEXT,
    amount          NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    frequency       frequency   NOT NULL DEFAULT 'monthly',
    next_debit_on   DATE,
    status          sip_status  NOT NULL DEFAULT 'active',
    linked_goal_id  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON sip_records (user_id) WHERE status = 'active';

-- ---------------------------------------------------------------- Phase 2b

CREATE TABLE goals (
    id                  TEXT PRIMARY KEY,
    user_id             BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    label               TEXT        NOT NULL,
    kind                TEXT        NOT NULL DEFAULT 'custom',
    target_amount       NUMERIC(14,2) NOT NULL CHECK (target_amount > 0),
    target_date         DATE        NOT NULL,
    priority            SMALLINT    NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    inflation_percent   NUMERIC(6,3) NOT NULL DEFAULT 6.000,
    archived_at         TIMESTAMPTZ,
    created_by_approval TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON goals (user_id) WHERE archived_at IS NULL;

-- A goal LINKS to funding assets. It never copies their balances.
CREATE TABLE goal_fundings (
    id              TEXT PRIMARY KEY,
    user_id         BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    goal_id         TEXT        NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    asset_table     TEXT        NOT NULL CHECK (asset_table IN ('holdings','deposits','sip_records','retirement_assets')),
    asset_id        TEXT        NOT NULL,
    allocation_pct  NUMERIC(5,2) NOT NULL DEFAULT 100.00 CHECK (allocation_pct > 0 AND allocation_pct <= 100),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (goal_id, asset_table, asset_id)
);
CREATE INDEX ON goal_fundings (user_id);

-- FD and RD share a table; kind decides which columns are meaningful.
CREATE TABLE deposits (
    id                      TEXT PRIMARY KEY,
    user_id                 BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    kind                    deposit_kind NOT NULL,
    institution             TEXT        NOT NULL,
    principal               NUMERIC(14,2) CHECK (principal >= 0),
    monthly_contribution    NUMERIC(14,2) CHECK (monthly_contribution >= 0),
    interest_rate_percent   NUMERIC(6,3) NOT NULL,
    compounding             TEXT        NOT NULL DEFAULT 'quarterly',
    opened_on               DATE        NOT NULL,
    matures_on              DATE        NOT NULL,
    active                  BOOLEAN     NOT NULL DEFAULT true,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((kind = 'fd' AND principal IS NOT NULL) OR (kind = 'rd' AND monthly_contribution IS NOT NULL))
);
CREATE INDEX ON deposits (user_id, matures_on) WHERE active;

-- What you own now. Value is derived from a verified price feed, never stored as truth.
CREATE TABLE holdings (
    id                  TEXT PRIMARY KEY,
    user_id             BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    kind                holding_kind NOT NULL,
    instrument_name     TEXT        NOT NULL,
    isin                TEXT,
    scheme_code         TEXT,
    folio_id            TEXT,
    units               NUMERIC(20,6) NOT NULL CHECK (units >= 0),
    average_cost        NUMERIC(14,4) NOT NULL CHECK (average_cost >= 0),
    as_of               DATE        NOT NULL,
    active              BOOLEAN     NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON holdings (user_id) WHERE active;

-- What happened. A holding is the running total of these.
CREATE TABLE investment_transactions (
    id              TEXT PRIMARY KEY,
    user_id         BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    holding_id      TEXT        REFERENCES holdings(id) ON DELETE SET NULL,
    kind            TEXT        NOT NULL CHECK (kind IN ('buy','sell','dividend','redemption','bonus','split')),
    occurred_on     DATE        NOT NULL,
    units           NUMERIC(20,6),
    price_per_unit  NUMERIC(14,4),
    amount          NUMERIC(14,2) NOT NULL,
    sip_id          TEXT        REFERENCES sip_records(id) ON DELETE SET NULL,
    import_batch_id TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON investment_transactions (user_id, occurred_on DESC);
CREATE INDEX ON investment_transactions (holding_id, occurred_on DESC);

CREATE TABLE retirement_assets (
    id                      TEXT PRIMARY KEY,
    user_id                 BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    scheme                  TEXT        NOT NULL CHECK (scheme IN ('epf','ppf','nps','pension','annuity')),
    account_reference       TEXT,
    balance                 NUMERIC(14,2) NOT NULL CHECK (balance >= 0),
    monthly_contribution    NUMERIC(14,2) NOT NULL DEFAULT 0,
    employer_contribution   NUMERIC(14,2) NOT NULL DEFAULT 0,
    interest_rate_percent   NUMERIC(6,3),
    as_of                   DATE        NOT NULL,
    active                  BOOLEAN     NOT NULL DEFAULT true,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON retirement_assets (user_id) WHERE active;

CREATE TABLE insurance_policies (
    id                  TEXT PRIMARY KEY,
    user_id             BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    insurer             TEXT        NOT NULL,
    policy_kind         TEXT        NOT NULL CHECK (policy_kind IN ('term','health','motor','home','endowment','ulip')),
    policy_reference    TEXT,
    cover_amount        NUMERIC(14,2) NOT NULL CHECK (cover_amount >= 0),
    premium_amount      NUMERIC(14,2) NOT NULL CHECK (premium_amount >= 0),
    premium_frequency   frequency   NOT NULL DEFAULT 'annual',
    renews_on           DATE,
    active              BOOLEAN     NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON insurance_policies (user_id, renews_on) WHERE active;

-- ---------------------------------------------------------- Cross-cutting

-- Append-only. No UPDATE, no DELETE. IDs and versions only, never balances or narratives.
CREATE TABLE audit_records (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    correlation_id      TEXT        NOT NULL,
    user_id             BIGINT      NOT NULL,
    conversation_id     TEXT        NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    skill_name          TEXT,
    skill_version       TEXT,
    prompt_version      TEXT,
    model_name          TEXT,
    route_confidence    NUMERIC(4,3),
    route_reason        TEXT,
    permission_granted  BOOLEAN     NOT NULL DEFAULT false,
    denial_reason       TEXT,
    result_status       TEXT,
    evidence_ids        TEXT[]      NOT NULL DEFAULT '{}',
    calculator_versions TEXT[]      NOT NULL DEFAULT '{}',
    assumptions         JSONB       NOT NULL DEFAULT '{}',
    validation_errors   TEXT[]      NOT NULL DEFAULT '{}',
    approval_id         TEXT,
    approval_decision   TEXT,
    write_performed     BOOLEAN     NOT NULL DEFAULT false
);
CREATE INDEX ON audit_records (user_id, recorded_at DESC);
CREATE INDEX ON audit_records (correlation_id);

-- The proposed change a paused graph is waiting on. before/after are what the user was shown.
CREATE TABLE pending_approvals (
    id                  TEXT PRIMARY KEY,
    user_id             BIGINT      NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    conversation_id     TEXT        NOT NULL,
    correlation_id      TEXT        NOT NULL,
    skill_name          TEXT        NOT NULL,
    skill_version       TEXT        NOT NULL,
    action_kind         TEXT        NOT NULL,
    target_table        TEXT,
    target_id           TEXT,
    before_state        JSONB,
    after_state         JSONB       NOT NULL,
    evidence_ids        TEXT[]      NOT NULL DEFAULT '{}',
    status              approval_status NOT NULL DEFAULT 'pending',
    idempotency_key     TEXT        NOT NULL UNIQUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at          TIMESTAMPTZ NOT NULL,
    decided_at          TIMESTAMPTZ,
    decided_by_user_id  BIGINT
);
CREATE INDEX ON pending_approvals (user_id, status);
CREATE INDEX ON pending_approvals (conversation_id) WHERE status = 'pending';
