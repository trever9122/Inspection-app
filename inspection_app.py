# ---------------------------------------------------------
# AI Inspection App — Clean Modern UI + Auto‑Apply AI
# Full Rewrite (Part 1 of 2)
# ---------------------------------------------------------

import streamlit as st
from PIL import Image
import io
import pandas as pd
from fpdf import FPDF
import datetime
import os
import requests

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

st.set_page_config(
    page_title="AI Inspection App",
    layout="wide",
)

AZURE_VISION_ENDPOINT = st.secrets["AZURE_VISION_ENDPOINT"].rstrip("/")
AZURE_VISION_KEY = st.secrets["AZURE_VISION_KEY"]

VISION_ANALYZE_URL = (
    f"{AZURE_VISION_ENDPOINT}/computervision/imageanalysis:analyze"
    "?api-version=2023-10-01&features=tags,caption"
)

# ---------------------------------------------------------
# SAFE WIDGET KEY SANITIZER
# ---------------------------------------------------------

def safe_key(text):
    return (
        str(text)
        .replace(" ", "_")
        .replace("/", "_")
        .replace("(", "")
        .replace(")", "")
        .replace("-", "_")
        .replace(".", "_")
        .replace(",", "_")
    )

# ---------------------------------------------------------
# INSPECTION TEMPLATES
# ---------------------------------------------------------

DEFAULT_TEMPLATES = {
    "Move-in / Move-out": [
        {"room": "Living Room", "items": ["Walls", "Flooring", "Windows", "Doors"]},
        {"room": "Kitchen", "items": ["Counters", "Cabinets", "Appliances", "Sink"]},
        {"room": "Bedroom", "items": ["Walls", "Flooring", "Closet", "Windows"]},
        {"room": "Bathroom", "items": ["Vanity", "Toilet", "Shower/Tub", "Flooring"]},
    ],

    "Annual Inspection": [
        {"room": "Exterior", "items": ["Siding", "Roof (visible)", "Windows", "Doors"]},
        {"room": "Mechanical", "items": ["Furnace", "Water Heater", "Electrical Panel"]},
        {"room": "Interior Common", "items": ["Hallways", "Stairs", "Lighting"]},
    ],

    "Semi-Annual Inspection": [
        {"room": "Exterior", "items": ["Siding", "Foundation (visible)", "Windows", "Doors"]},
        {"room": "Mechanical", "items": ["Furnace", "Water Heater", "HVAC Filters"]},
        {"room": "Interior", "items": ["Walls", "Flooring", "Smoke Alarms", "CO Detectors"]},
    ],

    "Empty Unit Inspection": [
        {"room": "General Interior", "items": ["Walls", "Flooring", "Windows", "Doors"]},
        {"room": "Kitchen", "items": ["Counters", "Cabinets", "Appliances", "Sink"]},
        {"room": "Bathroom", "items": ["Vanity", "Toilet", "Shower/Tub", "Flooring"]},
        {"room": "Safety", "items": ["Smoke Alarms", "CO Detectors", "Locks"]},
    ],

    "Exterior / Yard Inspection": [
        {"room": "Exterior Structure", "items": ["Siding", "Foundation (visible)", "Roof (visible)", "Windows"]},
        {"room": "Yard", "items": ["Grass", "Fencing", "Walkways", "Driveway"]},
        {"room": "Outbuildings", "items": ["Shed Exterior", "Garage Exterior", "Doors"]},
    ],
}

CONDITION_OPTIONS = ["Good", "Fair", "Poor"]

# ---------------------------------------------------------
# TAG FILTERING
# ---------------------------------------------------------

STRUCTURAL_NEGATIVE_TAGS = {
    "crack", "cracked", "damage", "damaged", "broken", "stain", "stained",
    "dirty", "dirt", "mold", "mould", "rust", "rusty", "peeling", "chipped",
    "hole", "holes", "scratch", "scratched", "worn", "wear", "scuff",
    "scuffed", "dent", "dented", "leak", "leaking", "water damage"
}

