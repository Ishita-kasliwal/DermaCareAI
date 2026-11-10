"""Server-side validated forms (Flask-WTF). Every field is validated here regardless of client checks.
Labels and messages use simple, friendly English."""

from __future__ import annotations

from datetime import date

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import (
    BooleanField,
    DateField,
    EmailField,
    HiddenField,
    IntegerField,
    PasswordField,
    RadioField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    Regexp,
)

NAME_RE = r"^[^\x00-\x1f<>{}\[\]\\]+$"  # printable, no markup characters

SEX_CHOICES = [("", "Prefer not to say"), ("female", "Female"), ("male", "Male"), ("other", "Other")]
SKIN_CHOICES = [("", "Not sure / prefer not to say")] + [
    (str(i), f"Type {r}: {d}") for i, (r, d) in enumerate([
        ("I", "always burns, never tans"), ("II", "usually burns, tans a little"),
        ("III", "sometimes burns, tans slowly"), ("IV", "rarely burns, tans easily"),
        ("V", "very rarely burns, tans very easily"), ("VI", "never burns"),
    ], start=1)
]


def _empty_to_none(v):
    return v if v not in ("", None) else None


class RegisterForm(FlaskForm):
    full_name = StringField("Your name", validators=[
        DataRequired("Please enter your name."), Length(2, 120, "Please enter between 2 and 120 characters."),
        Regexp(NAME_RE, message="Please use only letters, spaces and simple punctuation.")])
    email = EmailField("Email", validators=[
        DataRequired("Please enter your email."),
        Email("Please enter a valid email, like name@example.com.", check_deliverability=False), Length(max=254)])
    password = PasswordField("Password", validators=[DataRequired("Please choose a password."), Length(max=128)])
    confirm = PasswordField("Type your password again", validators=[
        DataRequired("Please type your password again."), EqualTo("password", "The two passwords don't match.")])
    accept = BooleanField("I understand that DermaCareAI is not a doctor and can't give a diagnosis", validators=[
        DataRequired("Please tick this box to continue.")])


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired("Please enter your email."), Length(max=254)])
    password = PasswordField("Password", validators=[DataRequired("Please enter your password."), Length(max=128)])
    next = HiddenField()


class ProfileForm(FlaskForm):
    full_name = StringField("Your name", validators=[
        DataRequired("Please enter your name."), Length(2, 120, "Please enter between 2 and 120 characters."),
        Regexp(NAME_RE, message="Please use only letters, spaces and simple punctuation.")])
    birth_year = IntegerField("Year you were born (optional)", validators=[
        Optional(), NumberRange(1900, date.today().year, "Please enter a year between 1900 and this year.")])
    sex = SelectField("Sex (optional)", choices=SEX_CHOICES, validators=[Optional()], filters=[_empty_to_none])
    skin_type = SelectField("Skin type (optional)", choices=SKIN_CHOICES, validators=[Optional()],
                            filters=[_empty_to_none])


class PasswordChangeForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[
        DataRequired("Please enter your current password."), Length(max=128)])
    new_password = PasswordField("New password", validators=[DataRequired("Please choose a new password."), Length(max=128)])
    confirm = PasswordField("Type the new password again", validators=[
        DataRequired("Please type the new password again."), EqualTo("new_password", "The two passwords don't match.")])


class DeleteAccountForm(FlaskForm):
    password = PasswordField("Your password", validators=[
        DataRequired("Please enter your password to confirm."), Length(max=128)])
    confirm_text = StringField('Type DELETE to confirm', validators=[
        DataRequired("Please type DELETE to confirm."), Regexp(r"^DELETE$", message="Please type DELETE in capital letters.")])


class UploadForm(FlaskForm):
    image = FileField("Photo of the skin spot", validators=[FileRequired("Please choose a photo to upload.")])


class AnalyzeForm(FlaskForm):
    consent = BooleanField(
        "I understand this is not a diagnosis, and I'll see a doctor if I'm worried about this spot.",
        validators=[DataRequired("Please tick the box to continue.")])


class FeedbackForm(FlaskForm):
    is_correct = RadioField("Did a doctor confirm this result?", choices=[
        ("yes", "Yes, the doctor agreed"), ("no", "No, the doctor said it was something else"),
        ("unsure", "I haven't seen a doctor yet")], validators=[InputRequired("Please choose an answer.")])
    suggested_class = SelectField("What did the doctor say it was?", choices=[], validators=[Optional()],
                                  filters=[_empty_to_none])
    comment = TextAreaField("Anything else? (optional)", validators=[Optional(), Length(max=500)])


class ConfirmForm(FlaskForm):
    """CSRF-protected button forms (delete, toggle, activate, logout)."""


class RoleForm(FlaskForm):
    role = SelectField("Role", choices=[("user", "User"), ("admin", "Admin")], validators=[DataRequired()])


class ClassEditForm(FlaskForm):
    description = TextAreaField("Description", validators=[DataRequired(), Length(10, 2000)])
    advice = TextAreaField("Advice shown with results", validators=[DataRequired(), Length(10, 2000)])


class HistoryFilterForm(FlaskForm):
    class Meta:
        csrf = False  # GET filter form, no state change

    category = SelectField("Type", choices=[], validators=[Optional()], filters=[_empty_to_none])
    status = SelectField("Result", choices=[("", "All results"), ("confident", "Clear match"),
                                            ("inconclusive", "Not sure")],
                         validators=[Optional()], filters=[_empty_to_none])
    risk = SelectField("Concern level", choices=[("", "All levels"), ("high", "See a doctor soon"),
                                                 ("medium", "Get it checked"), ("low", "Usually harmless")],
                       validators=[Optional()], filters=[_empty_to_none])
    date_from = DateField("From", validators=[Optional()])
    date_to = DateField("To", validators=[Optional()])


class UserSearchForm(FlaskForm):
    class Meta:
        csrf = False

    q = StringField("Search", validators=[Optional(), Length(max=100)])
    role = SelectField("Role", choices=[("", "All roles"), ("user", "Users"), ("admin", "Admins")],
                       validators=[Optional()], filters=[_empty_to_none])
    state = SelectField("Status", choices=[("", "All"), ("active", "Active"), ("inactive", "Switched off")],
                        validators=[Optional()], filters=[_empty_to_none])
