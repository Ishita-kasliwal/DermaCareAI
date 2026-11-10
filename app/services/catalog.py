"""Reference content for the 7 supported skin-spot types (seeded into disease_classes).

Written in simple, friendly English for patients. No diagnostic claims.
"""

from skinai_ml.classes import CLASS_INFO

CLASS_CONTENT = {
    "mel": (
        "A type of skin cancer that starts in the cells that give skin its colour. Warning signs: an uneven "
        "shape, a ragged edge, more than one colour, bigger than a pencil eraser (about 6 mm), or any change over time.",
        "Please book a visit with a skin doctor (dermatologist) as soon as you can. Finding melanoma early "
        "makes a big difference, and only a doctor can confirm it.",
    ),
    "bcc": (
        "The most common skin cancer. It often looks like a shiny or pearly bump, a pink scaly patch, or a "
        "sore that doesn't heal. It grows slowly and rarely spreads, but it should be treated.",
        "Please see a skin doctor soon. They can check it properly, and treatment works very well when "
        "it starts early.",
    ),
    "akiec": (
        "Rough, scaly patches caused by years of sun (actinic keratosis), or a very early skin cancer that "
        "stays in the top layer of skin (Bowen's disease). Some can turn into skin cancer if left alone.",
        "Book a visit with a skin doctor in the next few weeks. These are usually easy to treat when found early.",
    ),
    "bkl": (
        "Harmless growths such as age spots, sun spots and seborrheic keratoses (raised, waxy-looking spots). "
        "They become more common as we get older.",
        "Usually nothing to worry about. Get it checked if it changes quickly, bleeds, keeps itching, or looks "
        "different from your other spots.",
    ),
    "nv": (
        "A common mole: a harmless group of colour cells in the skin. Most adults have between 10 and 40 moles.",
        "Usually harmless. Keep an eye on it, and see a doctor if it changes size, shape or colour, or looks "
        "different from your other moles.",
    ),
    "df": (
        "A small, firm, harmless bump, often on the legs, that may dip inward when you pinch it. It sometimes "
        "appears after a small injury or insect bite.",
        "Usually harmless. Ask a doctor to look at it if it grows, starts to hurt, or you're unsure.",
    ),
    "vasc": (
        "Harmless spots made of tiny blood vessels, such as cherry angiomas. They are usually red, purple or blue.",
        "Usually harmless. See a doctor if it bleeds again and again or grows quickly.",
    ),
}

DISPLAY_ORDER = ["mel", "bcc", "akiec", "bkl", "nv", "df", "vasc"]


def seed_disease_classes(db, update_text: bool = False) -> int:
    """Insert the 7 types (and refresh names/risk). Returns number of rows created.

    Description/advice are only written for new rows unless update_text=True, so text an admin
    edited is not overwritten by accident.
    """
    from app.models import DiseaseClass

    created = 0
    for order, code in enumerate(DISPLAY_ORDER):
        info = CLASS_INFO[code]
        description, advice = CLASS_CONTENT[code]
        row = db.session.scalar(db.select(DiseaseClass).filter_by(code=code))
        if row is None:
            row = DiseaseClass(code=code)
            db.session.add(row)
            created += 1
            update_row_text = True
        else:
            update_row_text = update_text
        if update_row_text:
            row.description = description
            row.advice = advice
        row.name = info.name
        row.risk_level = info.risk_level
        row.display_order = order
    db.session.commit()
    return created
