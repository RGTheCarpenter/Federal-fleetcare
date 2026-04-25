import html
import json
import mimetypes
import os
from datetime import date, datetime
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from .auth import hash_password, load_secret_key, read_session, sign_session, verify_password
from .db import get_connection, init_db
from .pdf import build_simple_pdf


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
SECRET_KEY = load_secret_key()
COMPANY_INVITE_CODE = os.environ.get("COMPANY_INVITE_CODE", "").strip()
APP_PUBLIC_URL = os.environ.get("APP_PUBLIC_URL", "https://fleetcare-web.onrender.com").strip()
APP_BRAND = "Roadsmith Fleet"
APP_SHORT_NAME = "Roadsmith"
APP_TAGLINE = "Field command for working fleets"


def run():
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), FleetCareHandler)
    print(f"{APP_BRAND} running on http://{HOST}:{PORT}")
    server.serve_forever()


class FleetCareHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = urlparse(self.path)
        path = route.path

        if path.startswith("/static/"):
            return self.serve_static(path)
        if path == "/":
            return self.redirect("/dashboard" if self.current_user() else "/login")
        if path == "/health":
            return self.send_text("ok")
        if path == "/login":
            return self.render_auth_page("login")
        if path == "/register":
            return self.render_auth_page("register")
        if path == "/logout":
            return self.redirect("/login")
        if path == "/dashboard":
            return self.render_dashboard(route)
        if path == "/reports/fleet.pdf":
            return self.render_pdf_report(route)

        return self.not_found()

    def do_POST(self):
        route = urlparse(self.path)
        path = route.path
        form = self.read_form()

        if path == "/login":
            return self.handle_login(form)
        if path == "/register":
            return self.handle_register(form)
        if path == "/logout":
            return self.handle_logout()

        user = self.require_user()
        if not user:
            return

        if path == "/vehicles/add":
            return self.handle_vehicle_add(user, form)
        if path == "/vehicles/update":
            return self.handle_vehicle_update(user, form)
        if path == "/vehicles/delete":
            return self.handle_vehicle_delete(user, form)
        if path == "/drivers/add":
            return self.handle_driver_add(user, form)
        if path == "/drivers/update":
            return self.handle_driver_update(user, form)
        if path == "/drivers/delete":
            return self.handle_driver_delete(user, form)
        if path == "/assignments/add":
            return self.handle_assignment_add(user, form)
        if path == "/maintenance/add":
            return self.handle_maintenance_add(user, form)
        if path == "/fuel/add":
            return self.handle_fuel_add(user, form)
        if path == "/reminders/add":
            return self.handle_reminder_add(user, form)
        if path == "/gps/add":
            return self.handle_gps_add(user, form)
        if path == "/trips/start":
            return self.handle_trip_start(user, form)
        if path == "/trips/stop":
            return self.handle_trip_stop(user, form)

        return self.not_found()

    def read_form(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length).decode("utf-8")
        parsed = parse_qs(raw, keep_blank_values=True)
        return {key: values[0].strip() for key, values in parsed.items()}

    def current_user(self):
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return None

        jar = cookies.SimpleCookie()
        jar.load(cookie_header)
        session_cookie = jar.get("fleetcare_session")
        if not session_cookie:
            return None

        user_id = read_session(session_cookie.value, SECRET_KEY)
        if not user_id:
            return None

        with get_connection() as connection:
            return connection.execute(
                "SELECT id, company_name, email FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()

    def require_user(self):
        user = self.current_user()
        if not user:
            self.redirect("/login")
            return None
        return user

    def handle_register(self, form):
        company_name = form.get("company_name", "")
        email = form.get("email", "").lower()
        password = form.get("password", "")
        invite_code = form.get("invite_code", "")

        if not company_name or not email or not password or not invite_code:
            return self.redirect("/register?error=Please+fill+out+every+field")

        if not COMPANY_INVITE_CODE:
            return self.redirect("/register?error=Registration+is+not+configured")

        if invite_code != COMPANY_INVITE_CODE:
            return self.redirect("/register?error=Invalid+company+invite+code")

        password_hash = hash_password(password)
        try:
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO users (company_name, email, password_hash)
                    VALUES (?, ?, ?)
                    """,
                    (company_name, email, password_hash),
                )
                user = connection.execute(
                    "SELECT id FROM users WHERE email = ?",
                    (email,),
                ).fetchone()
        except Exception:
            return self.redirect("/register?error=That+email+is+already+registered")

        return self.login_user(user["id"])

    def handle_login(self, form):
        email = form.get("email", "").lower()
        password = form.get("password", "")

        with get_connection() as connection:
            user = connection.execute(
                "SELECT id, password_hash FROM users WHERE email = ?",
                (email,),
            ).fetchone()

        if not user or not verify_password(password, user["password_hash"]):
            return self.redirect("/login?error=Invalid+email+or+password")

        return self.login_user(user["id"])

    def handle_logout(self):
        self.send_response(303)
        self.send_header("Set-Cookie", self.session_cookie("", max_age=0))
        self.send_header("Location", "/login")
        self.end_headers()

    def login_user(self, user_id):
        session_value = sign_session(user_id, SECRET_KEY)
        self.send_response(303)
        self.send_header("Set-Cookie", self.session_cookie(session_value))
        self.send_header("Location", "/dashboard")
        self.end_headers()

    def handle_vehicle_add(self, user, form):
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO vehicles (user_id, name, plate, model, year, odometer, status, photo_name, photo_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    form.get("name", ""),
                    form.get("plate", "").upper(),
                    form.get("model", ""),
                    int(form.get("year") or 0) or None,
                    int(form.get("odometer") or 0),
                    form.get("status", "Active"),
                    clean_upload_name(form.get("photo_name", "")),
                    clean_upload_data(form.get("photo_data", "")),
                ),
            )

        self.redirect("/dashboard?tab=vehicles#vehicles")

    def handle_vehicle_update(self, user, form):
        vehicle_id = int(form.get("vehicle_id") or 0)
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE vehicles
                SET name = ?, plate = ?, model = ?, year = ?, odometer = ?, status = ?, photo_name = ?, photo_data = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    form.get("name", ""),
                    form.get("plate", "").upper(),
                    form.get("model", ""),
                    int(form.get("year") or 0) or None,
                    int(form.get("odometer") or 0),
                    form.get("status", "Active"),
                    clean_upload_name(form.get("photo_name", "")),
                    clean_upload_data(form.get("photo_data", "")),
                    vehicle_id,
                    user["id"],
                ),
            )

        self.redirect("/dashboard?tab=vehicles#vehicles")

    def handle_vehicle_delete(self, user, form):
        vehicle_id = int(form.get("vehicle_id") or 0)
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM vehicles WHERE id = ? AND user_id = ?",
                (vehicle_id, user["id"]),
            )

        self.redirect("/dashboard?tab=vehicles#vehicles")

    def handle_driver_add(self, user, form):
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO drivers (user_id, name, license_number, phone, email, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    form.get("name", ""),
                    form.get("license_number", ""),
                    form.get("phone", ""),
                    form.get("email", ""),
                    form.get("status", "Active"),
                ),
            )

        self.redirect("/dashboard?tab=drivers#drivers")

    def handle_driver_update(self, user, form):
        driver_id = int(form.get("driver_id") or 0)
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE drivers
                SET name = ?, license_number = ?, phone = ?, email = ?, status = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    form.get("name", ""),
                    form.get("license_number", ""),
                    form.get("phone", ""),
                    form.get("email", ""),
                    form.get("status", "Active"),
                    driver_id,
                    user["id"],
                ),
            )

        self.redirect("/dashboard?tab=drivers#drivers")

    def handle_driver_delete(self, user, form):
        driver_id = int(form.get("driver_id") or 0)
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM drivers WHERE id = ? AND user_id = ?",
                (driver_id, user["id"]),
            )

        self.redirect("/dashboard?tab=drivers#drivers")

    def handle_assignment_add(self, user, form):
        vehicle_id = int(form.get("vehicle_id") or 0)
        driver_id = int(form.get("driver_id") or 0)

        with get_connection() as connection:
            connection.execute(
                """
                UPDATE assignments
                SET active = 0
                WHERE user_id = ? AND vehicle_id = ? AND active = 1
                """,
                (user["id"], vehicle_id),
            )
            connection.execute(
                """
                INSERT INTO assignments (user_id, vehicle_id, driver_id, start_date, end_date, notes, active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    user["id"],
                    vehicle_id,
                    driver_id,
                    form.get("start_date", ""),
                    form.get("end_date") or None,
                    form.get("notes", ""),
                ),
            )

        self.redirect("/dashboard?tab=assignments#assignments")

    def handle_maintenance_add(self, user, form):
        vehicle_id = int(form.get("vehicle_id") or 0)
        odometer = int(form.get("odometer") or 0)

        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO maintenance_logs
                (user_id, vehicle_id, service_type, service_date, odometer, cost, notes, next_due_date, next_due_odometer, attachment_name, attachment_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    vehicle_id,
                    form.get("service_type", ""),
                    form.get("service_date", ""),
                    odometer,
                    float(form.get("cost") or 0),
                    form.get("notes", ""),
                    form.get("next_due_date") or None,
                    int(form.get("next_due_odometer") or 0) or None,
                    clean_upload_name(form.get("attachment_name", "")),
                    clean_upload_data(form.get("attachment_data", "")),
                ),
            )
            connection.execute(
                """
                UPDATE vehicles
                SET odometer = CASE
                    WHEN odometer < ? THEN ?
                    ELSE odometer
                END
                WHERE id = ? AND user_id = ?
                """,
                (odometer, odometer, vehicle_id, user["id"]),
            )

        self.redirect("/dashboard?tab=maintenance#maintenance")

    def handle_fuel_add(self, user, form):
        vehicle_id = int(form.get("vehicle_id") or 0)
        odometer = int(form.get("odometer") or 0)
        liters = float(form.get("liters") or 0)
        total_cost = float(form.get("total_cost") or 0)
        price_per_liter = total_cost / liters if liters else 0
        full_tank = 1 if form.get("full_tank") == "on" else 0

        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO fuel_logs
                (user_id, vehicle_id, fill_date, odometer, liters, total_cost, price_per_liter, station, full_tank, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    vehicle_id,
                    form.get("fill_date", ""),
                    odometer,
                    liters,
                    total_cost,
                    price_per_liter,
                    form.get("station", ""),
                    full_tank,
                    form.get("notes", ""),
                ),
            )
            connection.execute(
                """
                UPDATE vehicles
                SET odometer = CASE
                    WHEN odometer < ? THEN ?
                    ELSE odometer
                END
                WHERE id = ? AND user_id = ?
                """,
                (odometer, odometer, vehicle_id, user["id"]),
            )

        self.redirect("/dashboard?tab=fuel#fuel")

    def handle_reminder_add(self, user, form):
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO reminders (user_id, vehicle_id, title, due_date, due_odometer, notes, status)
                VALUES (?, ?, ?, ?, ?, ?, 'Open')
                """,
                (
                    user["id"],
                    int(form.get("vehicle_id") or 0),
                    form.get("title", ""),
                    form.get("due_date") or None,
                    int(form.get("due_odometer") or 0) or None,
                    form.get("notes", ""),
                ),
            )

        self.redirect("/dashboard?tab=alerts#reminders")

    def handle_gps_add(self, user, form):
        vehicle_id = int(form.get("vehicle_id") or 0)
        trip_id = int(form.get("trip_id") or 0) or None
        latitude = parse_coordinate(form.get("latitude"))
        longitude = parse_coordinate(form.get("longitude"))
        accuracy = parse_coordinate(form.get("accuracy_meters"))

        if not vehicle_id or latitude is None or longitude is None:
            return self.redirect("/dashboard?tab=vehicles#gps")

        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO gps_logs (user_id, vehicle_id, trip_id, latitude, longitude, accuracy_meters)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user["id"], vehicle_id, trip_id, latitude, longitude, accuracy),
            )

        self.redirect("/dashboard?tab=vehicles#gps")

    def handle_trip_start(self, user, form):
        vehicle_id = int(form.get("vehicle_id") or 0)
        latitude = parse_coordinate(form.get("latitude"))
        longitude = parse_coordinate(form.get("longitude"))
        label = form.get("label", "")

        if not vehicle_id:
            return self.redirect("/dashboard?tab=vehicles#trip-control")

        with get_connection() as connection:
            connection.execute(
                "UPDATE trips SET status = 'Completed', ended_at = CURRENT_TIMESTAMP WHERE user_id = ? AND status = 'Active'",
                (user["id"],),
            )
            connection.execute(
                """
                INSERT INTO trips (user_id, vehicle_id, label, start_latitude, start_longitude, status)
                VALUES (?, ?, ?, ?, ?, 'Active')
                """,
                (user["id"], vehicle_id, label or None, latitude, longitude),
            )
            trip = connection.execute(
                "SELECT id FROM trips WHERE user_id = ? AND vehicle_id = ? AND status = 'Active' ORDER BY started_at DESC LIMIT 1",
                (user["id"], vehicle_id),
            ).fetchone()
            if trip and latitude is not None and longitude is not None:
                connection.execute(
                    """
                    INSERT INTO gps_logs (user_id, vehicle_id, trip_id, latitude, longitude, accuracy_meters)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user["id"], vehicle_id, trip["id"], latitude, longitude, parse_coordinate(form.get("accuracy_meters"))),
                )

        self.redirect("/dashboard?tab=vehicles#trip-control")

    def handle_trip_stop(self, user, form):
        trip_id = int(form.get("trip_id") or 0)
        latitude = parse_coordinate(form.get("latitude"))
        longitude = parse_coordinate(form.get("longitude"))
        accuracy = parse_coordinate(form.get("accuracy_meters"))

        if not trip_id:
            return self.redirect("/dashboard?tab=vehicles#trip-control")

        with get_connection() as connection:
            trip = connection.execute(
                "SELECT id, vehicle_id FROM trips WHERE id = ? AND user_id = ? AND status = 'Active'",
                (trip_id, user["id"]),
            ).fetchone()
            if not trip:
                return self.redirect("/dashboard?tab=vehicles#trip-control")

            if latitude is not None and longitude is not None:
                connection.execute(
                    """
                    INSERT INTO gps_logs (user_id, vehicle_id, trip_id, latitude, longitude, accuracy_meters)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user["id"], trip["vehicle_id"], trip_id, latitude, longitude, accuracy),
                )
            connection.execute(
                """
                UPDATE trips
                SET status = 'Completed', ended_at = CURRENT_TIMESTAMP, end_latitude = ?, end_longitude = ?
                WHERE id = ? AND user_id = ?
                """,
                (latitude, longitude, trip_id, user["id"]),
            )

        self.redirect("/dashboard?tab=vehicles#trip-history")

    def render_auth_page(self, mode):
        route = urlparse(self.path)
        message = parse_qs(route.query).get("error", [""])[0]
        title = "Sign in" if mode == "login" else "Create account"
        action = "/login" if mode == "login" else "/register"
        alternate = (
            '<p class="auth-switch">No account yet? <a href="/register">Create one</a></p>'
            if mode == "login"
            else '<p class="auth-switch">Already registered? <a href="/login">Sign in</a></p>'
        )
        extra = (
            ""
            if mode == "login"
            else """
                <label>
                  <span>Company name</span>
                  <input type="text" name="company_name" required>
                </label>
                <label>
                  <span>Company invite code</span>
                  <input type="password" name="invite_code" autocomplete="off" required>
                </label>
            """
        )

        content = f"""
        <section class="auth-shell">
          <div class="auth-card">
            {render_brand_lockup(compact=True)}
            <h1>{title}</h1>
            <p class="muted">Manage fleet maintenance, fuel, assignments, reports, GPS, and alerts in one place.</p>
            {f'<div class="flash error">{h(message)}</div>' if message else ''}
            <form method="post" action="{action}" class="form-grid single-column">
              {extra}
              <label>
                <span>Email</span>
                <input type="email" name="email" required>
              </label>
              <label>
                <span>Password</span>
                <input type="password" name="password" required>
              </label>
              <button type="submit" class="primary-btn">{title}</button>
            </form>
            {alternate}
          </div>
        </section>
        """
        return self.send_html(page(APP_BRAND, content))

    def render_dashboard(self, route):
        user = self.require_user()
        if not user:
            return
        active_tab = get_active_tab(route)
        active_vehicle_view = get_vehicle_view(route)

        try:
            with get_connection() as connection:
                vehicles = connection.execute(
                    """
                    SELECT
                        v.*,
                        (
                            SELECT g.latitude
                            FROM gps_logs g
                            WHERE g.vehicle_id = v.id AND g.user_id = v.user_id
                            ORDER BY g.created_at DESC
                            LIMIT 1
                        ) AS last_latitude,
                        (
                            SELECT g.longitude
                            FROM gps_logs g
                            WHERE g.vehicle_id = v.id AND g.user_id = v.user_id
                            ORDER BY g.created_at DESC
                            LIMIT 1
                        ) AS last_longitude,
                        (
                            SELECT g.accuracy_meters
                            FROM gps_logs g
                            WHERE g.vehicle_id = v.id AND g.user_id = v.user_id
                            ORDER BY g.created_at DESC
                            LIMIT 1
                        ) AS last_accuracy_meters,
                        (
                            SELECT g.created_at
                            FROM gps_logs g
                            WHERE g.vehicle_id = v.id AND g.user_id = v.user_id
                            ORDER BY g.created_at DESC
                            LIMIT 1
                        ) AS last_location_at
                    FROM vehicles v
                    WHERE v.user_id = ?
                    ORDER BY v.created_at DESC
                    """,
                    (user["id"],),
                ).fetchall()
                drivers = connection.execute(
                    "SELECT * FROM drivers WHERE user_id = ? ORDER BY created_at DESC",
                    (user["id"],),
                ).fetchall()
                assignments = connection.execute(
                    """
                    SELECT a.*, v.name AS vehicle_name, v.plate, d.name AS driver_name
                    FROM assignments a
                    JOIN vehicles v ON v.id = a.vehicle_id
                    JOIN drivers d ON d.id = a.driver_id
                    WHERE a.user_id = ?
                    ORDER BY a.active DESC, a.start_date DESC
                    """,
                    (user["id"],),
                ).fetchall()
                maintenance = connection.execute(
                    """
                    SELECT m.*, v.name AS vehicle_name, v.plate
                    FROM maintenance_logs m
                    JOIN vehicles v ON v.id = m.vehicle_id
                    WHERE m.user_id = ?
                    ORDER BY m.service_date DESC
                    LIMIT 8
                    """,
                    (user["id"],),
                ).fetchall()
                fuel_logs = connection.execute(
                    """
                    SELECT f.*, v.name AS vehicle_name, v.plate
                    FROM fuel_logs f
                    JOIN vehicles v ON v.id = f.vehicle_id
                    WHERE f.user_id = ?
                    ORDER BY f.fill_date DESC
                    LIMIT 8
                    """,
                    (user["id"],),
                ).fetchall()
                reminders = connection.execute(
                    """
                    SELECT r.*, v.name AS vehicle_name, v.plate, v.odometer AS vehicle_odometer
                    FROM reminders r
                    JOIN vehicles v ON v.id = r.vehicle_id
                    WHERE r.user_id = ? AND r.status = 'Open'
                    ORDER BY COALESCE(r.due_date, '9999-12-31'), COALESCE(r.due_odometer, 999999999)
                    """,
                    (user["id"],),
                ).fetchall()
                gps_logs = []
                active_trip = None
                trips = []
                trip_points = []
                try:
                    gps_logs = connection.execute(
                        """
                        SELECT g.*, v.name AS vehicle_name, v.plate
                        FROM gps_logs g
                        JOIN vehicles v ON v.id = g.vehicle_id
                        WHERE g.user_id = ?
                        ORDER BY g.created_at DESC
                        LIMIT 12
                        """,
                        (user["id"],),
                    ).fetchall()
                    active_trip = connection.execute(
                        """
                        SELECT t.*, v.name AS vehicle_name, v.plate
                        FROM trips t
                        JOIN vehicles v ON v.id = t.vehicle_id
                        WHERE t.user_id = ? AND t.status = 'Active'
                        ORDER BY t.started_at DESC
                        LIMIT 1
                        """,
                        (user["id"],),
                    ).fetchone()
                    trips = connection.execute(
                        """
                        SELECT
                            t.*,
                            v.name AS vehicle_name,
                            v.plate,
                            (
                                SELECT COUNT(*)
                                FROM gps_logs g
                                WHERE g.trip_id = t.id
                            ) AS point_count
                        FROM trips t
                        JOIN vehicles v ON v.id = t.vehicle_id
                        WHERE t.user_id = ?
                        ORDER BY t.started_at DESC
                        LIMIT 8
                        """,
                        (user["id"],),
                    ).fetchall()
                    trip_points = connection.execute(
                        """
                        SELECT trip_id, latitude, longitude, created_at
                        FROM gps_logs
                        WHERE user_id = ? AND trip_id IS NOT NULL
                        ORDER BY trip_id, created_at
                        """,
                        (user["id"],),
                    ).fetchall()
                except Exception as error:
                    print(f"GPS dashboard data skipped: {error}")

            alerts = collect_alerts(reminders, assignments)
            stats = build_stats(vehicles, maintenance, fuel_logs, reminders)
            mobile_reminders = json.dumps(build_mobile_reminders(reminders), separators=(",", ":"))
            trip_routes = json.dumps(build_trip_routes(trip_points), separators=(",", ":"))
            tracking_state = json.dumps(build_tracking_payload(active_trip, gps_logs), separators=(",", ":"))

            content = f"""
        <div class="page-shell">
          <div class="offline-banner" data-offline-banner hidden>
            Connection lost. Roadsmith Fleet will retry automatically when your phone is back online.
          </div>
          <header class="hero">
            <div class="hero-copy">
              <p class="kicker">Fleet operations</p>
              {render_brand_lockup()}
              <p class="hero-subtitle">Workspace for {h(user["company_name"])}</p>
            </div>
            <div class="hero-actions">
              <button
                type="button"
                class="ghost-btn"
                data-share-app
                data-share-title="{h(APP_BRAND)}"
                data-share-text="Open {h(APP_BRAND)} to manage vehicles, service, fuel, and reminders."
                data-share-url="{h(APP_PUBLIC_URL)}"
              >Share workspace</button>
              <form method="post" action="/logout">
                <button type="submit" class="ghost-btn">Sign out</button>
              </form>
            </div>
          </header>

          <details class="report-panel">
            <summary>
              <span>
                <span class="section-kicker">Reports</span>
                <strong>Download PDF report</strong>
              </span>
            </summary>
            <form method="get" action="/reports/fleet.pdf" class="report-form">
              <label>
                <span>Report month</span>
                <input type="month" name="month">
              </label>
              <label>
                <span>From date</span>
                <input type="date" name="start_date">
              </label>
              <label>
                <span>To date</span>
                <input type="date" name="end_date">
              </label>
              <button type="submit" class="primary-btn">Download PDF</button>
            </form>
            <p class="muted report-help">Choose a month, or leave month blank and choose a custom from/to date range.</p>
          </details>

          <nav class="quick-links" aria-label="Dashboard sections">
            {render_tab_link("vehicles", "Vehicles", active_tab)}
            {render_tab_link("drivers", "Drivers", active_tab)}
            {render_tab_link("assignments", "Assignments", active_tab)}
            {render_tab_link("maintenance", "Maintenance", active_tab)}
            {render_tab_link("fuel", "Fuel", active_tab)}
            {render_tab_link("alerts", "Alerts", active_tab)}
          </nav>

          <section class="stats-grid">
            {render_stat("Vehicles", len(vehicles))}
            {render_stat("Drivers", len(drivers))}
            {render_stat("Open alerts", len(alerts))}
            {render_stat("Fuel spend", money(stats["fuel_spend"]))}
            {render_stat("Maintenance spend", money(stats["maintenance_spend"]))}
            {render_stat("Avg fuel price", money(stats["avg_fuel_price"]))}
          </section>

          <section class="{tab_panel_classes('alerts', active_tab, 'panel span-two')}" data-tab-section="alerts" {"hidden" if active_tab != "alerts" else ""}>
            <div class="panel-header">
              <div>
                <p class="section-kicker">Alerts</p>
                <h2>What needs attention</h2>
              </div>
            </div>
            <div class="stack-list">
              {render_alerts(alerts)}
            </div>
          </section>

          <main class="layout">
            <section class="{tab_panel_classes('vehicles', active_tab, 'panel span-two')}" id="vehicle-workspace" data-tab-section="vehicles" {"hidden" if active_tab != "vehicles" else ""}>
              <div class="panel-header">
                <div>
                  <p class="section-kicker">Vehicle workspace</p>
                  <h2>Fleet command</h2>
                </div>
              </div>
              <nav class="sub-links" aria-label="Vehicle workspace views">
                {render_subtab_link("vehicles", "overview", "Overview", active_vehicle_view)}
                {render_subtab_link("vehicles", "add", "Add vehicle", active_vehicle_view)}
                {render_subtab_link("vehicles", "capture", "GPS capture", active_vehicle_view)}
                {render_subtab_link("vehicles", "trips", "Trips", active_vehicle_view)}
                {render_subtab_link("vehicles", "history", "History", active_vehicle_view)}
              </nav>
            </section>

            <section class="{tab_panel_classes('vehicles', active_tab, 'panel')}" id="tracking-status" data-tab-section="vehicles" {"hidden" if active_tab != "vehicles" or active_vehicle_view != "overview" else ""}>
              <div class="panel-header"><div><p class="section-kicker">Tracking</p><h2>Tracking status</h2></div></div>
              {render_tracking_status(active_trip, gps_logs)}
            </section>

            <section class="{tab_panel_classes('vehicles', active_tab, 'panel')}" id="vehicles" data-tab-section="vehicles" {"hidden" if active_tab != "vehicles" or active_vehicle_view != "add" else ""}>
              <div class="panel-header"><div><p class="section-kicker">Fleet</p><h2>Add vehicle</h2></div></div>
              <form method="post" action="/vehicles/add" class="form-grid">
                <label><span>Name</span><input type="text" name="name" required></label>
                <label><span>Plate</span><input type="text" name="plate" required></label>
                <label><span>Model</span><input type="text" name="model"></label>
                <label><span>Year</span><input type="number" name="year" min="1990" max="2100"></label>
                <label><span>Odometer</span><input type="number" name="odometer" min="0" required></label>
                <label>
                  <span>Status</span>
                  <select name="status">
                    <option>Active</option>
                    <option>In service</option>
                    <option>Inactive</option>
                  </select>
                </label>
                {render_upload_field("Vehicle photo", "vehicle-photo-new", "photo_name", "photo_data", "image/*", capture=True)}
                <button type="submit" class="primary-btn">Save vehicle</button>
              </form>
            </section>

            <section class="{tab_panel_classes('vehicles', active_tab, 'panel')}" id="gps" data-tab-section="vehicles" {"hidden" if active_tab != "vehicles" or active_vehicle_view != "capture" else ""}>
              <div class="panel-header"><div><p class="section-kicker">GPS</p><h2>Capture a location</h2></div></div>
              {render_gps_form(vehicles, active_trip)}
            </section>

            <section class="{tab_panel_classes('vehicles', active_tab, 'panel')}" id="trip-control" data-tab-section="vehicles" {"hidden" if active_tab != "vehicles" or active_vehicle_view != "trips" else ""}>
              <div class="panel-header"><div><p class="section-kicker">Trips</p><h2>Trip tracking</h2></div></div>
              {render_trip_controls(vehicles, active_trip)}
            </section>

            <section class="{tab_panel_classes('drivers', active_tab, 'panel')}" id="drivers" data-tab-section="drivers" {"hidden" if active_tab != "drivers" else ""}>
              <div class="panel-header"><div><p class="section-kicker">Drivers</p><h2>Add driver</h2></div></div>
              <form method="post" action="/drivers/add" class="form-grid">
                <label><span>Name</span><input type="text" name="name" required></label>
                <label><span>License number</span><input type="text" name="license_number"></label>
                <label><span>Phone</span><input type="text" name="phone"></label>
                <label><span>Email</span><input type="email" name="email"></label>
                <label>
                  <span>Status</span>
                  <select name="status">
                    <option>Active</option>
                    <option>Vacation</option>
                    <option>Inactive</option>
                  </select>
                </label>
                <button type="submit" class="primary-btn">Save driver</button>
              </form>
            </section>

            <section class="{tab_panel_classes('assignments', active_tab, 'panel')}" id="assignments" data-tab-section="assignments" {"hidden" if active_tab != "assignments" else ""}>
              <div class="panel-header"><div><p class="section-kicker">Assignments</p><h2>Assign vehicle</h2></div></div>
              {render_assignment_form(vehicles, drivers)}
            </section>

            <section class="{tab_panel_classes('maintenance', active_tab, 'panel')}" id="maintenance" data-tab-section="maintenance" {"hidden" if active_tab != "maintenance" else ""}>
              <div class="panel-header"><div><p class="section-kicker">Maintenance</p><h2>Log service</h2></div></div>
              {render_maintenance_form(vehicles)}
            </section>

            <section class="{tab_panel_classes('fuel', active_tab, 'panel')}" id="fuel" data-tab-section="fuel" {"hidden" if active_tab != "fuel" else ""}>
              <div class="panel-header"><div><p class="section-kicker">Fuel</p><h2>Log fuel fill</h2></div></div>
              {render_fuel_form(vehicles)}
            </section>

            <section class="{tab_panel_classes('alerts', active_tab, 'panel')}" id="reminders" data-tab-section="alerts" {"hidden" if active_tab != "alerts" else ""}>
              <div class="panel-header"><div><p class="section-kicker">Reminders</p><h2>Create alert reminder</h2></div></div>
              {render_reminder_form(vehicles)}
            </section>

            <section class="{tab_panel_classes('vehicles', active_tab, 'panel span-two')}" data-tab-section="vehicles" {"hidden" if active_tab != "vehicles" or active_vehicle_view != "overview" else ""}>
              <div class="panel-header"><div><p class="section-kicker">Current state</p><h2>Vehicles</h2></div></div>
              <div class="stack-list">{render_vehicles(vehicles)}</div>
            </section>

            <section class="{tab_panel_classes('vehicles', active_tab, 'panel span-two')}" data-tab-section="vehicles" {"hidden" if active_tab != "vehicles" or active_vehicle_view != "capture" else ""}>
              <div class="panel-header"><div><p class="section-kicker">GPS</p><h2>Recent location history</h2></div></div>
              <div class="stack-list">{render_gps_logs(gps_logs)}</div>
            </section>

            <section class="{tab_panel_classes('vehicles', active_tab, 'panel span-two')}" id="trip-history" data-tab-section="vehicles" {"hidden" if active_tab != "vehicles" or active_vehicle_view not in {"trips", "history"} else ""}>
              <div class="panel-header"><div><p class="section-kicker">Trips</p><h2>Trip history and routes</h2></div></div>
              <div class="stack-list">{render_trip_history(trips)}</div>
            </section>

            <section class="{tab_panel_classes('drivers', active_tab, 'panel span-two')}" data-tab-section="drivers" {"hidden" if active_tab != "drivers" else ""}>
              <div class="panel-header"><div><p class="section-kicker">Current state</p><h2>Drivers</h2></div></div>
              <div class="stack-list">{render_drivers(drivers)}</div>
            </section>

            <section class="{tab_panel_classes('assignments', active_tab, 'panel span-two')}" data-tab-section="assignments" {"hidden" if active_tab != "assignments" else ""}>
              <div class="panel-header"><div><p class="section-kicker">Assignments</p><h2>Driver assignments</h2></div></div>
              <div class="stack-list">{render_assignments(assignments)}</div>
            </section>

            <section class="{tab_panel_classes('maintenance', active_tab, 'panel span-two')}" data-tab-section="maintenance" {"hidden" if active_tab != "maintenance" else ""}>
              <div class="panel-header"><div><p class="section-kicker">History</p><h2>Maintenance history</h2></div></div>
              <div class="stack-list">{render_maintenance_logs(maintenance)}</div>
            </section>

            <section class="{tab_panel_classes('fuel', active_tab, 'panel span-two')}" data-tab-section="fuel" {"hidden" if active_tab != "fuel" else ""}>
              <div class="panel-header"><div><p class="section-kicker">Consumption</p><h2>Fuel history</h2></div></div>
              <div class="stack-list">{render_fuel_logs(fuel_logs)}</div>
            </section>
          </main>
        </div>
        <script>window.FLEETCARE_REMINDERS = {mobile_reminders}; window.FLEETCARE_TRIP_ROUTES = {trip_routes}; window.FLEETCARE_TRACKING = {tracking_state};</script>
        """
            return self.send_html(page(f"{APP_BRAND} Dashboard", content))
        except Exception as error:
            print(f"Dashboard render failed: {error}")
            fallback = f"""
            <section class="auth-shell">
              <div class="auth-card">
                {render_brand_lockup(compact=True)}
                <h1>Dashboard recovering</h1>
                <p class="muted">A dashboard module failed to load after sign-in. The app is still running, and this page is here so you are not blocked by a 502 error.</p>
                <div class="flash error">Dashboard error: {h(error)}</div>
                <div class="hero-actions">
                  <a class="ghost-btn" href="/dashboard">Try dashboard again</a>
                  <a class="ghost-btn" href="/logout">Sign out</a>
                </div>
              </div>
            </section>
            """
            return self.send_html(page(f"{APP_BRAND} Recovery", fallback), status=200)

    def render_pdf_report(self, route):
        user = self.require_user()
        if not user:
            return

        query = parse_qs(route.query)
        vehicle_id = query.get("vehicle_id", [""])[0]
        start_date, end_date, report_period = parse_report_period(query)

        with get_connection() as connection:
            vehicle_filter = ""
            params = [user["id"]]
            if vehicle_id:
                vehicle_filter = " AND v.id = ?"
                params.append(int(vehicle_id))

            vehicles = connection.execute(
                f"SELECT v.* FROM vehicles v WHERE v.user_id = ?{vehicle_filter} ORDER BY v.name",
                tuple(params),
            ).fetchall()
            maintenance_filter, maintenance_params = report_date_filter(
                "m.service_date",
                start_date,
                end_date,
                params,
            )
            maintenance = connection.execute(
                f"""
                SELECT m.service_date, m.service_type, m.cost, v.name AS vehicle_name, m.odometer
                FROM maintenance_logs m
                JOIN vehicles v ON v.id = m.vehicle_id
                WHERE m.user_id = ?{vehicle_filter.replace('v.id', 'm.vehicle_id')}{maintenance_filter}
                ORDER BY m.service_date DESC
                LIMIT 20
                """,
                tuple(maintenance_params),
            ).fetchall()
            fuel_filter, fuel_params = report_date_filter(
                "f.fill_date",
                start_date,
                end_date,
                params,
            )
            fuel_logs = connection.execute(
                f"""
                SELECT f.fill_date, f.total_cost, f.liters, v.name AS vehicle_name, f.odometer
                FROM fuel_logs f
                JOIN vehicles v ON v.id = f.vehicle_id
                WHERE f.user_id = ?{vehicle_filter.replace('v.id', 'f.vehicle_id')}{fuel_filter}
                ORDER BY f.fill_date DESC
                LIMIT 20
                """,
                tuple(fuel_params),
            ).fetchall()

        lines = [f"Report period: {report_period}", "", "Fleet summary", ""]
        for vehicle in vehicles:
            lines.append(
                f"Vehicle: {vehicle['name']} | Plate: {vehicle['plate']} | Odometer: {vehicle['odometer']} km | Status: {vehicle['status']}"
            )
        lines.append("")
        lines.append("Recent maintenance")
        for item in maintenance:
            lines.append(
                f"{item['service_date']} | {item['vehicle_name']} | {item['service_type']} | {item['odometer']} km | {money(item['cost'])}"
            )
        lines.append("")
        lines.append("Recent fuel logs")
        for item in fuel_logs:
            lines.append(
                f"{item['fill_date']} | {item['vehicle_name']} | {item['odometer']} km | {item['liters']} L | {money(item['total_cost'])}"
            )

        pdf_bytes = build_simple_pdf(f"{user['company_name']} Fleet Report", lines)
        filename = slugify(user["company_name"]) + "-fleet-report.pdf"
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(pdf_bytes)))
        self.end_headers()
        self.wfile.write(pdf_bytes)

    def serve_static(self, path):
        file_path = STATIC_DIR / path.replace("/static/", "", 1)
        if not file_path.exists():
            return self.not_found()

        mime_type, _ = mimetypes.guess_type(file_path.name)
        payload = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def send_html(self, payload, status=200):
        data = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_text(self, payload):
        data = payload.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def not_found(self):
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not found")

    def session_cookie(self, value, max_age=None):
        parts = [f"fleetcare_session={value}", "Path=/", "HttpOnly", "SameSite=Lax"]
        forwarded_proto = self.headers.get("X-Forwarded-Proto", "")
        if forwarded_proto == "https" or os.environ.get("COOKIE_SECURE", "").lower() == "true":
            parts.append("Secure")
        if max_age is not None:
            parts.append(f"Max-Age={max_age}")
        return "; ".join(parts)


def page(title, content):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#1e7e61">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="{h(APP_SHORT_NAME)}">
  <meta name="apple-mobile-web-app-status-bar-style" content="default">
  <title>{h(title)}</title>
  <link rel="manifest" href="/static/manifest.webmanifest">
  <link rel="icon" type="image/svg+xml" href="/static/icon-192.svg">
  <link rel="apple-touch-icon" href="/static/icon-192.svg">
  <link rel="stylesheet" href="/static/styles.css">
  <script src="/static/mobile.js" defer></script>
  <script>
    if ("serviceWorker" in navigator) {{
      window.addEventListener("load", () => {{
        navigator.serviceWorker.register("/static/service-worker.js").catch(() => {{}});
      }});
    }}
  </script>
</head>
<body>{content}</body>
</html>"""


def h(value):
    return html.escape(str(value or ""))


def get_active_tab(route):
    valid_tabs = {"vehicles", "drivers", "assignments", "maintenance", "fuel", "alerts"}
    tab = parse_qs(route.query).get("tab", ["vehicles"])[0]
    return tab if tab in valid_tabs else "vehicles"


def get_vehicle_view(route):
    valid_views = {"overview", "add", "capture", "trips", "history"}
    view = parse_qs(route.query).get("vehicles_view", ["overview"])[0]
    return view if view in valid_views else "overview"


def render_tab_link(tab_name, label, active_tab):
    active_class = " is-active" if tab_name == active_tab else ""
    return f'<a class="quick-link{active_class}" href="/dashboard?tab={h(tab_name)}">{h(label)}</a>'


def render_subtab_link(tab_name, view_name, label, active_view):
    active_class = " is-active" if view_name == active_view else ""
    return f'<a class="sub-link{active_class}" href="/dashboard?tab={h(tab_name)}&vehicles_view={h(view_name)}">{h(label)}</a>'


def tab_panel_classes(tab_name, active_tab, base_classes):
    active_class = " is-active" if tab_name == active_tab else ""
    return f"{base_classes} tab-panel{active_class}"


def render_brand_lockup(compact=False):
    brand_class = "brand-lockup compact" if compact else "brand-lockup"
    subtitle = f'<span class="brand-tag">{h(APP_TAGLINE)}</span>' if not compact else ""
    return f"""
    <div class="{brand_class}">
      <span class="brand-mark" aria-hidden="true">RS</span>
      <div class="brand-copy">
        <span class="brand-name">{h(APP_BRAND)}</span>
        {subtitle}
      </div>
    </div>
    """


def render_stat(label, value):
    return f'<article class="stat-card"><strong>{h(value)}</strong><span>{h(label)}</span></article>'


def render_vehicle_options(vehicles, selected_id=None):
    if not vehicles:
        return '<option value="">Add a vehicle first</option>'
    return "".join(
        f'<option value="{vehicle["id"]}" {"selected" if str(vehicle["id"]) == str(selected_id) else ""}>{h(vehicle["name"])} - {h(vehicle["plate"])}</option>'
        for vehicle in vehicles
    )


def render_driver_options(drivers):
    if not drivers:
        return '<option value="">Add a driver first</option>'
    return "".join(f'<option value="{driver["id"]}">{h(driver["name"])}</option>' for driver in drivers)


def render_assignment_form(vehicles, drivers):
    if not vehicles or not drivers:
        return '<div class="empty-state">Add at least one vehicle and one driver before creating assignments.</div>'
    return f"""
    <form method="post" action="/assignments/add" class="form-grid">
      <label><span>Vehicle</span><select name="vehicle_id" required>{render_vehicle_options(vehicles)}</select></label>
      <label><span>Driver</span><select name="driver_id" required>{render_driver_options(drivers)}</select></label>
      <label><span>Start date</span><input type="date" name="start_date" value="{date.today().isoformat()}" required></label>
      <label><span>End date</span><input type="date" name="end_date"></label>
      <label class="full-span"><span>Notes</span><textarea name="notes" rows="3"></textarea></label>
      <button type="submit" class="primary-btn">Save assignment</button>
    </form>
    """


def render_maintenance_form(vehicles):
    if not vehicles:
        return '<div class="empty-state">Add a vehicle first to log service records.</div>'
    return f"""
    <form method="post" action="/maintenance/add" class="form-grid">
      <label><span>Vehicle</span><select name="vehicle_id" required>{render_vehicle_options(vehicles)}</select></label>
      <label><span>Service type</span><input type="text" name="service_type" required></label>
      <label><span>Service date</span><input type="date" name="service_date" value="{date.today().isoformat()}" required></label>
      <label><span>Odometer</span><input type="number" name="odometer" min="0" required></label>
      <label><span>Cost</span><input type="number" name="cost" min="0" step="0.01" required></label>
      <label><span>Next due date</span><input type="date" name="next_due_date"></label>
      <label><span>Next due odometer</span><input type="number" name="next_due_odometer" min="0"></label>
      {render_upload_field("Invoice or photo", "maintenance-attachment-new", "attachment_name", "attachment_data", ".pdf,image/*")}
      <label class="full-span"><span>Notes</span><textarea name="notes" rows="3"></textarea></label>
      <button type="submit" class="primary-btn">Save service</button>
    </form>
    """


def render_fuel_form(vehicles):
    if not vehicles:
        return '<div class="empty-state">Add a vehicle first to log fuel usage.</div>'
    return f"""
    <form method="post" action="/fuel/add" class="form-grid">
      <label><span>Vehicle</span><select name="vehicle_id" required>{render_vehicle_options(vehicles)}</select></label>
      <label><span>Fill date</span><input type="date" name="fill_date" value="{date.today().isoformat()}" required></label>
      <label><span>Odometer</span><input type="number" name="odometer" min="0" required></label>
      <label><span>Liters</span><input type="number" name="liters" min="0" step="0.01" required></label>
      <label><span>Total cost</span><input type="number" name="total_cost" min="0" step="0.01" required></label>
      <label><span>Station</span><input type="text" name="station"></label>
      <label class="checkbox-label"><input type="checkbox" name="full_tank" checked> Full tank fill</label>
      <label class="full-span"><span>Notes</span><textarea name="notes" rows="3"></textarea></label>
      <button type="submit" class="primary-btn">Save fuel log</button>
    </form>
    """


def render_reminder_form(vehicles):
    if not vehicles:
        return '<div class="empty-state">Add a vehicle first to create reminders.</div>'
    return f"""
    <form method="post" action="/reminders/add" class="form-grid">
      <label><span>Vehicle</span><select name="vehicle_id" required>{render_vehicle_options(vehicles)}</select></label>
      <label><span>Title</span><input type="text" name="title" required></label>
      <label><span>Due date</span><input type="date" name="due_date"></label>
      <label><span>Due odometer</span><input type="number" name="due_odometer" min="0"></label>
      <label class="full-span"><span>Notes</span><textarea name="notes" rows="3"></textarea></label>
      <button type="submit" class="primary-btn">Save reminder</button>
    </form>
    """


def render_gps_form(vehicles, active_trip=None):
    if not vehicles:
        return '<div class="empty-state">Add a vehicle first before logging GPS positions.</div>'
    trip_id = row_value(active_trip, "id") or ""
    active_vehicle_id = row_value(active_trip, "vehicle_id") or ""
    return f"""
    <form method="post" action="/gps/add" class="form-grid tracking-form" data-gps-form data-trip-log-form>
      <input type="hidden" name="trip_id" value="{h(trip_id)}">
      <label><span>Vehicle</span><select name="vehicle_id" required>{render_vehicle_options(vehicles, active_vehicle_id)}</select></label>
      <label><span>Latitude</span><input type="text" name="latitude" readonly required></label>
      <label><span>Longitude</span><input type="text" name="longitude" readonly required></label>
      <label><span>Accuracy (meters)</span><input type="text" name="accuracy_meters" readonly></label>
      <div class="gps-actions full-span">
        <button type="button" class="ghost-btn" data-capture-gps>Use my live location</button>
        <button type="submit" class="primary-btn">Save GPS location</button>
      </div>
      <p class="muted full-span">Use this when you want one exact checkpoint. On phones, allow location access when FleetCare asks.</p>
    </form>
    """


def render_trip_controls(vehicles, active_trip):
    if active_trip:
        return f"""
        <div class="trip-card">
          <div class="item-head">
            <div class="item-title-row">
              <div class="item-title">{h(row_value(active_trip, 'label') or 'Active trip')}</div>
              <span class="badge warning">In progress</span>
            </div>
            <strong>{h(row_value(active_trip, 'vehicle_name'))} - {h(row_value(active_trip, 'plate'))}</strong>
          </div>
          <div class="muted">Started: {h(row_value(active_trip, 'started_at'))}</div>
          <p class="muted trip-note">FleetCare keeps saving route points while this screen stays active. In the Android app, it also refreshes again as soon as the app comes back to the foreground.</p>
          <form method="post" action="/trips/stop" class="form-grid compact-form tracking-form" data-gps-form>
            <input type="hidden" name="trip_id" value="{h(row_value(active_trip, 'id'))}">
            <label class="full-span"><span>Stop note</span><input type="text" name="label" value="{h(row_value(active_trip, 'label') or '')}" readonly></label>
            <label><span>Latitude</span><input type="text" name="latitude" readonly></label>
            <label><span>Longitude</span><input type="text" name="longitude" readonly></label>
            <label><span>Accuracy (meters)</span><input type="text" name="accuracy_meters" readonly></label>
            <div class="gps-actions full-span">
              <button type="button" class="ghost-btn" data-capture-gps>Capture stop location</button>
              <button type="submit" class="danger-btn">Stop trip</button>
            </div>
          </form>
        </div>
        """

    if not vehicles:
        return '<div class="empty-state">Add a vehicle first before starting a trip.</div>'

    return f"""
    <form method="post" action="/trips/start" class="form-grid trip-card tracking-form" data-gps-form data-auto-gps>
      <label><span>Vehicle</span><select name="vehicle_id" required>{render_vehicle_options(vehicles)}</select></label>
      <label><span>Trip label</span><input type="text" name="label" placeholder="Morning route"></label>
      <label><span>Latitude</span><input type="text" name="latitude" readonly></label>
      <label><span>Longitude</span><input type="text" name="longitude" readonly></label>
      <label><span>Accuracy (meters)</span><input type="text" name="accuracy_meters" readonly></label>
      <div class="gps-actions full-span">
        <button type="button" class="ghost-btn" data-capture-gps>Capture start location</button>
        <button type="submit" class="primary-btn">Start trip</button>
      </div>
      <p class="muted full-span">Trip mode is best for route history. FleetCare saves a start point, then keeps collecting GPS checkpoints while the trip stays active.</p>
    </form>
    """


def render_tracking_status(active_trip, gps_logs):
    latest_point = gps_logs[0] if gps_logs else None
    active_label = "Trip active" if active_trip else "Ready"
    active_tone = "warning" if active_trip else "active"
    last_saved = h(row_value(latest_point, "created_at") or "No GPS point saved yet")
    vehicle_name = h(row_value(active_trip, "vehicle_name") or row_value(latest_point, "vehicle_name") or "No vehicle selected")
    plate = h(row_value(active_trip, "plate") or row_value(latest_point, "plate") or "")
    location_text = "No coordinates saved yet."
    if latest_point:
        location_text = f"{round(float(row_value(latest_point, 'latitude')), 6)}, {round(float(row_value(latest_point, 'longitude')), 6)}"

    return f"""
    <div class="tracking-status" data-tracking-summary>
      <div class="tracking-status__hero">
        <div>
          <div class="item-title-row">
            <div class="item-title">{h(APP_BRAND)} GPS</div>
            <span class="badge {active_tone}" data-tracking-mode>{active_label}</span>
          </div>
          <p class="muted">Use manual capture for one checkpoint, or start a trip for ongoing route collection.</p>
        </div>
        <button type="button" class="ghost-btn" data-request-location>Allow location access</button>
      </div>
      <div class="tracking-grid">
        <div class="tracking-pill">
          <strong>Tracking target</strong>
          <span>{vehicle_name}{f" - {plate}" if plate else ""}</span>
        </div>
        <div class="tracking-pill">
          <strong>Last saved point</strong>
          <span data-tracking-last-saved>{last_saved}</span>
        </div>
        <div class="tracking-pill">
          <strong>Last coordinates</strong>
          <span>{location_text}</span>
        </div>
      </div>
      <div class="flash error tracking-error" data-tracking-error hidden></div>
      <div class="tracking-tips">
        <div class="tracking-tip">
          <strong>Browser mode</strong>
          <span>Manual capture and trip logging work through the live {h(APP_BRAND)} link.</span>
        </div>
        <div class="tracking-tip">
          <strong>Android app mode</strong>
          <span>The wrapper is now prepared for location permissions, notifications, and the release paperwork needed for deeper background tracking.</span>
        </div>
      </div>
    </div>
    """


def render_alerts(alerts):
    if not alerts:
        return '<div class="empty-state">No urgent alerts right now.</div>'
    return "".join(
        f"""
        <article class="list-item">
          <div class="item-head">
            <div class="item-title-row">
              <div class="item-title">{h(alert['title'])}</div>
              <span class="badge {h(alert['tone'])}">{h(alert['label'])}</span>
            </div>
            <strong>{h(alert['context'])}</strong>
          </div>
          <div class="muted">{h(alert['details'])}</div>
        </article>
        """
        for alert in alerts
    )


def render_vehicles(vehicles):
    if not vehicles:
        return '<div class="empty-state">No vehicles yet.</div>'
    return "".join(
        f"""
        <article class="list-item">
          {render_media_preview(row_value(vehicle, 'photo_data'), row_value(vehicle, 'photo_name'), 'Vehicle photo')}
          <div class="item-head">
            <div class="item-title-row">
              <div class="item-title">{h(vehicle['name'])}</div>
              <span class="badge active">{h(vehicle['status'])}</span>
            </div>
            <strong>{h(vehicle['plate'])}</strong>
          </div>
          <div class="muted">{h(vehicle['model'] or 'Model not set')} {('- ' + str(vehicle['year'])) if vehicle['year'] else ''}</div>
          <div class="muted">{vehicle['odometer']} km</div>
          {render_vehicle_location(vehicle)}
          <details class="edit-box">
            <summary>Edit vehicle</summary>
            <form method="post" action="/vehicles/update" class="form-grid compact-form">
              <input type="hidden" name="vehicle_id" value="{vehicle['id']}">
              <label><span>Name</span><input type="text" name="name" value="{h(vehicle['name'])}" required></label>
              <label><span>Plate</span><input type="text" name="plate" value="{h(vehicle['plate'])}" required></label>
              <label><span>Model</span><input type="text" name="model" value="{h(vehicle['model'] or '')}"></label>
              <label><span>Year</span><input type="number" name="year" min="1990" max="2100" value="{h(vehicle['year'] or '')}"></label>
              <label><span>Odometer</span><input type="number" name="odometer" min="0" value="{vehicle['odometer']}" required></label>
              <label>
                <span>Status</span>
                <select name="status">
                  {render_status_options(vehicle['status'], ['Active', 'In service', 'Inactive'])}
                </select>
              </label>
              {render_upload_field("Vehicle photo", f"vehicle-photo-{vehicle['id']}", "photo_name", "photo_data", "image/*", capture=True, existing_name=row_value(vehicle, 'photo_name'), existing_data=row_value(vehicle, 'photo_data'))}
              <button type="submit" class="primary-btn">Save changes</button>
            </form>
            <form method="post" action="/vehicles/delete" class="delete-form" onsubmit="return confirm('Delete this vehicle and its related records?');">
              <input type="hidden" name="vehicle_id" value="{vehicle['id']}">
              <button type="submit" class="danger-btn">Delete vehicle</button>
            </form>
          </details>
        </article>
        """
        for vehicle in vehicles
    )


def render_drivers(drivers):
    if not drivers:
        return '<div class="empty-state">No drivers yet.</div>'
    return "".join(
        f"""
        <article class="list-item">
          <div class="item-head">
            <div class="item-title-row">
              <div class="item-title">{h(driver['name'])}</div>
              <span class="badge active">{h(driver['status'])}</span>
            </div>
            <strong>{h(driver['license_number'] or 'No license number')}</strong>
          </div>
          <div class="muted">{h(driver['phone'] or 'No phone')} | {h(driver['email'] or 'No email')}</div>
          <details class="edit-box">
            <summary>Edit driver</summary>
            <form method="post" action="/drivers/update" class="form-grid compact-form">
              <input type="hidden" name="driver_id" value="{driver['id']}">
              <label><span>Name</span><input type="text" name="name" value="{h(driver['name'])}" required></label>
              <label><span>License number</span><input type="text" name="license_number" value="{h(driver['license_number'] or '')}"></label>
              <label><span>Phone</span><input type="text" name="phone" value="{h(driver['phone'] or '')}"></label>
              <label><span>Email</span><input type="email" name="email" value="{h(driver['email'] or '')}"></label>
              <label>
                <span>Status</span>
                <select name="status">
                  {render_status_options(driver['status'], ['Active', 'Vacation', 'Inactive'])}
                </select>
              </label>
              <button type="submit" class="primary-btn">Save changes</button>
            </form>
            <form method="post" action="/drivers/delete" class="delete-form" onsubmit="return confirm('Delete this driver and their assignments?');">
              <input type="hidden" name="driver_id" value="{driver['id']}">
              <button type="submit" class="danger-btn">Delete driver</button>
            </form>
          </details>
        </article>
        """
        for driver in drivers
    )


def render_status_options(current_value, options):
    return "".join(
        f'<option value="{h(option)}" {"selected" if option == current_value else ""}>{h(option)}</option>'
        for option in options
    )


def render_assignments(assignments):
    if not assignments:
        return '<div class="empty-state">No assignments yet.</div>'
    return "".join(
        f"""
        <article class="list-item">
          <div class="item-head">
            <div class="item-title-row">
              <div class="item-title">{h(item['vehicle_name'])}</div>
              <span class="badge {'active' if item['active'] else 'warning'}">{'Active' if item['active'] else 'Past'}</span>
            </div>
            <strong>{h(item['driver_name'])}</strong>
          </div>
          <div class="muted">From {h(item['start_date'])} {f"to {h(item['end_date'])}" if item['end_date'] else ''}</div>
          <div class="muted">{h(item['notes'] or 'No notes')}</div>
        </article>
        """
        for item in assignments
    )


def render_maintenance_logs(maintenance):
    if not maintenance:
        return '<div class="empty-state">No maintenance history yet.</div>'
    return "".join(
        f"""
        <article class="list-item">
          {render_media_preview(row_value(item, 'attachment_data'), row_value(item, 'attachment_name'), 'Attachment')}
          <div class="item-head">
            <div class="item-title-row">
              <div class="item-title">{h(item['service_type'])}</div>
              <span class="badge active">{h(item['vehicle_name'])}</span>
            </div>
            <strong>{money(item['cost'])}</strong>
          </div>
          <div class="muted">{h(item['service_date'])} | {item['odometer']} km</div>
          <div class="muted">{h(item['notes'] or 'No notes')}</div>
        </article>
        """
        for item in maintenance
    )


def render_fuel_logs(fuel_logs):
    if not fuel_logs:
        return '<div class="empty-state">No fuel logs yet.</div>'
    return "".join(
        f"""
        <article class="list-item">
          <div class="item-head">
            <div class="item-title-row">
              <div class="item-title">{h(item['vehicle_name'])}</div>
              <span class="badge active">{round(item['price_per_liter'], 2)} / L</span>
            </div>
            <strong>{money(item['total_cost'])}</strong>
          </div>
          <div class="muted">{h(item['fill_date'])} | {item['liters']} L | {item['odometer']} km</div>
          <div class="muted">{h(item['station'] or 'Station not set')} | {'Full tank' if item['full_tank'] else 'Partial fill'}</div>
        </article>
        """
        for item in fuel_logs
    )


def render_gps_logs(gps_logs):
    if not gps_logs:
        return '<div class="empty-state">No GPS points saved yet.</div>'
    return "".join(
        f"""
        <article class="list-item">
          <div class="item-head">
            <div class="item-title-row">
              <div class="item-title">{h(item['vehicle_name'])}</div>
              <span class="badge active">{h(item['created_at'])}</span>
            </div>
            <strong>{h(item['plate'])}</strong>
          </div>
          <div class="muted">{round(float(item['latitude']), 6)}, {round(float(item['longitude']), 6)}</div>
          <div class="muted">{format_accuracy(item['accuracy_meters'])}</div>
          <a class="ghost-btn map-link" href="{gps_map_url(item['latitude'], item['longitude'])}" target="_blank" rel="noreferrer">Open in maps</a>
        </article>
        """
        for item in gps_logs
    )


def collect_alerts(reminders, assignments):
    today_value = date.today()
    alerts = []

    for reminder in reminders:
        due_date = parse_iso_date(reminder["due_date"])
        days_left = (due_date - today_value).days if due_date else None
        due_odometer = reminder["due_odometer"]
        overdue_by_mileage = due_odometer is not None and reminder["vehicle_odometer"] >= due_odometer
        soon_by_mileage = due_odometer is not None and reminder["vehicle_odometer"] >= due_odometer - 500

        if due_date and days_left < 0 or overdue_by_mileage:
            alerts.append(
                {
                    "title": reminder["title"],
                    "label": "Overdue",
                    "tone": "danger",
                    "context": reminder["vehicle_name"],
                    "details": build_reminder_details(reminder, days_left),
                }
            )
        elif (days_left is not None and days_left <= 7) or soon_by_mileage:
            alerts.append(
                {
                    "title": reminder["title"],
                    "label": "Soon",
                    "tone": "warning",
                    "context": reminder["vehicle_name"],
                    "details": build_reminder_details(reminder, days_left),
                }
            )

    for assignment in assignments:
        if not assignment["active"] or not assignment["end_date"]:
            continue
        end_date = parse_iso_date(assignment["end_date"])
        if not end_date:
            continue
        days_left = (end_date - today_value).days
        if days_left <= 3:
            alerts.append(
                {
                    "title": "Assignment ending soon",
                    "label": "Soon" if days_left >= 0 else "Expired",
                    "tone": "warning" if days_left >= 0 else "danger",
                    "context": assignment["vehicle_name"],
                    "details": f"{assignment['driver_name']} assignment ends on {assignment['end_date']}.",
                }
            )

    alerts.sort(key=lambda alert: (0 if alert["tone"] == "danger" else 1, alert["title"]))
    return alerts


def build_reminder_details(reminder, days_left):
    parts = []
    if reminder["due_date"]:
        if days_left is not None:
            when = f"{abs(days_left)} day(s) ago" if days_left < 0 else f"in {days_left} day(s)"
            parts.append(f"Due date {reminder['due_date']} ({when})")
    if reminder["due_odometer"] is not None:
        parts.append(f"Target {reminder['due_odometer']} km, current {reminder['vehicle_odometer']} km")
    if reminder["notes"]:
        parts.append(reminder["notes"])
    return " | ".join(parts) if parts else "Reminder has no extra details."


def build_stats(vehicles, maintenance, fuel_logs, reminders):
    fuel_spend = sum(item["total_cost"] for item in fuel_logs)
    maintenance_spend = sum(item["cost"] for item in maintenance)
    avg_fuel_price = (sum(item["price_per_liter"] for item in fuel_logs) / len(fuel_logs)) if fuel_logs else 0
    return {
        "vehicle_count": len(vehicles),
        "maintenance_spend": maintenance_spend,
        "fuel_spend": fuel_spend,
        "avg_fuel_price": avg_fuel_price,
        "reminders": len(reminders),
    }


def parse_report_period(query):
    month = query.get("month", [""])[0]
    if month:
        try:
            start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start.month + 1)
            return start.isoformat(), end.isoformat(), start.strftime("%B %Y")
        except ValueError:
            pass

    start_date = query.get("start_date", [""])[0]
    end_date = query.get("end_date", [""])[0]
    start = parse_iso_date(start_date)
    end = parse_iso_date(end_date)

    if start and end and end < start:
        start, end = end, start

    if start and end:
        return start.isoformat(), end.isoformat(), f"{start.isoformat()} to {end.isoformat()}"
    if start:
        return start.isoformat(), None, f"From {start.isoformat()}"
    if end:
        return None, end.isoformat(), f"Through {end.isoformat()}"
    return None, None, "All available dates"