STRUCTURAL_MINOR_TAGS = {
    "worn", "wear", "scuff", "scuffed", "chipped", "scratch", "scratched",
    "discoloration", "discoloured", "faded"
}

IGNORED_TAGS = {
    "cluttered", "messy", "clothes", "clothing", "bed", "blanket", "pillow",
    "box", "boxes", "bedding", "furniture", "sofa", "chair", "table",
    "personal items", "decor", "decoration", "toys", "laptop", "phone",
    "bag", "bags", "shoes", "books", "guitar", "instrument", "monitor",
    "tv", "television", "dresser", "couch", "lamp", "mirror", "frame",
    "plant", "plants", "bottle", "bottles", "laundry", "toy", "snake",
    "poster", "picture", "painting", "rug", "carpet", "mattress",
    "pillowcase", "sheet", "towel", "basket", "bin", "container"
}

# ---------------------------------------------------------
# PDF TEXT CLEANER
# ---------------------------------------------------------

def clean_text(text):
    if not text:
        return ""
    return (
        str(text)
        .replace("•", "-")
        .replace("—", "-")
        .replace("–", "-")
        .encode("latin-1", "replace")
        .decode("latin-1")
    )

# ---------------------------------------------------------
# AZURE VISION ANALYSIS
# ---------------------------------------------------------

def analyze_with_azure(image_file):
    img = Image.open(image_file).convert("RGB")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_VISION_KEY,
        "Content-Type": "application/octet-stream",
    }

    response = requests.post(
        VISION_ANALYZE_URL,
        headers=headers,
        data=img_bytes,
        timeout=15,
    )
    response.raise_for_status()
    result = response.json()

    tags = []
    if "tagsResult" in result and "values" in result["tagsResult"]:
        for t in result["tagsResult"]["values"]:
            tags.append((t.get("name", "").lower(), t.get("confidence", 0.0)))

    caption = result.get("captionResult", {}).get("text", "")

    return tags, caption

# ---------------------------------------------------------
# CONDITION + NOTE LOGIC
# ---------------------------------------------------------

def derive_condition_and_note(tags, caption, item_name):
    structural = [(name, conf) for name, conf in tags if name not in IGNORED_TAGS]

    has_severe = any(name in STRUCTURAL_NEGATIVE_TAGS for name, _ in structural)
    has_minor = any(name in STRUCTURAL_MINOR_TAGS for name, _ in structural)

    if has_severe:
        condition = "Poor"
    elif has_minor:
        condition = "Fair"
    else:
        condition = "Good"

    if condition == "Good":
        note = f"{item_name} appears clean and well-maintained with no concerns noted."
    elif condition == "Fair":
        note = f"{item_name} shows light wear consistent with normal use."
    else:
        note = f"{item_name} shows visible damage and may require repair."

    return condition, note

def analyze_photo_condition_only(image_file, item_name):
    tags, caption = analyze_with_azure(image_file)
    return derive_condition_and_note(tags, caption, item_name)

# ---------------------------------------------------------
# MERGE MULTIPLE PHOTOS
# ---------------------------------------------------------

def merge_conditions_and_notes(results, item_name):
    if not results:
        return "Good", f"- {item_name} appears clean and well-maintained."

    rank = {"Good": 1, "Fair": 2, "Poor": 3}
    worst = "Good"
    notes = []

    for cond, note in results:
        if rank[cond] > rank[worst]:
            worst = cond
        if note not in notes:
            notes.append(note)

    combined = "\n".join(f"- {n}" for n in notes)
    return worst, combined
    # ---------------------------------------------------------
# PART 2 — Full Rewritten App (Bottom Half)
# ---------------------------------------------------------

# ---------------------------------------------------------
# PDF GENERATION
# ---------------------------------------------------------

class InspectionPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 10, clean_text("Inspection Report"), ln=True, align="C")
        self.ln(2)
        self.set_draw_color(200, 200, 200)
        self.set_line_width(0.5)
        self.line(10, 22, 200, 22)
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, clean_text(f"Page {self.page_no()}"), align="C")


