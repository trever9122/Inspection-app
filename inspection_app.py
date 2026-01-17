import streamlit as st
import json
from datetime import datetime
from pathlib import Path
from fpdf import FPDF
from st_dragdrop_list import ST_DragDropList  # pip install streamlit-dragdroplist

# -------------------------------------------------
# CONFIG
# -------------------------------------------------
st.set_page_config(page_title="Property Inspection App", layout="wide")

INSPECTION_TYPES = [
    "Semi-Annual Inspection",
    "Empty Unit Inspection",
    "Move-In Inspection",
    "Move-Out Inspection",
    "Yard/Exterior Inspection",
]

BASE_ROOMS = [
    "Bedroom",
    "Hall",
    "Kitchen",
    "Bathroom",
    "Basement",
    "Living Room",
    "Dining Room",
    "Yard / Exterior",
]

ROOM_ICONS = {
    "Bedroom": "🛏️",
    "Hall": "🚪",
    "Kitchen": "🍽️",
    "Bathroom": "🚿",
    "Basement": "🏚️",
    "Living Room": "🛋️",
    "Dining Room": "🍴",
    "Yard / Exterior": "🌳",
}

CONDITION_OPTIONS = ["Good", "Fair", "Poor", "Bad"]

# Cloud‑sync friendly save folder (OneDrive by default)
SAVE_DIR = Path.home() / "OneDrive" / "Inspections"
SAVE_DIR.mkdir(parents=True, exist_ok=True)


# -------------------------------------------------
# SESSION STATE
# -------------------------------------------------
if "custom_rooms" not in st.session_state:
    st.session_state.custom_rooms = []

if "units" not in st.session_state:
    st.session_state.units = []

if "current_unit" not in st.session_state:
    st.session_state.current_unit = None


# -------------------------------------------------
# HELPERS
# -------------------------------------------------
def room_key(room_name: str) -> str:
    return room_name.lower().replace(" ", "_").replace("/", "_")


def suggest_notes(room, condition):
    base = room.lower()
    if condition == "Good":
        return f"The {base} appears to be in good working order with no visible defects."
    if condition == "Fair":
        return f"The {base} shows minor wear consistent with normal use. No urgent repairs required."
    if condition == "Poor":
        return f"The {base} has noticeable issues that may require maintenance attention."
    if condition == "Bad":
        return f"The {base} contains significant deficiencies that require prompt repair or replacement."
    return ""


def save_report(report: dict) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unit_part = report['unit_number'].replace(" ", "_") if report['unit_number'] else "unit"
    filename = f"{report['property_name'].replace(' ', '_')}_{unit_part}_{timestamp}.json"
    filepath = SAVE_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    return filepath


def generate_pdf(report: dict) -> Path:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Property Inspection Report", ln=True)

    pdf.set_font("Arial", size=12)
    pdf.ln(5)

    pdf.cell(0, 8, f"Inspection Type: {report['inspection_type']}", ln=True)
    pdf.cell(0, 8, f"Property: {report['property_name']}", ln=True)
    pdf.cell(0, 8, f"Unit: {report['unit_number']}", ln=True)
    pdf.cell(0, 8, f"Inspector: {report['inspector_name']}", ln=True)
    pdf.cell(0, 8, f"Date: {report['inspection_date']}", ln=True)

    pdf.ln(8)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 8, "General Notes:", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 6, report.get("general_notes", "") or "None")

    pdf.ln(6)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 8, "Room Details:", ln=True)

    for room, data in report["rooms"].items():
        pdf.ln(4)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, f"{room}", ln=True)

        pdf.set_font("Arial", size=12)
        pdf.cell(0, 6, f"Condition: {data['condition']}", ln=True)
        pdf.multi_cell(0, 6, f"Notes: {data['notes'] or 'None'}")

    pdf_path = SAVE_DIR / "inspection_report.pdf"
    pdf.output(str(pdf_path))
    return pdf_path


# -------------------------------------------------
# SIDEBAR: SETUP
# -------------------------------------------------
st.sidebar.title("Inspection Setup")

inspection_type = st.sidebar.selectbox("Inspection Type", INSPECTION_TYPES)

property_name = st.sidebar.text_input("Property Name / Address", "")

# Multi-unit support
st.sidebar.markdown("### Units in this Property")
new_unit = st.sidebar.text_input("Add Unit (e.g., 101, BSMT)")
if st.sidebar.button("Add Unit"):
    if new_unit.strip() and new_unit.strip() not in st.session_state.units:
        st.session_state.units.append(new_unit.strip())
        st.session_state.current_unit = new_unit.strip()
        st.sidebar.success(f"Added unit: {new_unit}")
    else:
        st.sidebar.error("Unit name must be unique and not empty.")

if st.session_state.units:
    st.session_state.current_unit = st.sidebar.selectbox(
        "Select Active Unit",
        st.session_state.units,
        index=st.session_state.units.index(st.session_state.current_unit)
        if st.session_state.current_unit in st.session_state.units
        else 0,
    )
