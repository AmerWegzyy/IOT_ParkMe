import streamlit as st
import sqlite3
import hashlib
import pandas as pd

st.set_page_config(page_title="ParkMe - Campus Parking System", page_icon="🅿️", layout="centered")

DB_FILE = "parkme.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user_info" not in st.session_state:
    st.session_state["user_info"] = None

def show_auth_page():
    st.title("🅿️ ParkMe @ Technion")
    st.subheader("Smart Parking Management Platform")
    
    tab_login, tab_signup = st.tabs(["🔒 Secure Login", "📝 Create Account"])
    
    with tab_login:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        
        if st.button("Log In", use_container_width=True):
            conn = get_db_connection()
            user = conn.execute(
                "SELECT * FROM users WHERE username = ? AND password_hash = ?", 
                (username, hash_password(password))
            ).fetchone()
            conn.close()
            
            if user:
                st.session_state["logged_in"] = True
                st.session_state["user_info"] = {
                    "id": user["user_id"],
                    "name": user["name"],
                    "role": user["user_type"],
                    "is_looking": bool(user["is_looking"])
                }
                st.success(f"Welcome back, {user['name']}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with tab_signup:
        new_name = st.text_input("Full Name")
        new_username = st.text_input("Choose Username")
        new_password = st.text_input("Create Password", type="password")
        # UPDATED: Changed choice to 'faculty member'
        new_role = st.selectbox("I am a...", ["student", "faculty member"])
        associated_plate = st.text_input("Vehicle License Plate (e.g., 123-45-678)")
        
        if st.button("Register Account", use_container_width=True):
            if not new_name or not new_username or not new_password or not associated_plate:
                st.warning("Please fill out all mandatory registration boxes.")
                return
                
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (name, username, password_hash, user_type) VALUES (?, ?, ?, ?)",
                    (new_name, new_username, hash_password(new_password), new_role)
                )
                new_uid = cursor.lastrowid
                
                cursor.execute(
                    "INSERT INTO vehicles (license_plate, user_id) VALUES (?, ?)",
                    (associated_plate, new_uid)
                )
                conn.commit()
                st.success("Account created successfully! Please head to the Log In tab.")
            except sqlite3.IntegrityError:
                st.error("Username or license plate already registered in the system.")
            finally:
                conn.close()

def show_driver_dashboard():
    user = st.session_state["user_info"]
    st.title(f"🚗 Driver Dashboard")
    st.write(f"Logged in as: **{user['name']}** ({user['role'].title()})")
    
    st.markdown("---")
    st.subheader("Your Parking Status")
    
    is_looking_check = st.checkbox(
        "🚨 I am actively looking for a parking spot right now", 
        value=user["is_looking"]
    )
    
    if is_looking_check != user["is_looking"]:
        conn = get_db_connection()
        conn.execute("UPDATE users SET is_looking = ? WHERE user_id = ?", (int(is_looking_check), user["id"]))
        conn.commit()
        conn.close()
        st.session_state["user_info"]["is_looking"] = is_looking_check
        st.toast("Your search status has been updated in the system map!", icon="🔄")

    st.markdown("---")
    st.subheader("📍 Live Parking Availability Map")
    
    conn = get_db_connection()
    spots = conn.execute("SELECT * FROM parking_spots").fetchall()
    conn.close()
    
    cols = st.columns(len(spots))
    for index, spot in enumerate(spots):
        with cols[index]:
            if spot["status"] == 0:
                st.metric(label=f"Spot {spot['spot_id']}", value="FREE")
                st.success(f"🟢 {spot['spot_type'].title()}")
            else:
                st.metric(label=f"Spot {spot['spot_id']}", value="BUSY")
                st.error(f"🔴 Occupied")

def show_admin_dashboard():
    st.title("🛡️ Technion Security Control Center")
    st.write("System Admin Overview & Log Diagnostics")
    
    conn = get_db_connection()
    
    st.markdown("---")
    st.subheader("🔋 Distributed Hardware Node Metrics")
    spots_data = conn.execute("SELECT spot_id, spot_type, battery_level, last_seen FROM parking_spots").fetchall()
    
    for spot in spots_data:
        battery = spot["battery_level"]
        if battery >= 50:
            bat_icon, text_color = "🟢", "healthy"
        elif 15 <= battery < 50:
            bat_icon, text_color = "⚠️", "low"
        else:
            bat_icon, text_color = "🪫", "critical swap needed"
            
        st.write(f"**Spot Node {spot['spot_id']}** ({spot['spot_type'].title()} Layout) — Battery status: {bat_icon} **{battery}%** ({text_color}) | Last Ping: *{spot['last_seen']}*")

    st.markdown("---")
    st.subheader("📋 System Incident History Logs")
    logs_data = conn.execute("SELECT * FROM parking_logs ORDER BY timestamp DESC").fetchall()
    conn.close()
    
    if logs_data:
        df_logs = pd.DataFrame([dict(log) for log in logs_data])
        st.dataframe(df_logs, use_container_width=True)
    else:
        st.info("No active activity events logged within the current period.")

if not st.session_state["logged_in"]:
    show_auth_page()
else:
    st.sidebar.title("Navigation")
    if st.sidebar.button("Log Out Securely"):
        st.session_state["logged_in"] = False
        st.session_state["user_info"] = None
        st.rerun()
        
    if st.session_state["user_info"]["role"] == "admin":
        show_admin_dashboard()
    else:
        show_driver_dashboard()