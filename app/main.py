from html import escape

from fastapi import Cookie, FastAPI, Form
from fastapi.responses import HTMLResponse

from app.db import (
    create_password_reset_token,
    create_session,
    create_user,
    delete_session,
    delete_sessions_for_user,
    ensure_default_user,
    get_password_reset_token,
    get_session,
    get_user_by_email,
    get_user_by_id,
    get_user_by_session_token,
    initialize_database,
    mark_password_reset_token_used,
    update_user_password,
    verify_password,
)

app = FastAPI(title="AI Hackaton")

SESSION_COOKIE_NAME = "session_token"
SESSION_MAX_AGE_SECONDS = 24 * 60 * 60


@app.on_event("startup")
def startup() -> None:
    initialize_database()
    ensure_default_user()


def render_page(
    page_title: str,
    heading: str,
    subtitle: str,
    content: str,
    *,
    width: str = "440px",
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    message_block = f'<p class="message {message_kind}">{escape(message)}</p>' if message else ""

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
        <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>{escape(page_title)}</title>
            <style>
                :root {{
                    color-scheme: light;
                    font-family: Inter, "Segoe UI", Arial, sans-serif;
                    --bg: #0f172a;
                    --panel: rgba(255, 255, 255, 0.96);
                    --text: #0f172a;
                    --muted: #64748b;
                    --accent: #2563eb;
                    --accent-hover: #1d4ed8;
                    --border: #dbe4f0;
                    --success: #166534;
                    --error: #b91c1c;
                    --info: #1d4ed8;
                    --shadow: 0 24px 60px rgba(15, 23, 42, 0.28);
                }}

                * {{ box-sizing: border-box; }}

                body {{
                    margin: 0;
                    min-height: 100vh;
                    display: grid;
                    place-items: center;
                    background:
                        radial-gradient(circle at top, rgba(37, 99, 235, 0.35), transparent 28%),
                        linear-gradient(135deg, #0f172a, #111827 55%, #1e293b);
                    color: var(--text);
                    padding: 24px;
                }}

                .card {{
                    width: min(100%, {width});
                    background: var(--panel);
                    border: 1px solid rgba(255, 255, 255, 0.45);
                    border-radius: 24px;
                    box-shadow: var(--shadow);
                    padding: 32px;
                }}

                .eyebrow {{
                    margin: 0 0 12px;
                    color: var(--accent);
                    font-size: 0.85rem;
                    font-weight: 700;
                    letter-spacing: 0.12em;
                    text-transform: uppercase;
                }}

                h1 {{
                    margin: 0 0 10px;
                    font-size: 2rem;
                    line-height: 1.1;
                }}

                p.subtitle {{
                    margin: 0 0 24px;
                    color: var(--muted);
                    line-height: 1.5;
                }}

                .message {{
                    margin: 0 0 16px;
                    padding: 12px 14px;
                    border-radius: 12px;
                    font-size: 0.95rem;
                }}

                .message.info {{ background: rgba(37, 99, 235, 0.08); color: var(--info); }}
                .message.success {{ background: rgba(22, 101, 52, 0.08); color: var(--success); }}
                .message.error {{ background: rgba(185, 28, 28, 0.08); color: var(--error); }}

                label {{
                    display: block;
                    margin: 0 0 8px;
                    font-size: 0.95rem;
                    font-weight: 600;
                }}

                .field {{ margin-bottom: 18px; }}

                input {{
                    width: 100%;
                    border: 1px solid var(--border);
                    border-radius: 14px;
                    padding: 14px 16px;
                    font-size: 1rem;
                    outline: none;
                    transition: border-color 0.2s ease, box-shadow 0.2s ease;
                }}

                input:focus {{
                    border-color: var(--accent);
                    box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.15);
                }}

                button {{
                    width: 100%;
                    border: 0;
                    border-radius: 14px;
                    padding: 14px 16px;
                    background: linear-gradient(135deg, var(--accent), #1e40af);
                    color: white;
                    font-size: 1rem;
                    font-weight: 700;
                    cursor: pointer;
                    transition: transform 0.15s ease, filter 0.15s ease;
                }}

                button:hover {{
                    filter: brightness(1.05);
                    transform: translateY(-1px);
                }}

                .links {{
                    display: flex;
                    flex-wrap: wrap;
                    gap: 12px;
                    margin-top: 18px;
                }}

                .links a {{
                    color: var(--accent);
                    font-weight: 600;
                    text-decoration: none;
                }}

                .links a:hover {{
                    color: var(--accent-hover);
                    text-decoration: underline;
                }}

                .small {{
                    margin-top: 16px;
                    color: var(--muted);
                    font-size: 0.9rem;
                    line-height: 1.5;
                }}

                .stack {{ display: grid; gap: 14px; }}

                .panel {{
                    border: 1px solid var(--border);
                    border-radius: 18px;
                    padding: 18px;
                    background: rgba(255, 255, 255, 0.72);
                }}

                .panel h2 {{
                    margin: 0 0 10px;
                    font-size: 1.05rem;
                }}

                code {{
                    display: block;
                    margin-top: 12px;
                    padding: 12px 14px;
                    border-radius: 12px;
                    background: rgba(15, 23, 42, 0.05);
                    overflow-wrap: anywhere;
                }}

                .dashboard-grid {{
                    display: grid;
                    gap: 16px;
                }}

                @media (min-width: 760px) {{
                    .dashboard-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
                    .dashboard-grid .wide {{ grid-column: 1 / -1; }}
                }}
            </style>
        </head>
        <body>
            <main class="card">
                <p class="eyebrow">AI Hackaton</p>
                <h1>{escape(heading)}</h1>
                <p class="subtitle">{escape(subtitle)}</p>
                {message_block}
                {content}
            </main>
        </body>
    </html>
    """

    return HTMLResponse(content=html)


def render_login_page(error: str | None = None, email: str = "") -> HTMLResponse:
    safe_email = escape(email)
    content = f"""
    <form method="post" action="/">
        <div class="field">
            <label for="email">Email</label>
            <input id="email" name="email" type="email" value="{safe_email}" placeholder="name@example.com" required />
        </div>
        <div class="field">
            <label for="password">Password</label>
            <input id="password" name="password" type="password" placeholder="Enter your password" required />
        </div>
        <button type="submit">Log in</button>
    </form>
    <div class="links">
        <a href="/register">Create account</a>
        <a href="/forgot-password">Reset password</a>
    </div>
    <p class="small">Use the seeded local account: admin@example.com / password123.</p>
    """
    return render_page(
        "AI Hackaton Login",
        "Log in",
        "Enter your email and password to access the system.",
        content,
        message=error,
        message_kind="error" if error else "info",
    )


def render_register_page(error: str | None = None, email: str = "") -> HTMLResponse:
    safe_email = escape(email)
    content = f"""
    <form method="post" action="/register">
        <div class="field">
            <label for="email">Email</label>
            <input id="email" name="email" type="email" value="{safe_email}" placeholder="name@example.com" required />
        </div>
        <div class="field">
            <label for="password">Password</label>
            <input id="password" name="password" type="password" placeholder="Create a password" required />
        </div>
        <div class="field">
            <label for="confirm_password">Confirm password</label>
            <input id="confirm_password" name="confirm_password" type="password" placeholder="Repeat your password" required />
        </div>
        <button type="submit">Create account</button>
    </form>
    <div class="links">
        <a href="/">Back to login</a>
        <a href="/forgot-password">Reset password</a>
    </div>
    """
    return render_page(
        "AI Hackaton Registration",
        "Create account",
        "Register a new user to access the dashboard.",
        content,
        message=error,
        message_kind="error" if error else "info",
    )


def render_forgot_password_page(error: str | None = None, email: str = "") -> HTMLResponse:
    safe_email = escape(email)
    content = f"""
    <form method="post" action="/forgot-password">
        <div class="field">
            <label for="email">Email</label>
            <input id="email" name="email" type="email" value="{safe_email}" placeholder="name@example.com" required />
        </div>
        <button type="submit">Generate reset link</button>
    </form>
    <div class="links">
        <a href="/">Back to login</a>
        <a href="/register">Create account</a>
    </div>
    <p class="small">For local testing, the reset link is displayed on screen instead of being emailed.</p>
    """
    return render_page(
        "AI Hackaton Password Reset",
        "Reset password",
        "Request a reset link for an existing account.",
        content,
        message=error,
        message_kind="error" if error else "info",
    )


def render_reset_password_page(token: str, error: str | None = None) -> HTMLResponse:
    safe_token = escape(token)
    content = f"""
    <form method="post" action="/reset-password/{safe_token}">
        <div class="field">
            <label for="password">New password</label>
            <input id="password" name="password" type="password" placeholder="Enter a new password" required />
        </div>
        <div class="field">
            <label for="confirm_password">Confirm password</label>
            <input id="confirm_password" name="confirm_password" type="password" placeholder="Repeat the new password" required />
        </div>
        <button type="submit">Update password</button>
    </form>
    <div class="links">
        <a href="/">Back to login</a>
    </div>
    """
    return render_page(
        "AI Hackaton Reset Password",
        "Set a new password",
        "Use the reset token to choose a new password.",
        content,
        message=error,
        message_kind="error" if error else "info",
    )


def render_dashboard_page(
    user_email: str,
    session_token: str,
    *,
    message: str | None = None,
    message_kind: str = "success",
) -> HTMLResponse:
    safe_email = escape(user_email)
    safe_token = escape(session_token)
    content = f"""
    <div class="dashboard-grid">
        <section class="panel wide">
            <h2>Signed in</h2>
            <p>You are logged in as <strong>{safe_email}</strong>.</p>
            <p>Your authenticated session is stored in SQLite and protected by an HTTP-only cookie.</p>
            <code>Session token: {safe_token}</code>
        </section>
        <section class="panel">
            <h2>Account actions</h2>
            <div class="links" style="margin-top: 0; flex-direction: column; align-items: flex-start;">
                <a href="/logout">Log out</a>
                <a href="/forgot-password">Reset password</a>
                <a href="/register">Create another account</a>
            </div>
        </section>
        <section class="panel">
            <h2>Project status</h2>
            <p>The dashboard is protected. Unauthenticated users are returned to the login flow.</p>
        </section>
    </div>
    """
    return render_page(
        "AI Hackaton Dashboard",
        "Dashboard",
        "Protected workspace for authenticated users.",
        content,
        width="760px",
        message=message,
        message_kind=message_kind,
    )


def set_session_cookie(response: HTMLResponse, session_token: str) -> HTMLResponse:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    return response


def current_user(session_token: str | None) -> tuple[str, object] | None:
    if not session_token:
        return None

    user = get_user_by_session_token(session_token)
    if user is None:
        return None

    return session_token, user


@app.get("/", response_class=HTMLResponse)
def read_root(session_token: str | None = Cookie(default=None)) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is not None:
        _, user = authenticated
        return render_dashboard_page(user["email"], session_token or "")

    return render_login_page()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(session_token: str | None = Cookie(default=None)) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is None:
        return render_login_page("Please log in to access the dashboard.")

    _, user = authenticated
    return render_dashboard_page(user["email"], session_token or "")


@app.post("/", response_class=HTMLResponse)
def login(email: str = Form(...), password: str = Form(...)) -> HTMLResponse:
    if not email or not password:
        return render_login_page("Both email and password are required.", email=email)

    user = get_user_by_email(email)
    if user is None or not verify_password(password, user["password_hash"]):
        return render_login_page("Invalid email or password.", email=email)

    session_token, _ = create_session(user["id"])
    response = set_session_cookie(
        render_dashboard_page(user["email"], session_token, message="You are now logged in."),
        session_token,
    )
    return response


@app.get("/register", response_class=HTMLResponse)
def register_page() -> HTMLResponse:
    return render_register_page()


@app.post("/register", response_class=HTMLResponse)
def register(email: str = Form(...), password: str = Form(...), confirm_password: str = Form(...)) -> HTMLResponse:
    if not email or not password or not confirm_password:
        return render_register_page("All fields are required.", email=email)

    if password != confirm_password:
        return render_register_page("Passwords do not match.", email=email)

    if get_user_by_email(email) is not None:
        return render_register_page("That email is already registered.", email=email)

    user = create_user(email, password)
    session_token, _ = create_session(user["id"])
    response = set_session_cookie(
        render_dashboard_page(user["email"], session_token, message="Account created successfully."),
        session_token,
    )
    return response


@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page() -> HTMLResponse:
    return render_forgot_password_page()


@app.post("/forgot-password", response_class=HTMLResponse)
def forgot_password(email: str = Form(...)) -> HTMLResponse:
    if not email:
        return render_forgot_password_page("Email is required.")

    user = get_user_by_email(email)
    if user is None:
        return render_forgot_password_page(
            "If that account exists, a reset link will be created here.",
            email=email,
        )

    token, _ = create_password_reset_token(user["id"])
    reset_link = f"/reset-password/{token}"
    content = f"""
    <div class="stack">
        <section class="panel wide">
            <h2>Reset link created</h2>
            <p>A reset link is ready for <strong>{escape(email)}</strong>.</p>
            <code>{escape(reset_link)}</code>
            <div class="links">
                <a href="{escape(reset_link)}">Open reset page</a>
                <a href="/">Back to login</a>
            </div>
        </section>
    </div>
    """
    return render_page(
        "AI Hackaton Reset Link",
        "Password reset link",
        "Open the generated link to set a new password.",
        content,
        width="520px",
        message="For local testing, the reset link is shown on screen instead of being emailed.",
        message_kind="success",
    )


@app.get("/reset-password/{token}", response_class=HTMLResponse)
def reset_password_page(token: str) -> HTMLResponse:
    reset_token = get_password_reset_token(token)
    if reset_token is None:
        return render_page(
            "AI Hackaton Reset Password",
            "Reset link expired",
            "The password reset token is invalid or expired.",
            '<div class="links"><a href="/forgot-password">Request a new reset link</a></div>',
            message="That reset link cannot be used.",
            message_kind="error",
        )

    return render_reset_password_page(token)


@app.post("/reset-password/{token}", response_class=HTMLResponse)
def reset_password(
    token: str,
    password: str = Form(...),
    confirm_password: str = Form(...),
) -> HTMLResponse:
    reset_token = get_password_reset_token(token)
    if reset_token is None:
        return render_page(
            "AI Hackaton Reset Password",
            "Reset link expired",
            "The password reset token is invalid or expired.",
            '<div class="links"><a href="/forgot-password">Request a new reset link</a></div>',
            message="That reset link cannot be used.",
            message_kind="error",
        )

    if not password or not confirm_password:
        return render_reset_password_page(token, "Both password fields are required.")

    if password != confirm_password:
        return render_reset_password_page(token, "Passwords do not match.")

    user_id = reset_token["user_id"]
    update_user_password(user_id, password)
    delete_sessions_for_user(user_id)
    mark_password_reset_token_used(token)

    user = get_user_by_id(user_id)
    if user is None:
        return render_login_page("Password updated, but the account could not be reloaded.")

    session_token, _ = create_session(user["id"])
    response = set_session_cookie(
        render_dashboard_page(user["email"], session_token, message="Password updated successfully."),
        session_token,
    )
    return response


@app.get("/logout", response_class=HTMLResponse)
def logout(session_token: str | None = Cookie(default=None)) -> HTMLResponse:
    if session_token:
        delete_session(session_token)

    response = render_login_page("You have been logged out.")
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
