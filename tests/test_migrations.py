from sqlalchemy import inspect, text

from bid_studio.database import Base, add_missing_columns, build_engine


def test_adds_missing_columns_to_an_older_database_without_touching_data(tmp_path):
    eng = build_engine(f"sqlite:///{tmp_path / 'old.db'}")
    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:
        conn.execute(text("INSERT INTO workspaces (slug, name, brand_name, primary_color, accent_color, support_email, is_white_label, client_isolation_enforced, created_at) VALUES ('w','W','B','#000','#111','a@b.co',0,1,CURRENT_TIMESTAMP)"))
        # simulate an old schema: rebuild a table without one of its columns
        conn.execute(text("ALTER TABLE saved_grants RENAME TO saved_old"))
        conn.execute(text("CREATE TABLE saved_grants (id INTEGER PRIMARY KEY, workspace_id INTEGER, notice_id INTEGER)"))
    assert "created_at" not in {c["name"] for c in inspect(eng).get_columns("saved_grants")}

    added = add_missing_columns(eng)
    assert "saved_grants.created_at" in added
    assert "created_at" in {c["name"] for c in inspect(eng).get_columns("saved_grants")}
    with eng.connect() as conn:
        assert conn.execute(text("SELECT slug FROM workspaces")).scalar() == "w"
    assert add_missing_columns(eng) == []  # idempotent


def test_not_null_columns_get_defaults_so_existing_rows_survive(tmp_path):
    eng = build_engine(f"sqlite:///{tmp_path / 'old2.db'}")
    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:
        conn.execute(text("DROP TABLE writer_profiles"))
        conn.execute(text("CREATE TABLE writer_profiles (id INTEGER PRIMARY KEY, account_id INTEGER, headline VARCHAR(200))"))
        conn.execute(text("INSERT INTO writer_profiles (account_id, headline) VALUES (1, 'Existing writer')"))
    added = add_missing_columns(eng)
    assert "writer_profiles.status" in added and "writer_profiles.day_rate" in added
    with eng.connect() as conn:
        row = conn.execute(text("SELECT headline, status, day_rate, currency, specialisms FROM writer_profiles")).one()
    assert row[0] == "Existing writer" and row[1] == "pending" and row[2] == 0 and row[3] == "GBP" and row[4] == "[]"