def report_date_filter(column, start_date, end_date, base_params):
    conditions = []
    params = list(base_params)

    if start_date:
        conditions.append(f"{column} >= ?")
        params.append(start_date)
    if end_date:
        conditions.append(f"{column} <= ?")
        params.append(end_date)

    if not conditions:
        return "", params
    return " AND " + " AND ".join(conditions), params


def parse_iso_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def money(value):
    return f"${float(value or 0):,.2f}"


def slugify(value):
    text = "".join(char.lower() if char.isalnum() else "-" for char in value)
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-") or "roadsmith-fleet"


def row_value(row, key):
    if row is None:
        return None
    if hasattr(row, "keys") and key in row.keys():
        return row[key]
    try:
        return row[key]
    except Exception:
        return None


def clean_upload_name(value):
    return (value or "").strip()[:160] or None


def clean_upload_data(value):
    data = (value or "").strip()
    if not data.startswith("data:"):
        return None
    return data[:4_000_000]


def render_upload_field(label, input_id, name_field, data_field, accept, capture=False, existing_name="", existing_data=""):
    capture_attr = ' capture="environment"' if capture else ""
    preview = render_media_preview(existing_data, existing_name, label, preview_class="upload-preview")
    current_name = h(existing_name or "")
    current_data = h(existing_data or "")
    return f"""
    <div class="upload-field full-span">
      <span>{h(label)}</span>
      <input
        id="{h(input_id)}"
        type="file"
        accept="{h(accept)}"{capture_attr}
        data-encode-target="{h(data_field)}"
        data-name-target="{h(name_field)}"
        data-preview-target="{h(input_id)}-preview"
      >
      <input type="hidden" name="{h(name_field)}" value="{current_name}">
      <input type="hidden" name="{h(data_field)}" value="{current_data}">
      <div id="{h(input_id)}-preview">{preview}</div>
      <small class="muted">On phones, you can pick a saved file or take a new photo.</small>
    </div>
    """


