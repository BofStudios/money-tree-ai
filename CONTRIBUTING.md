# Contributing

Thanks for helping. Small, clear changes are the easiest to merge.

1. Fork, then `pip install -r requirements.txt`.
2. Run the tests: `python -m pytest -q tests` (all must pass).
3. Keep the safety rules: Stop must win, real money is never armed by code, no keys in commits.
4. Words shown to users are short and plain (ASD-STE100 style) and exist in English and Turkish
   (`app/web/static/i18n.js`).
5. Open a pull request that says what changed and why.

Never include keys, `.env` files or data folders in a commit or an issue.
