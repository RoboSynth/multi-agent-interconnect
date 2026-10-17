CREATE TABLE IF NOT EXISTS orders (
    id uuid PRIMARY KEY,
    request_key text NOT NULL UNIQUE,
    item text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    status text NOT NULL CHECK (status IN ('CREATED', 'CANCELLED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS operation_receipts (
    operation_key text PRIMARY KEY,
    operation_kind text NOT NULL CHECK (operation_kind IN ('create', 'cancel')),
    request_hash text NOT NULL,
    order_id uuid NOT NULL REFERENCES orders(id),
    response jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS operation_receipts_order_idx ON operation_receipts(order_id);
