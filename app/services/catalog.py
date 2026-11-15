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
    # ---- rash or other skin problem (SCIN)
    "eczema": (
        "Dry, itchy, inflamed skin that often comes and goes. It's very common, especially in the creases "
        "of elbows and knees, and is not contagious.",
        "Moisturise often, use gentle soap and avoid things that trigger it. See a doctor or pharmacist if it "
        "keeps you awake, spreads, oozes or looks infected.",
    ),
    "contact_dermatitis": (
        "A red, itchy rash where the skin touched something that irritates it or causes an allergy, such as "
        "soaps, metals, plants, cosmetics or chemicals.",
        "Try to find and avoid what caused it, and wash the area gently. See a doctor if it's severe, on your "
        "face or genitals, or doesn't improve within a couple of weeks.",
    ),
    "urticaria": (
        "Raised, itchy welts (hives) that can appear and fade within hours, often due to an allergy, "
        "infection or stress.",
        "Antihistamines from a pharmacist often help. Get emergency help straight away if you have swelling of "
        "the lips, tongue or throat, or trouble breathing.",
    ),
    "insect_bite": (
        "Small itchy or painful bumps from bites or stings by insects such as mosquitoes, fleas, bed bugs or "
        "spiders.",
        "Clean the area, use a cold pack and avoid scratching. See a doctor if it becomes very red, hot, "
        "swollen or painful, or if you feel unwell.",
    ),
    "folliculitis": (
        "Small red bumps or pimples around hair follicles, often after shaving, sweating or tight clothing. "
        "Usually caused by mild infection or irritation.",
        "Keep the area clean and avoid shaving it for a while. See a doctor if it spreads, keeps coming back or "
        "forms painful lumps.",
    ),
    "fungal": (
        "A fungal infection of the skin, such as ringworm or athlete's foot. It often looks like a red, scaly, "
        "ring-shaped patch, or lighter or darker patches on the body.",
        "Antifungal creams from a pharmacist often work well. Keep the skin clean and dry. See a doctor if it "
        "spreads or doesn't improve after two weeks of treatment.",
    ),
    "acne": (
        "Spots, blackheads or redness on the face, chest or back. This group also includes rosacea, which "
        "causes facial redness and small bumps.",
        "Gentle skin care and over-the-counter treatments often help. See a doctor if it's painful, leaves "
        "scars or affects how you feel.",
    ),
    "psoriasis": (
        "Thick, red or darker patches covered in silvery scales, often on elbows, knees or the scalp. "
        "It's a long-term condition and is not contagious.",
        "It's worth seeing a doctor. There are effective treatments, and a doctor can confirm it's psoriasis.",
    ),
    "shingles": (
        "A painful rash with blisters, usually in a band on one side of the body. It's caused by the chickenpox "
        "virus waking up again.",
        "Please see a doctor soon, ideally within 3 days of the rash appearing, because antiviral medicine works "
        "best early. Get urgent help if it's near your eye.",
    ),
    "cold_sores": (
        "Small, painful blisters, usually on or around the lips, caused by the herpes simplex virus. They tend to "
        "come back from time to time.",
        "They usually heal by themselves in 1-2 weeks, and antiviral creams can help. Avoid kissing and sharing "
        "cups while you have one. See a doctor if they're frequent or severe.",
    ),
    "dermatitis": (
        "Red, itchy, irritated skin, often from something that touched the skin, like soap, metal, plants or "
        "a new product. It is not contagious.",
        "Try to find and stop using whatever caused it, and keep the skin moisturised. See a doctor or "
        "pharmacist if it spreads, oozes, or doesn't get better in two weeks.",
    ),
    "ringworm": (
        "A common skin infection caused by a fungus (not a worm). It usually looks like a red, itchy, "
        "ring-shaped patch with a clearer middle. It can spread by touch or shared towels.",
        "Antifungal creams from a pharmacist usually clear it in 2-4 weeks. Keep the skin clean and dry and "
        "don't share towels. See a doctor if it's on your scalp or doesn't get better.",
    ),
}

DISPLAY_ORDER = ["mel", "bcc", "akiec", "bkl", "nv", "df", "vasc",
                 "dermatitis", "eczema", "ringworm",
                 "contact_dermatitis", "urticaria", "insect_bite", "folliculitis", "fungal",
                 "acne", "psoriasis", "shingles", "cold_sores"]


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
        row.domain = info.domain
        row.display_order = order
    db.session.commit()
    return created
