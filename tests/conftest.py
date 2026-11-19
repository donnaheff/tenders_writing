import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from bid_studio.database import Base, build_engine, get_db
from bid_studio.main import create_app
from bid_studio.seed import seed_database


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_bid_studio.db"
    test_url = f"sqlite:///{db_path}"
    test_engine = build_engine(test_url)
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine, future=True
    )

    Base.metadata.create_all(bind=test_engine)
    with TestingSessionLocal() as db:
        seed_database(db)

    # Prevent startup lifespan from writing to repo root bid_studio.db
    monkeypatch.setattr("bid_studio.main.engine", test_engine)
    monkeypatch.setattr("bid_studio.main.SessionLocal", TestingSessionLocal)

    app = create_app()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client
