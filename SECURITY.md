# Security

## Reporting a problem

Please do **not** open a public issue for a security problem. Use GitHub's private
reporting: **Security → Report a vulnerability** on this repository.
Include what you found, how to repeat it and which version. You will get an answer within a few days.

## What the app protects, and how

- **Your keys** are entered in the app and stored encrypted for your Windows user (DPAPI) in `keys.dat`.
  The page can never read them back. They are removed from the logs and are never sent to an AI.
- **The dashboard** (the window and the phone link) always needs a password.
  - The first visit with the link logs the browser in with an `HttpOnly`, `SameSite=Strict` cookie and
    redirects to a clean address: the password is not left in the address bar, the history or the reach of a script.
  - It listens **only on this PC**. Phone access is a switch in Settings > Privacy and data; it is off for a new install.
  - Five wrong tries lock that address for a minute, then two, four ... up to 15 minutes.
  - A change that names an `Origin` must come from the page's own host, so another web page cannot press buttons here (CSRF).
    Requests under a foreign host name are refused (DNS rebinding).
  - Every answer carries a Content-Security-Policy (scripts only from the app's own files), `nosniff`,
    `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`.
  - "Make a new dashboard password" in Settings replaces the password; old links stop working.
- **Real money** is never armed by the app itself; arming needs you after every start. Stop is checked
  right before every order.
- **Nothing is sent to the author.** There is no server of ours. The app talks only to the services you connect
  (Alpaca, an AI provider) and public news and price sources. The full list is in [PRIVACY.md](PRIVACY.md),
  and `tests/test_privacy.py` fails when the code names a server that is not on it.

## Please never

- commit `.env`, `keys.dat`, `dashboard.token`, `data/` or logs;
- paste keys into issues. If you did, revoke them at the provider at once.

Not financial advice. See `installer/terms.txt`.
