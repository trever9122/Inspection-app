import streamlit as st
from PIL import Image
import io
import base64
import pandas as pd
from fpdf import FPDF
from openai import OpenAI
import datetime
import os

# ---------- CONFIG ----------

st.set_page_config(page_title="AI Inspection App", layout="wide")

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

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

# ---------- AI PHOTO ANALYSIS (NEW OPENAI API) ----------

def analyze_photo(image_file):
    img = Image.open(image_file).convert("RGB")
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG")
    img_bytes = buffered.getvalue()
    img_b64 = base64.b64encode(img_bytes).decode()

    prompt = (
        "You are an expert property inspector. Analyze this inspection photo and return:\n"
        "1. Condition rating: Good, Fair, or Poor.\n"
        "2. A professional inspection note describing any visible damage, wear, cleanliness issues, or concerns.\n\n"
        "Format:\n"
        "Condition: <Good/Fair/Poor>\n"
        "Note: <one or two sentences>"
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": f"data:image/jpeg;base64,{img_b64}",
                    },
                ],
            }
        ],
    )

    ai_text = response.choices[0].message.content
    lines = [l.strip() for l in ai_text.split("\n") if l.strip()]
    condition = "Fair"
    note = ""

    for line in lines:
        if line.lower().startswith("condition:"):
            condition = line.split(":", 1)[1].strip()
        if line.lower().startswith("note:"):
            note = line.split(":", 1)[1].strip()

    if condition not in CONDITION_OPTIONS:
        condition = "Fair"

    return condition, note

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

st.title("AI-Powered Inspection App (HappyCo-style Prototype)")

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

    # RIGHT: Photos + AI
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

        st.markdown("**AI Photo Analysis**")
        ai_photo = st.file_uploader(
            f"Upload a photo of the {item} for AI analysis",
            type=["jpg", "jpeg", "png"],
            key=f"{key_prefix}_ai_photo",
        )

        if ai_photo and st.button(
            f"Analyze {item} Photo with AI", key=f"{key_prefix}_analyze"
        ):
            with st.spinner("Analyzing photo with AI..."):
                ai_condition, ai_note = analyze_photo(ai_photo)

            st.success(f"AI Condition: {ai_condition}")
            st.info(f"AI Note: {ai_note}")

            if st.button(
                f"Use AI result for {item}", key=f"{key_prefix}_apply_ai"
            ):
                st.session_state[condition_key] = ai_condition
                st.session_state[note_key] = ai_note
                st.session_state.inspection_data[(selected_room, item)] = {
                    "condition": ai_condition,
                    "note": ai_note,
                }
                st.success("AI result applied to this item.")

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
