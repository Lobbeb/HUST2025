from gevent import monkey
monkey.patch_all()  # Patch for gevent compatibility

import pymysql
import time
import datetime
from flask import Flask, render_template, make_response, request, jsonify
from flask_socketio import SocketIO
from threading import Event

# ============ CONFIG ============
DB_HOST = "194.47.13.187"    # e.g. "194.47.13.187"
DB_USER = "remoteuser"
DB_PASSWORD = "mhsRuS84s6K6baslP9G7LGH"
DB_NAME = "Hust"

# Flask Setup
app = Flask(__name__)
app.config["SECRET_KEY"] = "whatever_you_want_here"

# SocketIO Setup (Gevent)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

# Background thread control
thread_stop_event = Event()

# Latest data stored for real-time SocketIO pushes
latest_data = {
    "battery_data": [],
    "motor_data": [],
    "mppt_data": [],
    "vehicle_data": []
}

# -------------------------------------------
# HELPER FUNCTIONS
# -------------------------------------------
def connect_db():
    """Connect to MySQL/MariaDB with DictCursor."""
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

def convert_timestamps(rows):
    """ Convert MySQL datetime objects to strings for JSON serialization. """
    for row in rows:
        if "timestamp" in row and isinstance(row["timestamp"], datetime.datetime):
            row["timestamp"] = row["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
    return rows

def fetch_all_data(limit=20):
    """
    Fetch Battery, Motor, MPPT, Vehicle data from DB.
    Returns a dict with keys: battery_data, motor_data, mppt_data, vehicle_data.
    """
    data = {
        "battery_data": [],
        "motor_data": [],
        "mppt_data": [],
        "vehicle_data": []
    }
    conn = None
    try:
        conn = connect_db()
        with conn.cursor() as cur:
            # Battery
            cur.execute(f"""
                SELECT id, timestamp, battery_volt, battery_current,
                       battery_cell_low_volt, battery_cell_high_volt, battery_cell_average_volt,
                       battery_cell_low_temp, battery_cell_high_temp, battery_cell_average_temp,
                       battery_cell_high_temp_ID, battery_cell_low_temp_ID
                FROM `Battery Data Table`
                ORDER BY id DESC
                LIMIT {limit};
            """)
            battery_rows = convert_timestamps(cur.fetchall())
            data["battery_data"] = battery_rows

            # Motor
            cur.execute(f"""
                SELECT id, timestamp, motor_current, motor_temp, motor_controller_temp
                FROM `Motor Data Table`
                ORDER BY id DESC
                LIMIT {limit};
            """)
            motor_rows = convert_timestamps(cur.fetchall())
            data["motor_data"] = motor_rows

            # MPPT
            cur.execute(f"""
                SELECT id, timestamp, MPPT1_watt, MPPT2_watt, MPPT3_watt, MPPT_total_watt
                FROM `MPPT Data Table`
                ORDER BY id DESC
                LIMIT {limit};
            """)
            mppt_rows = convert_timestamps(cur.fetchall())
            data["mppt_data"] = mppt_rows

            # Vehicle
            cur.execute(f"""
                SELECT id, timestamp, velocity, distance_travelled
                FROM `Vehicle Data Table`
                ORDER BY id DESC
                LIMIT {limit};
            """)
            vehicle_rows = convert_timestamps(cur.fetchall())
            data["vehicle_data"] = vehicle_rows

    except Exception as e:
        print("DB Error in fetch_all_data:", e)
    finally:
        if conn and conn.open:
            conn.close()

    return data

# -------------------------------------------
# BACKGROUND TASK FOR REAL-TIME UPDATES
# -------------------------------------------
def background_data_fetcher():
    """
    Continuously fetch data every 2 seconds and emit via Socket.IO.
    Stores the latest 20 rows in `latest_data`.
    """
    global latest_data
    while not thread_stop_event.is_set():
        time.sleep(2)

        # Fetch 20 rows for real-time
        new_data = fetch_all_data(limit=20)
        if any(new_data.values()):  # If we got valid data
            latest_data = new_data
        # Emit to connected clients
        socketio.emit("new_data", latest_data)

# -------------------------------------------
# ROUTES
# -------------------------------------------
@app.route("/")
def index():
    """Serves the main HTML page with Chart.js & Socket.IO scripts."""
    return render_template("index.html")

@app.route("/data")
def get_data():
    """
    JSON Endpoint:
    e.g. /data?limit=50
    Returns up to 'limit' rows from each table.
    """
    limit = request.args.get("limit", default=20, type=int)
    data = fetch_all_data(limit=limit)
    return jsonify(data)

@app.route("/export_csv")
def export_csv():
    """
    CSV export route for Battery & Motor data (20 rows).
    """
    csv_lines = ["Table,ID,Timestamp,Value1,Value2\n"]
    data_rows = fetch_all_data(limit=20)  # Reuse the same function
    battery_rows = data_rows["battery_data"]
    motor_rows = data_rows["motor_data"]

    # Battery CSV
    for row in battery_rows:
        csv_lines.append(
            f"Battery,{row['id']},{row['timestamp']},{row['battery_volt']},{row['battery_current']}\n"
        )

    # Motor CSV
    for row in motor_rows:
        csv_lines.append(
            f"Motor,{row['id']},{row['timestamp']},{row['motor_current']},{row['motor_temp']}\n"
        )

    resp = make_response("".join(csv_lines))
    resp.headers["Content-Disposition"] = "attachment; filename=hust_data_export.csv"
    resp.mimetype = "text/csv"
    return resp

# -------------------------------------------
# SOCKET.IO EVENTS
# -------------------------------------------
@socketio.on("connect")
def on_connect():
    print("Client connected:", request.sid)

@socketio.on("disconnect")
def on_disconnect():
    print("Client disconnected:", request.sid)

# -------------------------------------------
# STARTUP
# -------------------------------------------
if __name__ == "__main__":
    # Start background thread for real-time
    socketio.start_background_task(background_data_fetcher)
    try:
        socketio.run(app, host="0.0.0.0", port=5000, debug=True)
    finally:
        thread_stop_event.set()
        print("Shutting down background thread...")
