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

VISION_ANALYZE_URL = f"{AZURE_VISION_ENDPOINT}/computervision/imageanalysis:analyze?api-version=2023-10-01&features=tags,caption"

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
}

CONDITION_OPTIONS = ["Good", "Fair", "Poor"]

# Tags we care about for PHYSICAL condition only
STRUCTURAL_NEGATIVE_TAGS = {
    "crack",
    "cracked",
    "damage",
    "damaged",
    "broken",
    "stain",
    "stained",
    "dirty",
    "dirt",
    "mold",
    "mould",
    "rust",
    "rusty",
    "peeling",
    "chipped",
    "hole",
    "holes",
    "scratch",
    "scratched",
    "worn",
    "wear",
    "scuff",
    "scuffed",
    "dent",
    "dented",
    "leak",
    "leaking",
    "water damage",
}

STRUCTURAL_MINOR_TAGS = {
    "worn",
    "wear",
    "scuff",
    "scuffed",
    "chipped",
    "scratch",
    "scratched",
    "discoloration",
    "discoloured",
    "faded",
}

STRUCTURAL_POSITIVE_TAGS = {
    "clean",
    "intact",
    "undamaged",
    "new",
    "well maintained",
    "good condition",
}

# Tags to ignore (tenant belongings, clutter, personal items)
IGNORED_TAGS = {
    "cluttered",
    "messy",
    "clothes",
    "clothing",
    "bed",
    "blanket",
    "pillow",
    "box",
    "boxes",
    "furniture",
    "sofa",
    "chair",
    "table",
    "personal items",
    "decor",
    "decoration",
    "toys",
    "laptop",
    "phone",
    "bag",
    "bags",
    "shoes",
    "books",
    "bedding",
    "laundry",
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

    caption_text = ""
    if "captionResult" in result and "text" in result["captionResult"]:
        caption_text = result["captionResult"]["text"]

    return tags, caption_text

# ---------- CONDITION + NOTE LOGIC (NO AI, CONDITION ONLY) ----------

def derive_condition_and_note(tags, caption_text, item_name):
    # Filter tags: ignore non-structural / clutter / belongings
    structural_tags = []
    for name, conf in tags:
        if name in IGNORED_TAGS:
            continue
        structural_tags.append((name, conf))

    # Determine severity
    has_severe = False
    has_minor = False
    has_positive = False

    negative_hits = []
    minor_hits = []
    positive_hits = []

    for name, conf in structural_tags:
        if name in STRUCTURAL_NEGATIVE_TAGS:
            has_severe = True
            negative_hits.append(name)
        elif name in STRUCTURAL_MINOR_TAGS:
            has_minor = True
            minor_hits.append(name)
        elif name in STRUCTURAL_POSITIVE_TAGS:
            has_positive = True
            positive_hits.append(name)

    # Condition scoring
    if has_severe:
        condition = "Poor"
    elif has_minor:
        condition = "Fair"
    else:
        condition = "Good"

    # Build note (medium detail, condition-only)
    note_parts = []

    # If we have a caption, but we must strip clutter-like language
    clean_caption = caption_text
    for word in ["cluttered", "messy", "clothes", "bedding", "boxes", "personal items"]:
        clean_caption = clean_caption.replace(word, "").replace(word.capitalize(), "")

    clean_caption = clean_caption.strip()

    if condition == "Good":
        if positive_hits:
            note_parts.append(
                f"{item_name} appears in good condition with no significant visible damage."
            )
        else:
            note_parts.append(
                f"{item_name} appears to be in acceptable condition with no obvious defects noted."
            )
    elif condition == "Fair":
        if minor_hits:
            note_parts.append(
                f"Minor wear or cosmetic issues observed on the {item_name}, such as {', '.join(set(minor_hits))}."
            )
        else:
            note_parts.append(
                f"Some general wear is visible on the {item_name}, but it remains functional."
            )
    else:  # Poor
        if negative_hits:
            note_parts.append(
                f"Visible damage or significant issues observed on the {item_name}, including {', '.join(set(negative_hits))}. Repair is recommended."
            )
        else:
            note_parts.append(
                f"The {item_name} shows notable damage or deterioration. Further assessment and repair are recommended."
            )

    if clean_caption:
        note_parts.append(f"(Visual summary: {clean_caption}.)")

    note = " ".join(note_parts)
    return condition, note

def analyze_photo_condition_only(image_file, item_name):
    tags, caption_text = analyze_with_azure(image_file)
    return derive_condition_and_note(tags, caption_text, item_name)

# ---------- PDF GENERATION ----------

class InspectionPDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 14)
        self.cell(0, 10, "Inspection Report", ln=True, align="C")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