def generate_pdf(property_name, unit_name, inspection_type, data, photos_dict):
    pdf = InspectionPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, clean_text(f"Property: {property_name}"), ln=True)
    pdf.cell(0, 8, clean_text(f"Unit: {unit_name}"), ln=True)
    pdf.cell(0, 8, clean_text(f"Inspection Type: {inspection_type}"), ln=True)
    pdf.cell(0, 8, clean_text(f"Date: {datetime.date.today().isoformat()}"), ln=True)
    pdf.ln(6)

    pdf.set_draw_color(180, 180, 180)
    pdf.set_line_width(0.4)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    current_room = None
    for row in data:
        room = row["room"]
        item = row["item"]
        condition = row["condition"]
        note = row["note"]

        if room != current_room:
            current_room = room
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(0, 8, clean_text(room), ln=True)
            pdf.set_draw_color(210, 210, 210)
            pdf.set_line_width(0.3)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(2)
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(0, 0, 0)

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 6, clean_text(f"{item} - {condition}"), ln=True)
        if note:
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, clean_text(note))
        pdf.ln(2)

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 8, clean_text("Photos"), ln=True)
    pdf.ln(4)

    for key, files in photos_dict.items():
        room, item = key
        if not files:
            continue

        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 6, clean_text(f"{room} - {item}"), ln=True)
        pdf.ln(2)

        x_start = 10
        y_start = pdf.get_y()
        max_height_in_row = 0
        img_width = 60

        for idx, f in enumerate(files):
            try:
                img = Image.open(f).convert("RGB")
                img.thumbnail((800, 800))
                img_buffer = io.BytesIO()
                img.save(img_buffer, format="JPEG")
                img_buffer.seek(0)

                temp_path = f"temp_{safe_key(room)}_{safe_key(item)}_{idx}.jpg"
                with open(temp_path, "wb") as temp_img:
                    temp_img.write(img_buffer.getvalue())

                if x_start + img_width > 190:
                    x_start = 10
                    y_start += max_height_in_row + 4
                    max_height_in_row = 0

                pdf.image(temp_path, x=x_start, y=y_start, w=img_width)
                img_height = img.size[1] * (img_width / img.size[0])
                if img_height > max_height_in_row:
                    max_height_in_row = img_height

                x_start += img_width + 4

                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            except Exception:
                continue

        pdf.ln(max_height_in_row + 6)

    return pdf.output(dest="S").encode("latin-1", "replace")


# ---------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------

if "inspection_data" not in st.session_state:
    st.session_state.inspection_data = {}

if "photos" not in st.session_state:
    st.session_state.photos = {}

if "ai_results" not in st.session_state:
    st.session_state.ai_results = {}


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

st.sidebar.title("Inspection Setup")

property_name = st.sidebar.text_input("Property Name", "123 Sample Street")
unit_name = st.sidebar.text_input("Unit", "Unit 1")

inspection_type = st.sidebar.selectbox(
    "Inspection Type",
    list(DEFAULT_TEMPLATES.keys()),
    index=0,
)

template_rooms = DEFAULT_TEMPLATES[inspection_type]
room_names = [r["room"] for r in template_rooms]
selected_room = st.sidebar.selectbox("Room", room_names)

st.sidebar.markdown("---")
if st.sidebar.button("Reset Inspection Data"):
    st.session_state.inspection_data = {}
    st.session_state.photos = {}
    st.session_state.ai_results = {}
    st.sidebar.success("Inspection data cleared.")


# ---------------------------------------------------------
# MAIN HEADER
# ---------------------------------------------------------

st.title("AI-Powered Inspection App")

st.markdown(
    f"**Property:** {property_name} &nbsp;&nbsp; | &nbsp;&nbsp; "
    f"**Unit:** {unit_name} &nbsp;&nbsp; | &nbsp;&nbsp; "
    f"**Type:** {inspection_type}"
)

st.markdown("---")

current_room_struct = next(r for r in template_rooms if r["room"] == selected_room)
items = current_room_struct["items"]

st.header(selected_room)


