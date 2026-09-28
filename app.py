import os
import tempfile
from typing import Dict, List, Optional, Tuple
from pyvis.network import Network
import psycopg2
from psycopg2.extras import RealDictCursor
import streamlit as st
import streamlit.components.v1 as components

# ==========================================
# 1. CLOUD DATABASE CONNECTION
# ==========================================


def get_db():
    """Connect to PostgreSQL using Streamlit Secrets or Environment Variable."""
    db_url = st.secrets["postgres"]["db_url"]
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    return conn


def init_db():
    """Initialize PostgreSQL table and seed sample data if empty."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS family_members (
                    id VARCHAR PRIMARY KEY,
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    gender VARCHAR(10) CHECK(gender IN ('M', 'F', 'Other')),
                    birth_date DATE,
                    father_id VARCHAR REFERENCES family_members(id),
                    mother_id VARCHAR REFERENCES family_members(id)
                );
            """)

            cursor.execute("SELECT COUNT(*) as count FROM family_members;")
            row = cursor.fetchone()
            if row["count"] == 0:
                sample_data = [
                    ("101", "Arthur", "Smith", "M", "1940-01-01", None, None),
                    ("102", "Robert", "Smith", "M", "1965-05-12", "101", None),
                    ("103", "David", "Smith", "M", "1988-08-20", "102", None),
                    ("104", "Mark", "Smith", "M", "1990-11-15", "102", None),
                    ("105", "Alice", "Smith", "F", "2010-03-10", "103", None),
                    ("106", "Bob", "Smith", "M", "2012-07-25", "103", None),
                    ("107", "Charlie", "Smith", "M", "2014-02-18", "104", None),
                    ("108", "Daniel", "Smith", "M", "2032-09-01", "107", None),
                ]
                for member in sample_data:
                    cursor.execute(
                        """
                        INSERT INTO family_members (id, first_name, last_name, gender, birth_date, father_id, mother_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING;
                    """,
                        member,
                    )
        conn.commit()


init_db()

# ==========================================
# 2. TRANSLATIONS DICTIONARY
# ==========================================
TRANSLATIONS = {
    "en": {
        "title": "🌳 Family Tree & Kinship Explorer",
        "subtitle": "Connect family members, trace lineage, and calculate exact relationships.",
        "add_tab": "➕ Add / Edit Member",
        "calc_tab": "🔍 Kinship Calculator",
        "tree_tab": "🌐 Visual Family Tree",
        "first_name": "First Name",
        "last_name": "Last Name",
        "gender": "Gender",
        "birth_date": "Birth Date (YYYY-MM-DD)",
        "father": "Select Father (Optional)",
        "mother": "Select Mother (Optional)",
        "member_id": "Member ID (Unique)",
        "save_btn": "Save Member to Tree",
        "select_p1": "Select First Person",
        "select_p2": "Select Second Person",
        "calculate": "Calculate Relationship",
        "result": "Relationship Result",
        "none_option": "None",
        "saved_msg": "Member saved successfully to Cloud DB!",
        "required_err": "Member ID, First Name, and Last Name are required.",
    },
    "rw": {
        "title": "🌳 Igiti cy'Umuryango n'Isano",
        "subtitle": "Huza abanyamuryango, shakisha inkomoko, kandi ubare isano nyakuri iri hagati yabo.",
        "add_tab": "➕ Ongeramo / Hindura Umuntu",
        "calc_tab": "🔍 Shakisha Isano",
        "tree_tab": "🌐 Igiti cy'Umuryango mu Shusho",
        "first_name": "Izina rya Mbere",
        "last_name": "Izina ry'Umuryango",
        "gender": "Igitsina",
        "birth_date": "Itariki y'amavuko (YYYY-MM-DD)",
        "father": "Hitamo Papa / Data (Niba ahari)",
        "mother": "Hitamo Mama / Nyina (Niba ahari)",
        "member_id": "Numero Iranga Umuntu (ID)",
        "save_btn": "Bika mu Muryango",
        "select_p1": "Hitamo Umuntu wa Mbere",
        "select_p2": "Hitamo Umuntu wa Kabiri",
        "calculate": "Shakisha Isano",
        "result": "Igisubizo cy'Isano",
        "none_option": "Ntawe",
        "saved_msg": "Umuntu yaguzwe neza muri Cloud Database!",
        "required_err": "ID, Izina rya Mbere, n'izina ry'umuryango birakenewe.",
    },
}

# ==========================================
# 3. KINSHIP ENGINE (PostgreSQL Compatible)
# ==========================================


