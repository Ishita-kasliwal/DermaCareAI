from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user

from app.blueprints.auth import bp
from app.extensions import limiter
from app.forms import ConfirmForm, ForgotPasswordForm, LoginForm, RegisterForm, ResetPasswordForm
from app.security.passwords import MIN_LENGTH
from app.security.utils import safe_next_url
from app.services.audit_service import audit
from app.services.auth_service import AuthError, authenticate, get_user_by_email, register_user
from app.services.password_reset import (
    ResetError,
    mail_configured,
    send_reset_email,
    user_from_token,
)
from app.services.password_reset import reset_password as reset_with_token
from app.services import google_auth


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["REGISTER_RATE_LIMIT"], methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            user = register_user(form.email.data, form.full_name.data, form.password.data)
        except AuthError as e:
            getattr(form, e.field or "email").errors.append(e.message)
        else:
            session.clear()
            login_user(user)
            session.permanent = True
            flash("Welcome to DermaCareAI! Your account is ready.", "success")
            return redirect(url_for("main.dashboard"))
    return render_template("auth/register.html", form=form, min_length=MIN_LENGTH), (
        400 if form.errors else 200)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["LOGIN_RATE_LIMIT"], methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = LoginForm()
    if request.method == "GET":
        form.next.data = request.args.get("next", "")
    error = None
    if form.validate_on_submit():
        try:
            user = authenticate(form.email.data, form.password.data)
        except AuthError as e:
            error = e.message
        else:
            target = safe_next_url(form.next.data, url_for("main.dashboard"))
            session.clear()  # new session on privilege change (prevents fixation)
            login_user(user)
            session.permanent = True
            return redirect(target)
    status = 401 if error else (400 if form.errors else 200)
    return render_template("auth/login.html", form=form, error=error), status


@bp.route("/forgot", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["FORGOT_RATE_LIMIT"], methods=["POST"])
def forgot_password():
    """Always shows the same message, whether or not the account exists (no account fishing)."""
    if current_user.is_authenticated:
        return redirect(url_for("account.profile"))
    form = ForgotPasswordForm()
    sent = False
    if form.validate_on_submit():
        user = get_user_by_email(form.email.data)
        if user is not None and user.is_active:
            emailed = send_reset_email(user)
            audit("password_reset_requested", user, "user", user.public_id,
                  details={"delivery": "email" if emailed else "admin"})
        else:
            audit("password_reset_requested", None, details={"known_account": False})
        sent = True
    return render_template("auth/forgot.html", form=form, sent=sent, mail_enabled=mail_configured())


@bp.route("/reset/<token>", methods=["GET", "POST"])
@limiter.limit(lambda: current_app.config["LOGIN_RATE_LIMIT"], methods=["POST"])
def reset_password(token):
    if current_user.is_authenticated:
        logout_user()
        session.clear()
    try:
        user = user_from_token(token)
    except ResetError as e:
        return render_template("auth/reset.html", form=None, invalid=e.message), 400
    form = ResetPasswordForm()
    if form.validate_on_submit():
        try:
            reset_with_token(token, form.password.data)
        except ResetError as e:
            if e.field:
                form.password.errors.append(e.message)
            else:
                return render_template("auth/reset.html", form=None, invalid=e.message), 400
        else:
            flash("Your password has been changed. You can log in with it now.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset.html", form=form, invalid=None, user=user, min_length=MIN_LENGTH), (
        400 if form.errors else 200)


@bp.get("/google")
@limiter.limit(lambda: current_app.config["LOGIN_RATE_LIMIT"])
def google_start():
    """Send the person to Google to choose their account. Authlib stores state + nonce in the session."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if not google_auth.google_configured():
        flash("Google sign-in isn't set up on this site yet. Please use your email and password.", "info")
        return redirect(url_for("auth.login"))
    # Google only accepts the exact return address saved in Google Cloud (docs/GOOGLE_SIGNIN.md uses 127.0.0.1).
    # "localhost" is the same computer but a different address to Google, so move to 127.0.0.1 first
    # (before anything is stored in the session, which is tied to the address).
    host = request.host.partition(":")[0]
    if host == "localhost" and current_app.config.get("GOOGLE_LOCALHOST_TO_127", True):
        return redirect(request.url.replace("//localhost", "//127.0.0.1", 1))
    session["google_next"] = safe_next_url(request.args.get("next", ""), url_for("main.dashboard"))
    redirect_uri = current_app.config.get("GOOGLE_REDIRECT_URI") or url_for("auth.google_callback", _external=True)
    current_app.logger.info("google sign-in: redirect_uri sent to Google = %s", redirect_uri)
    try:
        return google_auth.client().authorize_redirect(redirect_uri)
    except Exception:  # noqa: BLE001 - e.g. no internet to reach Google
        current_app.logger.exception("google sign-in start failed")
        flash("We couldn't reach Google just now. Please try again, or use your email and password.", "error")
        return redirect(url_for("auth.login"))


@bp.get("/google/callback")
@limiter.limit(lambda: current_app.config["LOGIN_RATE_LIMIT"])
def google_callback():
    if not google_auth.google_configured():
        return redirect(url_for("auth.login"))
    if request.args.get("error"):  # the person pressed Cancel on Google's page
        flash("Google sign-in was cancelled. You can try again or use your email and password.", "info")
        return redirect(url_for("auth.login"))
    target = session.pop("google_next", None) or url_for("main.dashboard")
    try:
        token = google_auth.client().authorize_access_token()  # checks state, nonce and the ID token
        info = token.get("userinfo") or {}
        user = google_auth.user_from_google(info)
    except AuthError as e:
        audit("login_fail", None, details={"reason": "google", "message": e.message[:80]})
        flash(e.message, "error")
        return redirect(url_for("auth.login"))
    except Exception:  # noqa: BLE001 - bad/expired state, network error, invalid token
        current_app.logger.exception("google sign-in failed")
        flash("Google sign-in didn't work this time. Please try again.", "error")
        return redirect(url_for("auth.login"))
    session.clear()  # new session on login (prevents fixation)
    login_user(user)
    session.permanent = True
    flash(f"Welcome, {user.first_name}! You're logged in with Google.", "success")
    return redirect(safe_next_url(target, url_for("main.dashboard")))


@bp.post("/logout")
def logout():
    form = ConfirmForm()
    if form.validate_on_submit() and current_user.is_authenticated:
        audit("logout", current_user, "user", current_user.public_id)
        logout_user()
        session.clear()
        flash("You've been logged out. See you soon!", "info")
    return redirect(url_for("main.index"))