unit_number = st.session_state.current_unit or ""

inspector_name = st.sidebar.text_input("Inspector Name", "")
inspection_date = st.sidebar.date_input("Inspection Date", datetime.today())

# Custom rooms
st.sidebar.markdown("### Add Custom Room")
custom_room = st.sidebar.text_input("Custom Room Name")
if st.sidebar.button("Add Room"):
    if custom_room.strip():
        st.session_state.custom_rooms.append(custom_room.strip())
        st.sidebar.success(f"Added room: {custom_room}")
    else:
        st.sidebar.error("Room name cannot be empty.")

# Rooms + drag-and-drop ordering
st.sidebar.markdown("### Rooms / Areas to Inspect")

all_rooms = BASE_ROOMS + st.session_state.custom_rooms
room_data_for_drag = [
    {"id": f"room_{i}", "order": i, "name": r} for i, r in enumerate(all_rooms)
]

dragged_rooms = ST_DragDropList(room_data_for_drag, key="room_order")
ordered_rooms = [item["name"] for item in dragged_rooms]

selected_rooms = []
for r in ordered_rooms:
    if st.sidebar.checkbox(r, value=True, key=f"chk_{r}"):
        selected_rooms.append(r)

st.sidebar.info("Drag rooms to reorder. Check to include in this inspection.")


# -------------------------------------------------
# MAIN LAYOUT
# -------------------------------------------------
st.title("Property Inspection Workspace")

st.write(
    f"**Inspection Type:** {inspection_type}  \n"
    f"**Property:** {property_name or 'N/A'}  \n"
    f"**Active Unit:** {unit_number or 'N/A'}  \n"
    f"**Inspector:** {inspector_name or 'N/A'}  \n"
    f"**Date:** {inspection_date}"
)

st.markdown("---")

if not property_name:
    st.warning("Enter at least a Property Name / Address in the sidebar.")

if not unit_number:
    st.info("Add/select a unit in the sidebar to track multi-unit inspections cleanly.")

with st.form("inspection_form"):
    st.subheader("Overview & General Notes")
    general_notes = st.text_area(
        "Overall comments about the property condition (no personal/tenant details)",
        height=120,
    )

    st.markdown("---")
    st.subheader("Room / Area Details")

    room_data = {}

    for room in selected_rooms:
        key_prefix = room_key(room)
        icon = ROOM_ICONS.get(room, "📍")
        with st.expander(f"{icon} {room}", expanded=False):
            col1, col2 = st.columns([1, 2])

            with col1:
                condition = st.selectbox(
                    f"{room} Condition",
                    CONDITION_OPTIONS,
                    key=f"{key_prefix}_condition",
                )

                suggested = suggest_notes(room, condition)
                auto_notes = st.text_area(
                    f"Suggested Notes ({room})",
                    value=suggested,
                    key=f"{key_prefix}_auto_notes",
                )

                notes = st.text_area(
                    f"Additional Notes ({room})",
                    key=f"{key_prefix}_notes",
                    placeholder=f"Add any extra condition-based details for the {room.lower()}...",
                )

            with col2:
                st.write(f"**{room} Photos**")
                photos = st.file_uploader(
                    f"Upload photos for {room}",
                    type=["png", "jpg", "jpeg"],
                    accept_multiple_files=True,
                    key=f"{key_prefix}_photos",
                )

                if photos:
                    for i, img in enumerate(photos):
                        st.image(img, caption=f"{room} Photo {i+1}", use_column_width=True)

            room_data[room] = {
                "condition": condition,
                "notes": (auto_notes or "") + ("\n\n" + notes if notes else ""),
                "photo_names": [p.name for p in photos] if photos else [],
            }

    st.markdown("---")
    submitted = st.form_submit_button("Save Inspection Report")

if submitted:
    report = {
        "inspection_type": inspection_type,
        "property_name": property_name,
        "unit_number": unit_number,
        "inspector_name": inspector_name,
        "inspection_date": str(inspection_date),
        "general_notes": general_notes,
        "rooms": room_data,
        "created_at": datetime.now().isoformat(),
    }

    json_path = save_report(report)
    st.success(f"Inspection report saved to: `{json_path}`")

    st.subheader("Inspection Overview")

    condition_counts = {c: 0 for c in CONDITION_OPTIONS}
    for _, data in report["rooms"].items():
        condition_counts[data["condition"]] += 1

    st.write("### Condition Summary")
    st.bar_chart(condition_counts)

    st.write("### Room Breakdown")
    for room, data in report["rooms"].items():
        st.write(f"**{room}:** {data['condition']}")

    st.subheader("Raw Report Data")
    st.json(report)

    st.markdown("---")
    st.subheader("Export")

    pdf_path = generate_pdf(report)
    st.success(f"PDF generated at: `{pdf_path}`")

    with open(pdf_path, "rb") as f:
        st.download_button(
            "Download PDF (Landlord / Tenant / Buildium)",
            f,
            file_name=f"inspection_{property_name}_{unit_number}.pdf",
            mime="application/pdf",
        )