class KinshipEngine:

    @staticmethod
    def get_all_ancestors(
        conn, person_id: str
    ) -> Dict[str, Tuple[int, List[str]]]:
        ancestors = {person_id: (0, [person_id])}
        queue = [(person_id, 0, [person_id])]

        while queue:
            current_id, depth, path = queue.pop(0)
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT father_id, mother_id FROM family_members WHERE id = %s;",
                    (current_id,),
                )
                row = cursor.fetchone()

            if not row:
                continue

            for parent_id in [row["father_id"], row["mother_id"]]:
                if parent_id and parent_id not in ancestors:
                    new_path = path + [parent_id]
                    ancestors[parent_id] = (depth + 1, new_path)
                    queue.append((parent_id, depth + 1, new_path))

        return ancestors

    @classmethod
    def calculate_relationship(
        cls, conn, id_a: str, id_b: str, lang: str = "rw"
    ) -> str:
        if id_a == id_b:
            return "Ni umuntu umwe" if lang == "rw" else "Same person"

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, first_name, last_name FROM family_members WHERE id IN (%s, %s);",
                (id_a, id_b),
            )
            members = {row["id"]: row for row in cursor.fetchall()}

        if id_a not in members or id_b not in members:
            return (
                "Umuntu umwe cyangwa bose ntababonetse."
                if lang == "rw"
                else "One or both persons not found."
            )

        p_a = members[id_a]
        p_b = members[id_b]

        ancestors_a = cls.get_all_ancestors(conn, id_a)
        ancestors_b = cls.get_all_ancestors(conn, id_b)

        common_ancestors = set(ancestors_a.keys()).intersection(
            set(ancestors_b.keys())
        )

        if not common_ancestors:
            return (
                f"Nta sano izwi iri hagati ya {p_a['first_name']} na {p_b['first_name']}."
                if lang == "rw"
                else f"No known biological relationship between {p_a['first_name']} and {p_b['first_name']}."
            )

        lca_id = min(
            common_ancestors,
            key=lambda ancestor: ancestors_a[ancestor][0]
            + ancestors_b[ancestor][0],
        )

        d_a, _ = ancestors_a[lca_id]
        d_b, _ = ancestors_b[lca_id]

        return cls._format_title(
            p_a["first_name"], p_b["first_name"], d_a, d_b, lang
        )

    @staticmethod
    def _format_title(
        name_a: str, name_b: str, d_a: int, d_b: int, lang: str
    ) -> str:
        if d_a == 0:
            if d_b == 1:
                return (
                    f"{name_a} ni umubyeyi wa {name_b}"
                    if lang == "rw"
                    else f"{name_a} is the Parent of {name_b}"
                )
            if d_b == 2:
                return (
                    f"{name_a} ni sogokuru/nyirakuru wa {name_b}"
                    if lang == "rw"
                    else f"{name_a} is the Grandparent of {name_b}"
                )
            if d_b == 3:
                return (
                    f"{name_a} ni bisogokuru/binyirakuru wa {name_b}"
                    if lang == "rw"
                    else f"{name_a} is the Great-Grandparent of {name_b}"
                )
            return (
                f"{name_a} ni sekuruza wa {name_b}"
                if lang == "rw"
                else f"{name_a} is a Direct Ancestor of {name_b}"
            )

        if d_b == 0:
            if d_a == 1:
                return (
                    f"{name_a} ni umwana wa {name_b}"
                    if lang == "rw"
                    else f"{name_a} is the Child of {name_b}"
                )
            if d_a == 2:
                return (
                    f"{name_a} ni umwuzukuru wa {name_b}"
                    if lang == "rw"
                    else f"{name_a} is the Grandchild of {name_b}"
                )
            if d_a == 3:
                return (
                    f"{name_a} ni umwuzukuruza wa {name_b}"
                    if lang == "rw"
                    else f"{name_a} is the Great-Grandchild of {name_b}"
                )
            return (
                f"{name_a} ni umukomokozwa wa {name_b}"
                if lang == "rw"
                else f"{name_a} is a Direct Descendant of {name_b}"
            )

        if d_a == 1 and d_b == 1:
            return (
                f"{name_a} na {name_b} ni abavandimwe"
                if lang == "rw"
                else f"{name_a} and {name_b} are Siblings"
            )

        if d_a == 1 and d_b > 1:
            if d_b == 2:
                return (
                    f"{name_a} ni marume / nyirasenge (shangazi) / data wacu wa {name_b}"
                    if lang == "rw"
                    else f"{name_a} is the Aunt/Uncle of {name_b}"
                )
            return (
                f"{name_a} ni umuvandimwe w'umubyeyi wa {name_b}"
                if lang == "rw"
                else f"{name_a} is a Great-Aunt/Uncle of {name_b}"
            )

        if d_b == 1 and d_a > 1:
            if d_a == 2:
                return (
                    f"{name_a} ni umwisengeneza / umwishywa wa {name_b}"
                    if lang == "rw"
                    else f"{name_a} is the Niece/Nephew of {name_b}"
                )
            return (
                f"{name_a} ni umukomoko ku muvandimwe wa {name_b}"
                if lang == "rw"
                else f"{name_a} is a Great-Niece/Nephew of {name_b}"
            )

        degree = min(d_a, d_b) - 1
        removed = abs(d_a - d_b)

        if lang == "rw":
            rem_text = (
                f" (irutanwa rya bisekuru {removed})" if removed > 0 else ""
            )
            return f"{name_a} na {name_b} ni ababyara{rem_text}"

        ordinals = {1: "1st", 2: "2nd", 3: "3rd"}
        deg_str = ordinals.get(degree, f"{degree}th")
        rem_str = (
            ""
            if removed == 0
            else f" {removed} time{'s' if removed > 1 else ''} removed"
        )
        return f"{name_a} and {name_b} are {deg_str} Cousins{rem_str}"


