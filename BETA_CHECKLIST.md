# Beta Checklist

## Deploy Target

- Primary: Railway (cheap + fast start)
- Alternative: Fly.io
- Domain: `tene.app`
- SSL: provider auto TLS enabled

## Preflight

- [ ] `python -m pytest tests/ -q` passes
- [ ] `python -m alembic upgrade head` on production DB
- [ ] Health endpoint responds: `GET /health/`
- [ ] Stripe keys configured in environment
- [ ] SMTP optional vars set (if weekly email report enabled)

## Postman API Smoke

- [ ] Import `postman_collection.json`
- [ ] Set `base_url` to deployed URL
- [ ] Register test user
- [ ] Verify email via `/auth/verify-email`
- [ ] Login and set `access_token`
- [ ] Run assistant + calendar endpoints

## 3 Beta Users

1. Owner (you)
2. Friend #1
3. Friend #2

### Validate with beta users

- [ ] Voice upload + transcript
- [ ] Voice -> calendar event
- [ ] Weekly summary quality
- [ ] Billing checkout flow (test mode)
- [ ] Performance + errors report
