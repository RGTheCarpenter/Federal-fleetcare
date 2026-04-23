import html
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


def run():
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), FleetCareHandler)
    print(f"FleetCare running on http://{HOST}:{PORT}")
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
                INSERT INTO vehicles (user_id, name, plate, model, year, odometer, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    form.get("name", ""),
                    form.get("plate", "").upper(),
                    form.get("model", ""),
                    int(form.get("year") or 0) or None,
                    int(form.get("odometer") or 0),
                    form.get("status", "Active"),
                ),
            )

        self.redirect("/dashboard#vehicles")

    def handle_vehicle_update(self, user, form):
        vehicle_id = int(form.get("vehicle_id") or 0)
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE vehicles
                SET name = ?, plate = ?, model = ?, year = ?, odometer = ?, status = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    form.get("name", ""),
                    form.get("plate", "").upper(),
                    form.get("model", ""),
                    int(form.get("year") or 0) or None,
                    int(form.get("odometer") or 0),
                    form.get("status", "Active"),
                    vehicle_id,
                    user["id"],
                ),
            )

        self.redirect("/dashboard#vehicles")

    def handle_vehicle_delete(self, user, form):
        vehicle_id = int(form.get("vehicle_id") or 0)
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM vehicles WHERE id = ? AND user_id = ?",
                (vehicle_id, user["id"]),
            )

        self.redirect("/dashboard#vehicles")

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

        self.redirect("/dashboard#drivers")

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

        self.redirect("/dashboard#drivers")

    def handle_driver_delete(self, user, form):
        driver_id = int(form.get("driver_id") or 0)
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM drivers WHERE id = ? AND user_id = ?",
                (driver_id, user["id"]),
            )

        self.redirect("/dashboard#drivers")

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

        self.redirect("/dashboard#assignments")

    def handle_maintenance_add(self, user, form):
        vehicle_id = int(form.get("vehicle_id") or 0)
        odometer = int(form.get("odometer") or 0)

        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO maintenance_logs
                (user_id, vehicle_id, service_type, service_date, odometer, cost, notes, next_due_date, next_due_odometer)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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

        self.redirect("/dashboard#maintenance")

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

        self.redirect("/dashboard#fuel")

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

        self.redirect("/dashboard#reminders")

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
            <p class="kicker">FleetCare</p>
            <h1>{title}</h1>
            <p class="muted">Manage fleet maintenance, fuel, assignments, reports, and alerts in one place.</p>
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
        return self.send_html(page("FleetCare", content))

    def render_dashboard(self, route):
        user = self.require_user()
        if not user:
            return

        with get_connection() as connection:
            vehicles = connection.execute(
                "SELECT * FROM vehicles WHERE user_id = ? ORDER BY created_at DESC",
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

        alerts = collect_alerts(reminders, assignments)
        stats = build_stats(vehicles, maintenance, fuel_logs, reminders)

        content = f"""
        <div class="page-shell">
          <header class="hero">
            <div>
              <p class="kicker">Fleet operations</p>
              <h1>{h(user["company_name"])}</h1>
            </div>
            <div class="hero-actions">
              <form method="post" action="/logout">
                <button type="submit" class="ghost-btn">Sign out</button>
              </form>
            </div>
          </header>

          <section class="report-panel">
            <div>
              <p class="section-kicker">Reports</p>
              <h2>Download PDF report</h2>
            </div>
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
          </section>

          <nav class="quick-links" aria-label="Dashboard sections">
            <button class="quick-link is-active" type="button" data-tab-target="vehicles">Vehicles</button>
            <button class="quick-link" type="button" data-tab-target="drivers">Drivers</button>
            <button class="quick-link" type="button" data-tab-target="assignments">Assignments</button>
            <button class="quick-link" type="button" data-tab-target="maintenance">Maintenance</button>
            <button class="quick-link" type="button" data-tab-target="fuel">Fuel</button>
            <button class="quick-link" type="button" data-tab-target="alerts">Alerts</button>
          </nav>

          <section class="stats-grid">
            {render_stat("Vehicles", len(vehicles))}
            {render_stat("Drivers", len(drivers))}
            {render_stat("Open alerts", len(alerts))}
            {render_stat("Fuel spend", money(stats["fuel_spend"]))}
            {render_stat("Maintenance spend", money(stats["maintenance_spend"]))}
            {render_stat("Avg fuel price", money(stats["avg_fuel_price"]))}
          </section>

          <section class="panel span-two tab-panel" data-tab-section="alerts">
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
            <section class="panel tab-panel" id="vehicles" data-tab-section="vehicles">
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
                <button type="submit" class="primary-btn">Save vehicle</button>
              </form>
            </section>

            <section class="panel tab-panel" id="drivers" data-tab-section="drivers">
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

            <section class="panel tab-panel" id="assignments" data-tab-section="assignments">
              <div class="panel-header"><div><p class="section-kicker">Assignments</p><h2>Assign vehicle</h2></div></div>
              {render_assignment_form(vehicles, drivers)}
            </section>

            <section class="panel tab-panel" id="maintenance" data-tab-section="maintenance">
              <div class="panel-header"><div><p class="section-kicker">Maintenance</p><h2>Log service</h2></div></div>
              {render_maintenance_form(vehicles)}
            </section>

            <section class="panel tab-panel" id="fuel" data-tab-section="fuel">
              <div class="panel-header"><div><p class="section-kicker">Fuel</p><h2>Log fuel fill</h2></div></div>
              {render_fuel_form(vehicles)}
            </section>

            <section class="panel tab-panel" id="reminders" data-tab-section="alerts">
              <div class="panel-header"><div><p class="section-kicker">Reminders</p><h2>Create alert reminder</h2></div></div>
              {render_reminder_form(vehicles)}
            </section>

            <section class="panel span-two tab-panel" data-tab-section="vehicles">
              <div class="panel-header"><div><p class="section-kicker">Current state</p><h2>Vehicles</h2></div></div>
              <div class="stack-list">{render_vehicles(vehicles)}</div>
            </section>

            <section class="panel span-two tab-panel" data-tab-section="drivers">
              <div class="panel-header"><div><p class="section-kicker">Current state</p><h2>Drivers</h2></div></div>
              <div class="stack-list">{render_drivers(drivers)}</div>
            </section>

            <section class="panel span-two tab-panel" data-tab-section="assignments">
              <div class="panel-header"><div><p class="section-kicker">Assignments</p><h2>Driver assignments</h2></div></div>
              <div class="stack-list">{render_assignments(assignments)}</div>
            </section>

            <section class="panel span-two tab-panel" data-tab-section="maintenance">
              <div class="panel-header"><div><p class="section-kicker">History</p><h2>Maintenance history</h2></div></div>
              <div class="stack-list">{render_maintenance_logs(maintenance)}</div>
            </section>

            <section class="panel span-two tab-panel" data-tab-section="fuel">
              <div class="panel-header"><div><p class="section-kicker">Consumption</p><h2>Fuel history</h2></div></div>
              <div class="stack-list">{render_fuel_logs(fuel_logs)}</div>
            </section>
          </main>
        </div>
        """
        return self.send_html(page("FleetCare Dashboard", content))

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

    def send_html(self, payload):
        data = payload.encode("utf-8")
        self.send_response(200)
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
  <title>{h(title)}</title>
  <link rel="stylesheet" href="/static/styles.css">
  <script src="/static/app.js" defer></script>
</head>
<body>{content}</body>
</html>"""


def h(value):
    return html.escape(str(value or ""))


def render_stat(label, value):
    return f'<article class="stat-card"><strong>{h(value)}</strong><span>{h(label)}</span></article>'


def render_vehicle_options(vehicles):
    if not vehicles:
        return '<option value="">Add a vehicle first</option>'
    return "".join(f'<option value="{vehicle["id"]}">{h(vehicle["name"])} - {h(vehicle["plate"])}</option>' for vehicle in vehicles)


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
          <div class="item-head">
            <div class="item-title-row">
              <div class="item-title">{h(vehicle['name'])}</div>
              <span class="badge active">{h(vehicle['status'])}</span>
            </div>
            <strong>{h(vehicle['plate'])}</strong>
          </div>
          <div class="muted">{h(vehicle['model'] or 'Model not set')} {('- ' + str(vehicle['year'])) if vehicle['year'] else ''}</div>
          <div class="muted">{vehicle['odometer']} km</div>
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
    return text.strip("-") or "fleetcare"
