# ------------------------------
# inspection_app.py (FINAL BUILD)
# ------------------------------

import streamlit as st
from PIL import Image
import io
import pandas as pd
from fpdf import FPDF
import datetime
import os
import requests

# ---------- CONFIG ----------

st.set_page_config(page_title="AI Inspection App (Azure Vision)", layout="wide")

AZURE_VISION_ENDPOINT = st.secrets["AZURE_VISION_ENDPOINT"].rstrip("/")
AZURE_VISION_KEY = st.secrets["AZURE_VISION_KEY"]

VISION_ANALYZE_URL = (
    f"{AZURE_VISION_ENDPOINT}/computervision/imageanalysis:analyze"
    "?api-version=2023-10-01&features=tags,caption"
)

# ---------- DATA MODELS ----------

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

# ---------- STRUCTURAL TAG FILTERING ----------

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

STRUCTURAL_POSITIVE_TAGS = {
    "clean", "intact", "undamaged", "new", "well maintained", "good condition"
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

# ---------- AZURE VISION ANALYSIS ----------

def analyze_with_azure(image_file):
    img = Image.open(image_file).convert("RGB")
    img.thumbnail((1024, 1024))
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG")
    img_bytes = buffered.getvalue()

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
            name = t.get("name", "").lower()
            conf = t.get("confidence", 0.0)
            tags.append((name, conf))

    caption_text = result.get("captionResult", {}).get("text", "")

    return tags, caption_text

# ---------- CONDITION + NOTE LOGIC (STRUCTURE ONLY, NATURAL LANGUAGE) ----------

def derive_condition_and_note(tags, caption_text, item_name):
    structural_tags = []
    for name, conf in tags:
        if name in IGNORED_TAGS:
            continue
        structural_tags.append((name, conf))

    has_severe = False
    has_minor = False

    negative_hits = []
    minor_hits = []

    for name, conf in structural_tags:
        if name in STRUCTURAL_NEGATIVE_TAGS:
            has_severe = True
            negative_hits.append(name)
        elif name in STRUCTURAL_MINOR_TAGS:
            has_minor = True
            minor_hits.append(name)

    if has_severe:
        condition = "Poor"
    elif has_minor:
        condition = "Fair"
    else:
        condition = "Good"

    if condition == "Good":
        note = f"{item_name} appears clean and well-maintained with no concerns noted."
    elif condition == "Fair":
        if minor_hits:
            note = (
                f"{item_name} shows light wear, including {', '.join(set(minor_hits))}. "
                "Overall condition is acceptable."
            )
        else:
            note = f"{item_name} shows general wear consistent with normal use."
    else:
        if negative_hits:
            note = (
                f"{item_name} shows visible damage, including {', '.join(set(negative_hits))}. "
                "Repairs should be scheduled."
            )
        else:
            note = f"{item_name} shows significant deterioration and may require repair."

    return condition, note

def analyze_photo_condition_only(image_file, item_name):
    tags, caption_text = analyze_with_azure(image_file)
    return derive_condition_and_note(tags, caption_text, item_name)

# ---------- CONDITION MERGING (MULTI-PHOTO) ----------

def merge_conditions_and_notes(results, item_name):
    if not results:
        return "Good", ""

    condition_rank = {"Good": 1, "Fair": 2, "Poor": 3}
    worst_condition = "Good"
    notes = []

    for cond, note in results:
        if condition_rank[cond] > condition_rank[worst_condition]:
            worst_condition = cond
        if note and note not in notes:
            notes.append(note)

    if notes:
        bullet_notes = "\n".join([f"• {n}" for n in notes])
    else:
        if worst_condition == "Good":
            bullet_notes = f"• {item_name} appears clean and well-maintained."
        elif worst_condition == "Fair":
            bullet_notes = f"• {item_name} shows general wear consistent with normal use."
        else:
            bullet_notes = f"• {item_name} shows visible damage and may require repair."

    return worst_condition, bullet_notes

# ---------- PDF GENERATION (PROFESSIONAL LAYOUT) ----------

class InspectionPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 10, "Inspection Report", ln=True, align="C")
        self.ln(2)
        self.set_draw_color(200, 200, 200)
        self.set_line_width(0.5)
        self.line(10, 22, 200, 22)
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

