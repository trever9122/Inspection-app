# ---------- ITEM LOOP (FULLY UPDATED WITH AUTO‑APPLY AI) ----------

for item in items:
    key_prefix = f"{selected_room}_{item}"

    st.subheader(item)

    cols = st.columns([1, 2])

    # -------------------------
    # LEFT COLUMN: CONDITION + NOTES
    # -------------------------
    with cols[0]:
        condition_key = f"{key_prefix}_condition"
        note_key = f"{key_prefix}_note"

        # Load existing saved values
        saved_data = st.session_state.inspection_data.get((selected_room, item), {})
        current_condition = saved_data.get("condition", "Good")
        current_note = saved_data.get("note", "")

        # Condition selector
        condition = st.radio(
            "Condition",
            CONDITION_OPTIONS,
            index=CONDITION_OPTIONS.index(current_condition),
            key=condition_key,
            horizontal=True,
        )

        # Notes box
        note = st.text_area(
            "Notes",
            value=current_note,
            key=note_key,
            placeholder=f"Add any notes about the {item.lower()}...",
        )

    # -------------------------
    # RIGHT COLUMN: PHOTOS + AI
    # -------------------------
    with cols[1]:
        st.write("**Photos**")

        photos_key = (selected_room, item)

        uploaded_photos = st.file_uploader(
            f"Upload photos for {item}",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key=f"{key_prefix}_photos",
        )

        # If new photos uploaded → run AI
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

                # Save AI results
                st.session_state.ai_results[photos_key] = {
                    "condition": final_condition,
                    "note": combined_note,
                }

                # -----------------------------------------
                # AUTO‑APPLY AI RESULTS (SAFE FOR STREAMLIT)
                # -----------------------------------------
                st.session_state[condition_key] = final_condition
                st.session_state[note_key] = combined_note

                st.success(f"AI Suggested Condition: {final_condition}")
                st.info("AI Suggested Notes:\n" + combined_note)
                st.success("AI result applied automatically. You can edit the note below.")

        # Show thumbnails
        if photos_key in st.session_state.photos:
            for p in st.session_state.photos[photos_key]:
                st.image(p, caption=f"{item} photo", use_column_width=True)

    # -------------------------
    # ALWAYS SAVE LATEST WIDGET VALUES
    # -------------------------
    st.session_state.inspection_data[(selected_room, item)] = {
        "condition": st.session_state.get(condition_key, "Good"),
        "note": st.session_state.get(note_key, ""),
    }