def generate_pdf(property_name, unit_name, inspection_type, data, photos_dict):
    pdf = InspectionPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, f"Property: {property_name}", ln=True)
    pdf.cell(0, 8, f"Unit: {unit_name}", ln=True)
    pdf.cell(0, 8, f"Inspection Type: {inspection_type}", ln=True)
    pdf.cell(0, 8, f"Date: {datetime.date.today().isoformat()}", ln=True)
    pdf.ln(5)

    current_room = None
    for row in data:
        room = row["room"]
        item = row["item"]
        condition = row["condition"]
        note = row["note"]

        if room != current_room:
            current_room = room
            pdf.set_font("Arial", "B", 12)
            pdf.ln(4)
            pdf.cell(0, 8, room, ln=True)
            pdf.set_font("Arial", "", 11)

        pdf.cell(0, 6, f"- {item}: {condition}", ln=True)
        if note:
            pdf.set_font("Arial", "I", 10)
            pdf.multi_cell(0, 5, f"  Note: {note}")
            pdf.set_font("Arial", "", 11)

    # Photos section
    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Photos", ln=True)
    pdf.ln(4)

    for key, files in photos_dict.items():
        room, item = key
        if not files:
            continue
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 6, f"{room} - {item}", ln=True)
        pdf.set_font("Arial", "", 10)

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

                pdf.image(temp_path, w=80)
                pdf.ln(2)

                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            except Exception:
                continue

        pdf.ln(4)

    return pdf.output(dest="S").encode("latin-1")

# ---------- SESSION STATE ----------

if "inspection_data" not in st.session_state:
    st.session_state.inspection_data = {}  # (room, item) -> {"condition": ..., "note": ...}

if "photos" not in st.session_state:
    st.session_state.photos = {}  # (room, item) -> [files]

# ---------- SIDEBAR: SETUP ----------

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
    st.sidebar.success("Inspection data cleared.")

# ---------- MAIN HEADER ----------

st.title("AI-Powered Inspection App (Azure Vision, Condition-Only)")

st.markdown(
    f"**Property:** {property_name} &nbsp;&nbsp; | &nbsp;&nbsp; "
    f"**Unit:** {unit_name} &nbsp;&nbsp; | &nbsp;&nbsp; "
    f"**Type:** {inspection_type}"
)

st.markdown("---")

# ---------- ROOM VIEW ----------

current_room_struct = next(r for r in template_rooms if r["room"] == selected_room)
items = current_room_struct["items"]

st.header(selected_room)

for item in items:
    key_prefix = f"{selected_room}_{item}"

    st.subheader(item)

    cols = st.columns([1, 2])

    # LEFT: Condition + Notes
    with cols[0]:
        condition_key = f"{key_prefix}_condition"
        note_key = f"{key_prefix}_note"

        current_condition = st.session_state.inspection_data.get(
            (selected_room, item), {}
        ).get("condition", "Good")

        condition = st.radio(
            "Condition",
            CONDITION_OPTIONS,
            index=CONDITION_OPTIONS.index(current_condition)
            if current_condition in CONDITION_OPTIONS
            else 0,
            key=condition_key,
            horizontal=True,
        )

        note_default = st.session_state.inspection_data.get(
            (selected_room, item), {}
        ).get("note", "")

        note = st.text_area(
            "Notes",
            value=note_default,
            key=note_key,
            placeholder=f"Add any notes about the {item.lower()}...",
        )

    # RIGHT: Photos + Azure Analysis
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

        if photos_key in st.session_state.photos:
            for p in st.session_state.photos[photos_key]:
                st.image(p, caption=f"{item} photo", use_column_width=True)

        st.markdown("**AI Photo Analysis (Azure, Condition Only)**")
        ai_photo = st.file_uploader(
            f"Upload a photo of the {item} for condition analysis",
            type=["jpg", "jpeg", "png"],
            key=f"{key_prefix}_ai_photo",
        )

        if ai_photo and st.button(
            f"Analyze {item} Photo with Azure", key=f"{key_prefix}_analyze"
        ):
            try:
                with st.spinner("Analyzing photo with Azure Vision..."):
                    ai_condition, ai_note = analyze_photo_condition_only(ai_photo, item)

                st.success(f"Suggested Condition: {ai_condition}")
                st.info(f"Suggested Note: {ai_note}")

                if st.button(
                    f"Use Azure result for {item}", key=f"{key_prefix}_apply_ai"
                ):
                    st.session_state[condition_key] = ai_condition
                    st.session_state[note_key] = ai_note
                    st.session_state.inspection_data[(selected_room, item)] = {
                        "condition": ai_condition,
                        "note": ai_note,
                    }
                    st.success("Azure result applied to this item.")
            except Exception as e:
                st.error(f"Azure analysis failed: {e}")

    # Save manual edits
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
