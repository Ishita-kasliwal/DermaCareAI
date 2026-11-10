from flask import flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required, logout_user

from app.blueprints.account import bp
from app.forms import DeleteAccountForm, PasswordChangeForm, ProfileForm
from app.security.passwords import MIN_LENGTH
from app.services.auth_service import AuthError, change_password, delete_account, update_profile


def _render(profile_form=None, password_form=None, delete_form=None, status=200):
    user = current_user
    if profile_form is None:
        profile_form = ProfileForm(obj=user, formdata=None)
        profile_form.sex.data = user.sex or ""
        profile_form.skin_type.data = str(user.skin_type) if user.skin_type else ""
    return render_template(
        "account/profile.html",
        profile_form=profile_form,
        password_form=password_form or PasswordChangeForm(formdata=None),
        delete_form=delete_form or DeleteAccountForm(formdata=None),
        min_length=MIN_LENGTH,
    ), status


@bp.get("/")
@login_required
def profile():
    return _render()


@bp.post("/")
@login_required
def profile_update():
    form = ProfileForm()
    if not form.validate_on_submit():
        return _render(profile_form=form, status=400)
    update_profile(current_user, form.full_name.data, form.birth_year.data, form.sex.data,
                   int(form.skin_type.data) if form.skin_type.data else None)
    flash("Saved! Your details are up to date.", "success")
    return redirect(url_for("account.profile"))


@bp.post("/password")
@login_required
def password():
    form = PasswordChangeForm()
    if form.validate_on_submit():
        try:
            change_password(current_user, form.current_password.data, form.new_password.data)
        except AuthError as e:
            getattr(form, e.field or "new_password").errors.append(e.message)
        else:
            # auth_version changed -> refresh this session's login id, others are signed out
            from flask_login import login_user

            login_user(current_user._get_current_object())
            flash("Password changed. You've been logged out on your other devices.", "success")
            return redirect(url_for("account.profile"))
    return _render(password_form=form, status=400)


@bp.post("/delete")
@login_required
def delete():
    form = DeleteAccountForm()
    if form.validate_on_submit():
        try:
            delete_account(current_user._get_current_object(), form.password.data)
        except AuthError as e:
            form.password.errors.append(e.message)
        else:
            logout_user()
            session.clear()
            flash("Your account and all your photos have been deleted.", "info")
            return redirect(url_for("main.index"))
    return _render(delete_form=form, status=400)
