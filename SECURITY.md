# Security

## Reporting a problem

Please do **not** open a public issue for a security problem. Use GitHub's private
reporting: **Security → Report a vulnerability** on this repository.
Include what you found, how to repeat it and which version. You will get an answer within a few days.

## What the app protects, and how

- **Your keys** are entered in the app and stored encrypted for your Windows user (DPAPI) in `keys.dat`.
  The page can never read them back. They are removed from the logs.
- **The dashboard** (the window and the phone link) always needs a password. If `.env` sets none, the
  app makes a random one and keeps it in the data folder. Requests under a foreign host name are refused.
- **Real money** is never armed by the app itself; arming needs you after every start. Stop is checked
  right before every order.
- **Nothing is sent to the author.** The app talks only to the services you connect (Alpaca, an AI provider)
  and public news and price sources.

## Please never

- commit `.env`, `keys.dat`, `dashboard.token`, `data/` or logs;
- paste keys into issues. If you did, revoke them at the provider at once.

Not financial advice. See `installer/terms.txt`.
