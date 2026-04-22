-- STCPe Core - schema PostgreSQL para Supabase
-- Pode ser executado varias vezes sem quebrar (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS routes (
    agency_id TEXT,
    route_id TEXT PRIMARY KEY,
    route_short_name TEXT NOT NULL,
    route_type INTEGER,
    route_long_name TEXT,
    route_url TEXT,
    route_color TEXT,
    route_text_color TEXT,
    route_sort_order INTEGER
);

CREATE TABLE IF NOT EXISTS trips (
    route_id TEXT NOT NULL,
    service_id TEXT,
    trip_id TEXT PRIMARY KEY,
    trip_headsign TEXT,
    wheelchair_accessible INTEGER,
    block_id TEXT,
    direction_id INTEGER,
    shape_id TEXT
);

CREATE TABLE IF NOT EXISTS stops (
    stop_id TEXT PRIMARY KEY,
    stop_code TEXT,
    stop_name TEXT NOT NULL,
    stop_lat DOUBLE PRECISION NOT NULL,
    stop_lon DOUBLE PRECISION NOT NULL,
    zone_id TEXT,
    stop_url TEXT
);

CREATE TABLE IF NOT EXISTS stop_times (
    trip_id TEXT NOT NULL,
    arrival_time TEXT NOT NULL,
    departure_time TEXT NOT NULL,
    stop_id TEXT NOT NULL,
    stop_sequence INTEGER NOT NULL,
    timepoint INTEGER,
    shape_dist_traveled DOUBLE PRECISION,
    PRIMARY KEY (trip_id, stop_sequence)
);

CREATE TABLE IF NOT EXISTS shapes (
    shape_id TEXT NOT NULL,
    shape_pt_lat DOUBLE PRECISION NOT NULL,
    shape_pt_lon DOUBLE PRECISION NOT NULL,
    shape_dist_traveled DOUBLE PRECISION,
    shape_pt_sequence INTEGER NOT NULL,
    PRIMARY KEY (shape_id, shape_pt_sequence)
);

CREATE TABLE IF NOT EXISTS veiculos (
    id_veiculo TEXT PRIMARY KEY,
    linha TEXT NOT NULL,
    sentido TEXT NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    velocidade DOUBLE PRECISION DEFAULT 0,
    bearing DOUBLE PRECISION DEFAULT 0,
    timestamp TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_routes_short_name ON routes (route_short_name);
CREATE INDEX IF NOT EXISTS idx_trips_route_direction ON trips (route_id, direction_id);
CREATE INDEX IF NOT EXISTS idx_trips_shape_id ON trips (shape_id);
CREATE INDEX IF NOT EXISTS idx_stops_name ON stops (stop_name);
CREATE INDEX IF NOT EXISTS idx_stop_times_stop_id ON stop_times (stop_id);
CREATE INDEX IF NOT EXISTS idx_shapes_shape_id ON shapes (shape_id);
CREATE INDEX IF NOT EXISTS idx_veiculos_linha ON veiculos (linha);
CREATE INDEX IF NOT EXISTS idx_veiculos_updated_at ON veiculos (updated_at);