# ==========================================
# 4. STREAMLIT INTERFACE
# ==========================================
st.set_page_config(
    page_title="Family Tree & Kinship Engine", page_icon="🌳", layout="wide"
)

lang_choice = st.sidebar.radio("🌐 Ururimi / Language", ["Ikinyarwanda", "English"])
lang_code = "rw" if lang_choice == "Ikinyarwanda" else "en"
t = TRANSLATIONS[lang_code]

st.title(t["title"])
st.caption(t["subtitle"])


def get_all_members():
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM family_members;")
            return cursor.fetchall()


members = get_all_members()
member_options = {
    f"{m['first_name']} {m['last_name']} (ID: {m['id']})": m["id"]
    for m in members
}

tab1, tab2, tab3 = st.tabs([t["add_tab"], t["calc_tab"], t["tree_tab"]])

# --- TAB 1: ADD / EDIT MEMBER ---
with tab1:
    st.header(t["add_tab"])
    with st.form("member_form"):
        col1, col2 = st.columns(2)
        with col1:
            m_id = st.text_input(t["member_id"], placeholder="e.g. 109")
            f_name = st.text_input(t["first_name"], placeholder="e.g. Eric")
            l_name = st.text_input(t["last_name"], placeholder="e.g. Mugisha")
            gnd = st.selectbox(t["gender"], ["M", "F", "Other"])

        with col2:
            b_date = st.text_input(t["birth_date"], placeholder="1995-06-15")
            fat_sel = st.selectbox(
                t["father"], [t["none_option"]] + list(member_options.keys())
            )
            mot_sel = st.selectbox(
                t["mother"], [t["none_option"]] + list(member_options.keys())
            )

        submit_btn = st.form_submit_button(t["save_btn"])

        if submit_btn:
            if not m_id or not f_name or not l_name:
                st.error(t["required_err"])
            else:
                f_id = (
                    member_options[fat_sel]
                    if fat_sel != t["none_option"]
                    else None
                )
                m_id_val = (
                    member_options[mot_sel]
                    if mot_sel != t["none_option"]
                    else None
                )
                b_date_val = b_date if b_date.strip() != "" else None

                with get_db() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO family_members (id, first_name, last_name, gender, birth_date, father_id, mother_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT(id) DO UPDATE SET
                                first_name=EXCLUDED.first_name,
                                last_name=EXCLUDED.last_name,
                                gender=EXCLUDED.gender,
                                birth_date=EXCLUDED.birth_date,
                                father_id=EXCLUDED.father_id,
                                mother_id=EXCLUDED.mother_id;
                        """,
                            (
                                m_id,
                                f_name,
                                l_name,
                                gnd,
                                b_date_val,
                                f_id,
                                m_id_val,
                            ),
                        )
                    conn.commit()
                st.success(t["saved_msg"])
                st.rerun()

# --- TAB 2: KINSHIP CALCULATOR ---
with tab2:
    st.header(t["calc_tab"])
    if len(member_options) < 2:
        st.info("Shyiramo abantu nibura 2 ngo ubare isano.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            p1 = st.selectbox(t["select_p1"], list(member_options.keys()), key="p1")
        with c2:
            p2 = st.selectbox(t["select_p2"], list(member_options.keys()), key="p2")

        if st.button(t["calculate"], type="primary"):
            id1 = member_options[p1]
            id2 = member_options[p2]

            with get_db() as conn:
                rel_str = KinshipEngine.calculate_relationship(
                    conn, id1, id2, lang=lang_code
                )
            st.subheader(t["result"])
            st.success(f"**{rel_str}**")

# --- TAB 3: VISUAL GRAPH ---
with tab3:
    st.header(t["tree_tab"])
    if st.button("Refresh / Vugurura Shusho"):
        st.rerun()

    if not members:
        st.info("Nta muryango urandikwa.")
    else:
        net = Network(height="550px", width="100%", directed=True)
        net.toggle_physics(True)

        for m in members:
            gender = m["gender"]
            color = (
                "#97C2FC"
                if gender == "M"
                else ("#FFC0CB" if gender == "F" else "#FFFF00")
            )
            net.add_node(
                m["id"],
                label=f"{m['first_name']} {m['last_name']}\n(ID: {m['id']})",
                color=color,
                shape="ellipse",
            )

        for m in members:
            if m["father_id"]:
                net.add_edge(
                    m["father_id"],
                    m["id"],
                    title="Papa / Father",
                    arrows="to",
                )
            if m["mother_id"]:
                net.add_edge(
                    m["mother_id"],
                    m["id"],
                    title="Mama / Mother",
                    arrows="to",
                )

        tmp_dir = tempfile.gettempdir()
        html_path = os.path.join(tmp_dir, "family_tree.html")
        net.save_graph(html_path)

        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        components.html(html_content, height=600, scrolling=True)