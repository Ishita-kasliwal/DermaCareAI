from app.extensions import db
from app.models import AuditLog, User
from tests.conftest import PASSWORD, login, logout, make_user

GOOD = {"full_name": "Carol Diaz", "email": "Carol@Example.com", "password": "Lichen-Planus-42",
        "confirm": "Lichen-Planus-42", "accept": "y"}


def test_register_creates_hashed_user_and_signs_in(client, app):
    r = client.post("/auth/register", data=GOOD)
    assert r.status_code == 302 and r.headers["Location"].endswith("/dashboard")
    u = db.session.scalar(db.select(User).filter_by(email="carol@example.com"))
    assert u is not None, "email is normalised to lower case"
    assert u.password_hash.startswith("$argon2id$")
    assert GOOD["password"] not in u.password_hash
    assert client.get("/dashboard").status_code == 200


def test_register_rejects_duplicate_weak_mismatch_and_missing_consent(client, user):
    cases = [
        ({**GOOD, "email": "alice@example.com"}, b"already an account"),
        ({**GOOD, "password": "short", "confirm": "short"}, b"at least 10"),
        ({**GOOD, "password": "password123", "confirm": "password123"}, b"too easy to guess"),
        ({**GOOD, "password": "carol-and-carol!", "confirm": "carol-and-carol!"}, b"use your email in your password"),
        ({**GOOD, "confirm": "Different-Pass-1"}, b"don&#39;t match"),
        ({k: v for k, v in GOOD.items() if k != "accept"}, b"tick this box"),
        ({**GOOD, "email": "not-an-email"}, b"valid email"),
        ({**GOOD, "full_name": "<script>x</script>"}, b"simple punctuation"),
    ]
    for data, msg in cases:
        r = client.post("/auth/register", data=data)
        assert r.status_code == 400, data
        assert msg in r.data, (data, msg)
    assert db.session.scalar(db.select(db.func.count(User.id))) == 1


def test_login_success_and_logout(client, user):
    r = login(client)
    assert r.status_code == 302
    assert client.get("/dashboard").status_code == 200
    assert logout(client).status_code == 302
    assert client.get("/dashboard").status_code == 302


def test_login_errors_are_generic(client, user):
    a = login(client, password="wrong-password-1")
    b = login(client, email="nobody@example.com")
    assert a.status_code == b.status_code == 401
    assert b"That email or password isn&#39;t right" in a.data
    assert b"That email or password isn&#39;t right" in b.data


def test_lockout_after_five_failures(client, user):
    for _ in range(5):
        login(client, password="wrong-password-1")
    r = login(client)  # correct password, but locked
    assert r.status_code == 401 and b"Too many wrong tries" in r.data
    assert db.session.scalar(db.select(db.func.count(AuditLog.id)).filter_by(action="account_locked")) == 1


def test_inactive_user_cannot_login(client, user):
    user.is_active_flag = False
    db.session.commit()
    r = login(client)
    assert r.status_code == 401 and b"switched off" in r.data


def test_logout_requires_post(client, user):
    login(client)
    assert client.get("/auth/logout").status_code == 405
    assert client.get("/dashboard").status_code == 200


def test_open_redirect_blocked(client, user):
    for evil in ("https://evil.example/", "//evil.example", "/\\evil.example", "javascript:alert(1)"):
        r = client.post("/auth/login", data={"email": "alice@example.com", "password": PASSWORD, "next": evil})
        assert r.headers["Location"].endswith("/dashboard"), evil
        logout(client)
    r = client.post("/auth/login", data={"email": "alice@example.com", "password": PASSWORD, "next": "/history/"})
    assert r.headers["Location"].endswith("/history/")


def test_password_change_signs_out_other_sessions(app, user):
    c1, c2 = app.test_client(), app.test_client()
    login(c1)
    login(c2)
    r = c1.post("/account/password", data={"current_password": PASSWORD, "new_password": "New-Dermis-Pass-7",
                                           "confirm": "New-Dermis-Pass-7"})
    assert r.status_code == 302
    assert c1.get("/dashboard").status_code == 200, "current session stays signed in"
    assert c2.get("/dashboard").status_code == 302, "other session is signed out"
    logout(c1)
    assert login(c1, password=PASSWORD).status_code == 401
    assert login(c1, password="New-Dermis-Pass-7").status_code == 302


def test_password_change_requires_current_password(client, user):
    login(client)
    r = client.post("/account/password", data={"current_password": "nope-nope-nope", "new_password": "New-Dermis-Pass-7",
                                               "confirm": "New-Dermis-Pass-7"})
    assert r.status_code == 400 and b"current password isn&#39;t right" in r.data


def test_profile_update_validates(client, user):
    login(client)
    ok = client.post("/account/", data={"full_name": "Alice B Walker", "birth_year": "1990", "sex": "female", "skin_type": "2"})
    assert ok.status_code == 302
    db.session.refresh(user)
    assert (user.full_name, user.birth_year, user.sex, user.skin_type) == ("Alice B Walker", 1990, "female", 2)
    for bad in ({"full_name": "A"}, {"full_name": "Alice", "birth_year": "1800"},
                {"full_name": "Alice", "sex": "dragon"}, {"full_name": "Alice", "skin_type": "9"}):
        assert client.post("/account/", data=bad).status_code == 400, bad


def test_delete_account_anonymises_and_blocks_login(client, user):
    login(client)
    r = client.post("/account/delete", data={"password": PASSWORD, "confirm_text": "DELETE"})
    assert r.status_code == 302
    db.session.refresh(user)
    assert user.deleted_at is not None and "alice" not in user.email and user.password_hash == "!deleted"
    assert login(client).status_code == 401


def test_delete_account_requires_password_and_confirmation(client, user):
    login(client)
    assert client.post("/account/delete", data={"password": "wrong-pass-123", "confirm_text": "DELETE"}).status_code == 400
    assert client.post("/account/delete", data={"password": PASSWORD, "confirm_text": "delete"}).status_code == 400
    db.session.refresh(user)
    assert user.deleted_at is None


def test_cli_create_admin(app):
    runner = app.test_cli_runner()
    res = runner.invoke(args=["create-admin", "--email", "root@example.com", "--name", "Root Admin"],
                        input="Admin-Strong-Pass-1\nAdmin-Strong-Pass-1\n")
    assert res.exit_code == 0, res.output
    u = db.session.scalar(db.select(User).filter_by(email="root@example.com"))
    assert u.role == "admin" and u.password_hash.startswith("$argon2id$")
    weak = runner.invoke(args=["create-admin", "--email", "w@example.com", "--name", "Weak"], input="short\nshort\n")
    assert weak.exit_code != 0


def test_make_user_helper_sanity(app):
    u = make_user("x@example.com", "X Person")
    assert u.public_id and u.get_id().endswith(".1")
