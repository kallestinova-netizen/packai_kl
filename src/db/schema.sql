CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    url TEXT UNIQUE,
    source TEXT,
    summary TEXT,
    score INTEGER DEFAULT 0,
    generated_linkedin TEXT,
    generated_telegram TEXT,
    generated_threads TEXT,
    generated_blog TEXT,
    status TEXT DEFAULT 'new',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_number INTEGER,
    scheduled_date DATE,
    title TEXT,
    full_text TEXT,
    rubric TEXT,
    status TEXT DEFAULT 'ready',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS generated_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT,
    source_id INTEGER,
    rubric TEXT,
    format TEXT,
    text TEXT,
    status TEXT DEFAULT 'draft',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT,
    command TEXT,
    details TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS config_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT,
    action TEXT,
    old_value TEXT,
    new_value TEXT,
    confirmed BOOLEAN DEFAULT FALSE,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