def render_media_preview(data_url, file_name, alt_text, preview_class="attachment-preview"):
    if not data_url:
        return ""
    safe_url = h(data_url)
    safe_name = h(file_name or alt_text)
    if data_url.startswith("data:image/"):
        return f'<div class="{preview_class}"><img src="{safe_url}" alt="{h(alt_text)}"><span>{safe_name}</span></div>'
    return f'<div class="{preview_class}"><a href="{safe_url}" download="{safe_name}" class="ghost-btn">Open {safe_name}</a></div>'


def build_mobile_reminders(reminders):
    items = []
    for reminder in reminders:
        if not reminder["due_date"]:
            continue
        items.append(
            {
                "id": int(reminder["id"]),
                "title": reminder["title"],
                "vehicle": reminder["vehicle_name"],
                "dueDate": reminder["due_date"],
                "notes": reminder["notes"] or "",
            }
        )
    return items


def build_tracking_payload(active_trip, gps_logs):
    latest_point = gps_logs[0] if gps_logs else None
    return {
        "tripActive": bool(active_trip),
        "tripId": row_value(active_trip, "id"),
        "tripVehicle": row_value(active_trip, "vehicle_name"),
        "lastSavedAt": str(row_value(latest_point, "created_at") or ""),
        "lastVehicle": row_value(latest_point, "vehicle_name"),
    }


