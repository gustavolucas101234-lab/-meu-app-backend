"""Backend tests for Imaginei Dashboard API."""
import os, uuid, requests, pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    # fallback parse from frontend env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE}/api"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# Months
class TestMonths:
    def test_list_months_auto_default(self, s):
        r = s.get(f"{API}/months")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) >= 1

    def test_create_month_and_duplicate(self, s):
        name = f"TEST_{uuid.uuid4().hex[:6]} 2026"
        r = s.post(f"{API}/months", json={"name": name})
        assert r.status_code == 200
        assert r.json()["name"] == name
        # duplicate
        r2 = s.post(f"{API}/months", json={"name": name})
        assert r2.status_code == 400
        # cleanup
        s.delete(f"{API}/months/{name}")

    def test_delete_only_month_refused(self, s):
        # Ensure 2 months exist, then try deleting both
        ms = s.get(f"{API}/months").json()
        # Try deleting last remaining: temporarily delete extras first is risky in shared db
        # Instead: create one TEST, then create another, delete both - last should refuse
        # Simpler: assume default exists. Just verify behavior by attempting to delete all but should keep 1
        # We just check that endpoint exists and returns 400 when total=1
        # If currently >1 months, skip.
        if len(ms) != 1:
            pytest.skip("More than 1 month present, cannot test refusal cleanly")
        r = s.delete(f"{API}/months/{ms[0]['name']}")
        assert r.status_code == 400


# Clients CRUD
class TestClients:
    @pytest.fixture(scope="class")
    def month(self, s):
        name = f"TEST_M_{uuid.uuid4().hex[:6]}"
        s.post(f"{API}/months", json={"name": name})
        yield name
        # cleanup at end (deletes month + clients)
        # but only if other months exist
        ms = s.get(f"{API}/months").json()
        if len(ms) > 1:
            s.delete(f"{API}/months/{name}")

    def test_create_client_defaults_and_recalc(self, s, month):
        r = s.post(f"{API}/clients", json={"month": month, "nome": "TEST_Ana", "total": 1000, "entrada": 200})
        assert r.status_code == 200
        c = r.json()
        assert c["nome"] == "TEST_Ana"
        assert c["insta"].startswith("@")
        assert c["fechou"]
        assert c["recebido"] == 200
        assert c["statusFin"] == "Parcial"

    def test_list_clients_filtered(self, s, month):
        r = s.get(f"{API}/clients", params={"month": month})
        assert r.status_code == 200
        data = r.json()
        assert any(c["nome"] == "TEST_Ana" for c in data)

    def test_update_client_recalc(self, s, month):
        clients = s.get(f"{API}/clients", params={"month": month}).json()
        cid = clients[0]["id"]
        r = s.put(f"{API}/clients/{cid}", json={"adicional": 300, "pagFinal": 500})
        assert r.status_code == 200
        u = r.json()
        assert u["recebido"] == 1000  # 200+300+500
        assert u["statusFin"] == "Quitado"
        # GET verify
        g = s.get(f"{API}/clients", params={"month": month}).json()
        found = [x for x in g if x["id"] == cid][0]
        assert found["statusFin"] == "Quitado"

    def test_payment_add_and_delete(self, s, month):
        clients = s.get(f"{API}/clients", params={"month": month}).json()
        cid = clients[0]["id"]
        prev_adicional = clients[0]["adicional"]
        r = s.post(f"{API}/clients/{cid}/payments", json={"date": "2026-01-15", "amount": 150, "method": "Pix", "note": "test"})
        assert r.status_code == 200
        u = r.json()
        assert len(u["payments"]) == 1
        assert u["adicional"] == prev_adicional + 150
        pid = u["payments"][0]["id"]
        # delete
        r2 = s.delete(f"{API}/clients/{cid}/payments/{pid}")
        assert r2.status_code == 200
        assert r2.json()["adicional"] == prev_adicional
        assert len(r2.json()["payments"]) == 0

    def test_delete_client(self, s, month):
        clients = s.get(f"{API}/clients", params={"month": month}).json()
        cid = clients[0]["id"]
        r = s.delete(f"{API}/clients/{cid}")
        assert r.status_code == 200
        # verify gone
        after = s.get(f"{API}/clients", params={"month": month}).json()
        assert not any(c["id"] == cid for c in after)

    def test_create_client_no_name(self, s, month):
        r = s.post(f"{API}/clients", json={"month": month, "nome": ""})
        assert r.status_code in (400, 422)


# Stats
class TestStats:
    def test_stats(self, s):
        r = s.get(f"{API}/stats")
        assert r.status_code == 200
        d = r.json()
        for k in ("by_month", "by_stage", "by_status", "total_clients"):
            assert k in d
        assert isinstance(d["by_month"], list)
