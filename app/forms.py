"""Server-side validated forms (Flask-WTF). Every field is validated here regardless of client checks.
Labels and messages use simple, friendly English."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from flask_wtf import FlaskForm
from flask_wtf.file import MultipleFileField
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
    ValidationError,
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


class ForgotPasswordForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired("Please enter your email."), Length(max=254)])


class ResetPasswordForm(FlaskForm):
    password = PasswordField("New password", validators=[DataRequired("Please choose a new password."), Length(max=128)])
    confirm = PasswordField("Type the new password again", validators=[
        DataRequired("Please type the new password again."), EqualTo("password", "The two passwords don't match.")])


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
    # Optional here: Google-only accounts have no current password. auth_service checks it when one exists.
    current_password = PasswordField("Current password", validators=[Optional(), Length(max=128)])
    new_password = PasswordField("New password", validators=[DataRequired("Please choose a new password."), Length(max=128)])
    confirm = PasswordField("Type the new password again", validators=[
        DataRequired("Please type the new password again."), EqualTo("new_password", "The two passwords don't match.")])


class DeleteAccountForm(FlaskForm):
    password = PasswordField("Your password", validators=[Optional(), Length(max=128)])  # checked in auth_service
    confirm_text = StringField('Type DELETE to confirm', validators=[
        DataRequired("Please type DELETE to confirm."), Regexp(r"^DELETE$", message="Please type DELETE in capital letters.")])


class UploadForm(FlaskForm):
    # "auto" first and pre-selected: most people don't know which checker fits, so the AI picks one
    check_type = RadioField("What are you checking?", choices=[
        ("auto", "Not sure? Let the AI choose"), ("lesion", "A mole or spot"),
        ("general", "A rash or other skin problem")],
        default="auto", validators=[InputRequired("Please choose what you are checking.")])
    # 1 to MAX_PHOTOS photos; checked in the upload route (each file is validated like a single upload)
    image = MultipleFileField("Photos of the skin")


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


# Letters (any script, incl. Indian vowel signs), spaces and . ' - ( ) only: no digits or markup in place names
PLACE_RE = r"^[^\W\d_](?:[^\W\d_]|[ऀ-෿]|[ .'()\-])*$"


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class DoctorSearchForm(FlaskForm):
    """Find a dermatologist near me (Task 4). A GET search form: nothing is saved."""

    class Meta:
        csrf = False

    city = StringField("City or town", filters=[_strip], validators=[
        DataRequired("Please type your city or town, for example Pune."),
        Length(min=2, max=60, message="Please type a city or town name between 2 and 60 letters long."),
        Regexp(PLACE_RE, message="Please use only letters and spaces in the city name (no numbers)."),
    ])
    district = StringField("District (optional)", filters=[_strip], validators=[
        Optional(),
        Length(min=2, max=60, message="Please type a district name between 2 and 60 letters long, or leave it empty."),
        Regexp(PLACE_RE, message="Please use only letters and spaces in the district name (no numbers)."),
    ])
    state = SelectField("State or union territory", choices=[], validators=[
        DataRequired("Please choose your state or union territory from the list."),
    ])
    prediction = HiddenField()   # optional: the check this search came from (used for booking later)

    def __init__(self, *args, **kwargs):
        from app.data.india import STATES, UNION_TERRITORIES

        super().__init__(*args, **kwargs)
        self.state.choices = ([("", "Choose your state")] + [(s, s) for s in STATES]
                              + [(u, f"{u} (UT)") for u in UNION_TERRITORIES])


def _not_in_past(form, field):
    """Dates are compared in India time (UTC+5:30), so "today" is right for people in India."""
    today = datetime.now(UTC).astimezone(timezone(timedelta(hours=5, minutes=30))).date()
    if field.data and field.data < today:
        raise ValidationError("Please choose today or a later date.")
    if field.data and field.data > today + timedelta(days=180):
        raise ValidationError("Please choose a date within the next 6 months.")


class AppointmentForm(FlaskForm):
    """Ask for an appointment at a clinic from the "Find a dermatologist" list (Task 5)."""

    patient_name = StringField("Your name", filters=[_strip], validators=[
        DataRequired("Please tell us your name."),
        Length(min=2, max=80, message="Please type a name between 2 and 80 letters long."),
        Regexp(NAME_RE, message="Please use only letters and spaces in your name."),
    ])
    patient_phone = StringField("Mobile number", filters=[lambda v: "".join(ch for ch in v if ch.isdigit())[-10:] if isinstance(v, str) else v],
                                validators=[
        DataRequired("Please type your mobile number so the clinic can reach you."),
        Regexp(r"^[6-9]\d{9}$", message="Please type a 10-digit mobile number, like 9876543210."),
    ])
    preferred_date = DateField("Preferred date", validators=[
        DataRequired("Please choose a date."), _not_in_past,
    ])
    time_slot = RadioField("Preferred time", choices=[
        ("morning", "Morning (9 am to 12 pm)"), ("afternoon", "Afternoon (12 to 4 pm)"),
        ("evening", "Evening (4 to 8 pm)")],
        validators=[InputRequired("Please choose a time of day.")])
    note = TextAreaField("Anything the clinic should know? (optional)", filters=[_strip], validators=[
        Optional(), Length(max=500, message="Please keep the note under 500 characters."),
    ])
    # the clinic (copied from the search result) and the check this booking came from
    clinic_name = HiddenField(validators=[DataRequired(), Length(max=160)])
    clinic_address = HiddenField(validators=[Optional(), Length(max=255)])
    clinic_phone = HiddenField(validators=[Optional(), Length(max=40)])
    clinic_lat = HiddenField(validators=[Optional(), Length(max=20)])
    clinic_lon = HiddenField(validators=[Optional(), Length(max=20)])
    prediction = HiddenField(validators=[Optional(), Length(max=36)])