def render_vehicle_location(vehicle):
    latitude = row_value(vehicle, "last_latitude")
    longitude = row_value(vehicle, "last_longitude")
    recorded_at = row_value(vehicle, "last_location_at")
    if latitude is None or longitude is None:
        return '<div class="muted">Last GPS: not captured yet.</div>'

    return f"""
    <div class="gps-summary">
      <div class="muted">Last GPS: {round(float(latitude), 6)}, {round(float(longitude), 6)} {f'| {h(recorded_at)}' if recorded_at else ''}</div>
      <a class="ghost-btn map-link" href="{gps_map_url(latitude, longitude)}" target="_blank" rel="noreferrer">Open in maps</a>
    </div>
    """


def gps_map_url(latitude, longitude):
    return f"https://www.google.com/maps?q={float(latitude):.6f},{float(longitude):.6f}"


def format_accuracy(value):
    if value is None:
        return "Accuracy not provided."
    return f"Accuracy: {round(float(value), 1)} meters"


def parse_coordinate(value):
    text = (value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def render_trip_history(trips):
    if not trips:
        return '<div class="empty-state">No trips recorded yet.</div>'
    return "".join(
        f"""
        <article class="list-item">
          <div class="item-head">
            <div class="item-title-row">
              <div class="item-title">{h(row_value(trip, 'label') or 'Trip')}</div>
              <span class="badge {'warning' if row_value(trip, 'status') == 'Active' else 'active'}">{h(row_value(trip, 'status'))}</span>
            </div>
            <strong>{h(row_value(trip, 'vehicle_name'))} - {h(row_value(trip, 'plate'))}</strong>
          </div>
          <div class="muted">Started: {h(row_value(trip, 'started_at'))}</div>
          <div class="muted">{f"Ended: {h(row_value(trip, 'ended_at'))}" if row_value(trip, 'ended_at') else "Trip still active."}</div>
          <div class="muted">{int(row_value(trip, 'point_count') or 0)} GPS points logged</div>
          <div class="trip-map" data-trip-map data-trip-id="{h(row_value(trip, 'id'))}">Route map will load here.</div>
        </article>
        """
        for trip in trips
    )


def build_trip_routes(trip_points):
    routes = {}
    for point in trip_points:
        trip_id = row_value(point, "trip_id")
        if trip_id is None:
            continue
        routes.setdefault(str(trip_id), []).append(
            {
                "lat": float(row_value(point, "latitude")),
                "lng": float(row_value(point, "longitude")),
                "at": str(row_value(point, "created_at") or ""),
            }
        )
    return routes