# ---------------------------------------------------------
# ITEM LOOP — CLEAN + MODERN + AUTO-APPLY AI
# ---------------------------------------------------------

for item in items:
    key_prefix = safe_key(f"{selected_room}_{item}")
    photos_key = (selected_room, item)

    st.markdown(f"### {item}")

    container = st.container()
    with container:
        col_left, col_right = st.columns([1.1, 1.4], gap="large")

        # LEFT: CONDITION + NOTES
        with col_left:
            condition_widget_key = safe_key(f"{key_prefix}_condition")
            note_widget_key = safe_key(f"{key_prefix}_note")

            saved = st.session_state.inspection_data.get((selected_room, item), {})
            ai = st.session_state.ai_results.get(photos_key, {})

            default_condition = ai.get("condition", saved.get("condition", "Good"))
            default_note = ai.get("note", saved.get("note", ""))

            with st.container(border=True):
                st.markdown("**Condition**")
                condition = st.radio(
                    "",
                    CONDITION_OPTIONS,
                    index=CONDITION_OPTIONS.index(default_condition),
                    key=condition_widget_key,
                    horizontal=True,
                )

            with st.container(border=True):
                st.markdown("**Notes**")
                note = st.text_area(
                    "",
                    value=default_note,
                    key=note_widget_key,
                    placeholder=f"Add any notes about the {item.lower()}...",
                    height=120,
                )

        # RIGHT: PHOTOS + AI
        with col_right:
            with st.container(border=True):
                st.markdown("**Photos**")

                photos_widget_key = safe_key(f"{key_prefix}_photos")

                uploaded_photos = st.file_uploader(
                    f"Upload photos for {item}",
                    type=["jpg", "jpeg", "png"],
                    accept_multiple_files=True,
                    key=photos_widget_key,
                )

                if uploaded_photos:
                    st.session_state.photos[photos_key] = uploaded_photos

                    ai_results = []
                    with st.spinner("Analyzing photos with Azure Vision..."):
                        for p in uploaded_photos:
                            try:
                                ai_condition, ai_note = analyze_photo_condition_only(p, item)
                                ai_results.append((ai_condition, ai_note))
                            except Exception as e:
                                st.warning(f"Azure analysis failed: {e}")

                    if ai_results:
                        final_condition, combined_note = merge_conditions_and_notes(ai_results, item)

                        st.session_state.ai_results[photos_key] = {
                            "condition": final_condition,
                            "note": combined_note,
                        }

                        st.success(f"AI Suggested Condition: {final_condition}")
                        st.info("AI Suggested Notes:\n" + combined_note)
                        st.caption("AI has been applied as the default. You can still edit the fields on the left.")

                if photos_key in st.session_state.photos:
                    photo_files = st.session_state.photos[photos_key]
                    if photo_files:
                        cols_photos = st.columns(3)
                        for idx, p in enumerate(photo_files):
                            with cols_photos[idx % 3]:
                                st.image(p, caption=f"{item} photo", use_column_width=True)

    st.session_state.inspection_data[(selected_room, item)] = {
        "condition": condition,
        "note": note,
    }

st.markdown("---")
st.header("Inspection Summary")

summary_rows = []
for room_struct in template_rooms:
    room = room_struct["room"]
    for item in room_struct["items"]:
        data = st.session_state.inspection_data.get((room, item), {})
        condition = data.get("condition", "Good")
        note = data.get("note", "")
        summary_rows.append(
            {"room": room, "item": item, "condition": condition, "note": note}
        )

df = pd.DataFrame(summary_rows)
st.dataframe(df, use_container_width=True)

if st.button("Generate PDF Report"):
    pdf_bytes = generate_pdf(
        property_name,
        unit_name,
        inspection_type,
        summary_rows,
        st.session_state.photos,
    )
    st.download_button(
        label="Download Inspection PDF",
        data=pdf_bytes,
        file_name=f"inspection_{property_name}_{unit_name}.pdf",
        mime="application/pdf",
    )

# ---------------------------------------------------------
# END OF FILE
# ---------------------------------------------------------