def generate_pdf(property_name, unit_name, inspection_type, data, photos_dict):
    pdf = InspectionPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, f"Property: {property_name}", ln=True)
    pdf.cell(0, 8, f"Unit: {unit_name}", ln=True)
    pdf.cell(0, 8, f"Inspection Type: {inspection_type}", ln=True)
    pdf.cell(0, 8, f"Date: {datetime.date.today().isoformat()}", ln=True)
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
            pdf.cell(0, 8, room, ln=True)
            pdf.set_draw_color(210, 210, 210)
            pdf.set_line_width(0.3)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(2)
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(0, 0, 0)

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 6, f"{item} — {condition}", ln=True)
        if note:
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, note)
        pdf.ln(2)

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 8, "Photos", ln=True)
    pdf.ln(4)

    for key, files in photos_dict.items():
        room, item = key
        if not files:
            continue

        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 6, f"{room} — {item}", ln=True)
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

                temp_path = f"temp_{room}_{item}_{idx}.jpg"
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

    return pdf.output(dest="S").encode("latin-1")

# ---------- SESSION STATE ----------

if "inspection_data" not in st.session_state:
    st.session_state.inspection_data = {}

if "photos" not in st.session_state:
    st.session_state.photos = {}

if "ai_results" not in st.session_state:
    st.session_state.ai_results = {}

# ---------- SIDEBAR ----------

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

# ---------- MAIN UI ----------

st.title("AI-Powered Inspection App (Azure Vision — Condition Only)")

st.markdown(
    f"**Property:** {property_name} &nbsp;&nbsp; | &nbsp;&nbsp; "
    f"**Unit:** {unit_name} &nbsp;&nbsp; | &nbsp;&nbsp; "
    f"**Type:** {inspection_type}"
)

st.markdown("---")

current_room_struct = next(r for r in template_rooms if r["room"] == selected_room)
items = current_room_struct["items"]

st.header(selected_room)

for item in items:
    key_prefix = f"{selected_room}_{item}"

    st.subheader(item)

    cols = st.columns([1, 2])

    with cols[0]:
        condition_key = f"{key_prefix}_condition"
        note_key = f"{key_prefix}_note"

        current_condition = st.session_state.inspection_data.get(
            (selected_room, item), {}
        ).get("condition", "Good")

        condition = st.radio(
            "Condition",
            CONDITION_OPTIONS,
            index=CONDITION_OPTIONS.index(current_condition),
            key=condition_key,
            horizontal=True,
        )

        note_default = st.session_state.inspection_data.get(
            (selected_room, item), {}
        ).get("note", ""
        )

        note = st.text_area(
            "Notes",
            value=note_default,
            key=note_key,
            placeholder=f"Add any notes about the {item.lower()}...",
        )

    with cols[1]:
        st.write("**Photos**")

        photos_key = (selected_room, item)
        uploaded_photos = st.file_uploader(
            f"Upload photos for {item}",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key=f"{key_prefix}_photos",
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
                        st.warning(f"Azure analysis failed for one photo: {e}")

            if ai_results:
                final_condition, combined_note = merge_conditions_and_notes(ai_results, item)
                st.session_state.ai_results[photos_key] = {
                    "condition": final_condition,
                    "note": combined_note,
                }

                if ai_results:
    final_condition, combined_note = merge_conditions_and_notes(ai_results, item)
    st.session_state.ai_results[photos_key] = {
        "condition": final_condition,
        "note": combined_note,
    }

    st.success(f"AI Suggested Condition: {final_condition}")
    st.info("AI Suggested Notes:\n" + combined_note)

    if st.button(f"Use AI result for {item}", key=f"{key_prefix}_apply_ai"):
        # Update the widget values safely
        st.session_state[condition_key] = final_condition
        st.session_state[note_key] = combined_note

        # Save to inspection data
        st.session_state.inspection_data[(selected_room, item)] = {
            "condition": final_condition,
            "note": combined_note,
        }

        st.success("AI result applied to this item.")

        if photos_key in st.session_state.photos:
            for p in st.session_state.photos[photos_key]:
                st.image(p, caption=f"{item} photo", use_column_width=True)

    st.session_state.inspection_data[(selected_room, item)] = {
        "condition": st.session_state.get(condition_key, "Good"),
        "note": st.session_state.get(note_key, ""),
    }

st.markdown("---")

# ---------- SUMMARY + PDF ----------

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

# ------------------------------
# END OF FILE
# ------------------------------


