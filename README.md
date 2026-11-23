# Saint Lucia ministry website

Django application for the Ministry of Infrastructure, Port Services and Energy, preserving the navy, teal and gold homepage design and Castries harbour imagery.

## Docker with shared development services

The Docker stack uses the existing **kingship-shared-services** development services: PostgreSQL on `shared-dev-database`, Redis database 12 with a `ministry-website` key prefix, Mailpit for captured email, and shared Nginx on `shared-dev-proxy`. It does not start duplicate database, cache or mail servers.

Start the shared development services first, then run from this repository:

```sh
python3 scripts/setup_docker.py
docker compose --env-file .env.docker up -d --build --wait
```

The setup script generates a private, ignored `.env.docker` and creates a dedicated `ministry_website_dev` PostgreSQL role and database. It preserves existing credentials and databases when rerun. Override `SHARED_POSTGRES_CONTAINER` if your shared development PostgreSQL container has a different name. Review `.env.docker.example` for hostnames, ports and settings.

Open http://localhost:8000/ or http://localhost:8000/staff/. The `init` service waits for shared PostgreSQL and Redis, applies migrations and collects static files. Gunicorn runs as a non-root user. The gateway serves static assets and uploaded PDFs from persistent volumes. A single `notifications` worker checks for eligible emails every five minutes and sends them to shared Mailpit at http://localhost:8025/. Keep one notification worker per database.

To enable the shared Nginx route (installed on this workstation):

```sh
cp docker/shared-nginx.conf ../kingship-shared-services/nginx/dev-conf.d/ministry-website.conf
docker exec shared-services-dev-nginx-1 nginx -t
docker exec shared-services-dev-nginx-1 nginx -s reload
```

The route is http://ministry.localhost/ (also available on port 8080). It connects to the gateway's unique `ministry-website-dev` network alias. If your local resolver does not resolve `.localhost`, use localhost:8000 or map `ministry.localhost` to `127.0.0.1`. Change `SITE_URL`, `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` together when changing the canonical address. This configuration targets the local shared development stack.

Useful commands:

```sh
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs -f web notifications
docker compose --env-file .env.docker exec web python manage.py createsuperuser
docker compose --env-file .env.docker exec web python manage.py seed_content
docker compose --env-file .env.docker exec web python manage.py send_notifications --dry-run
docker compose --env-file .env.docker run --rm --no-deps -e DB_HOST= -e REDIS_URL= web python manage.py test pages
docker compose --env-file .env.docker down
```

The test command uses an isolated in-memory SQLite database. `/healthz/` checks the running application's database and cache and returns HTTP 503 if either is unavailable. `down` preserves the application's upload/static volumes and its shared PostgreSQL database. Back up the PostgreSQL database and `media_data` volume together.

### Existing local data

The current SQLite data, including seeded content and staff accounts, has been imported into the dedicated PostgreSQL database. A private pre-transfer backup and export are stored in the ignored `.docker-state/` directory. The original `app/db.sqlite3` is retained. Docker and a host-run development server now use separate databases.

For a different checkout with existing SQLite data, export before switching databases:

```sh
mkdir -p .docker-state
chmod 700 .docker-state
(umask 077; .venv/bin/python app/manage.py dumpdata auth pages --exclude auth.permission --natural-foreign --natural-primary > .docker-state/sqlite-export.json)
```

Import **once into a new application database** after migrations, with the notification worker stopped:

```sh
docker compose --env-file .env.docker stop notifications
docker compose --env-file .env.docker exec -T web python manage.py loaddata --format=json - < .docker-state/sqlite-export.json
# If there are existing uploads, copy them into the media volume:
# docker compose --env-file .env.docker cp app/mediafiles/. web:/srv/media/
docker compose --env-file .env.docker start notifications
```

Do not import the old export over an actively edited Docker database. Schema migrations run automatically on startup; content seeding and SQLite imports are explicit operations.

## Remote deployment on .157

The source code and sample content are deployed in `/home/kingship/ministry-website` on `10.104.20.157`, using the next available application port, **8006**. Existing local accounts, uploaded documents and database exports are excluded from the deployment.

The remote `.env.docker` contains freshly generated credentials, `APP_PORT=8006`, `DEPLOY_BIND=10.104.20.157`, `SHARED_PROXY_NETWORK=shared-proxy`, `PROXY_ALIAS=ministry-website-web` and `SITE_URL=https://infrastucture.kingship.info`. HTTPS cookies are enabled. PostgreSQL and Redis use the existing shared development services with a dedicated application database and cache prefix. Outgoing notifications are captured by shared Mailpit.

Use both Compose files on this server:

```sh
cd /home/kingship/ministry-website
docker compose --env-file .env.docker -f compose.yaml -f compose.remote.yaml up -d --build --wait
docker compose --env-file .env.docker -f compose.yaml -f compose.remote.yaml exec web python manage.py seed_content
docker compose --env-file .env.docker -f compose.yaml -f compose.remote.yaml ps
```

The gateway listens at `http://10.104.20.157:8006/` and `http://127.0.0.1:8006/`. In Pangolin, route the HTTP resource for **infrastucture.kingship.info** through the existing .157 site to **10.104.20.157:8006**, using HTTP upstream. The gateway preserves `X-Forwarded-Proto: https` from the edge. Staff sign-in should use the HTTPS domain because the remote cookies are secure.

Create a fresh staff account on the remote server when needed:

```sh
docker compose --env-file .env.docker -f compose.yaml -f compose.remote.yaml exec web python manage.py createsuperuser
```

## Run without Docker

Python 3.10+ is required.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r app/requirements.txt
cd app
../.venv/bin/python manage.py migrate
DEBUG=1 ../.venv/bin/python manage.py runserver
```

Open http://127.0.0.1:8000/. The homepage works without database content. Migrations initialise Django’s built-in admin/auth tables.

## Architecture

- **Django 5.2:** full-page rendering, curated content, search and resource filtering.
- **Alpine.js 3.14.9:** mobile menu, search panel, focus handling, Escape dismissal and request error messages.
- **HTMX 2.0.11:** submits search and filters resource cards using server-rendered HTML fragments, without reloading the page.

Both JavaScript libraries are pinned and served locally from `app/static/vendor/`; no Node build is required. Their upstream projects are [Alpine.js](https://alpinejs.dev/) (MIT) and [HTMX](https://htmx.org/) (BSD 2-Clause). Google Fonts remains optional, with system-font fallbacks.

Routes:

| URL | Behaviour |
| --- | --- |
| `/` | Homepage; accepts `?category=notice` or `?category=publication` |
| `/search/?q=roads` | Search fragment for HTMX, full page for a normal request |
| `/updates/?category=notice` | Resource fragment for HTMX, full page for a normal request |
| `/staff/` | Custom staff workspace |
| `/staff/login/` | Staff sign in |
| `/admin/` | Account administration only |

Search covers homepage sections, published staff content and FAQs. Navigation, search, resource filters, FAQs and subscription forms work without JavaScript.

Edit `app/pages/content.py` for curated section links and official resource cards, `app/templates/` for markup, and `app/static/` for styling and scripts. Staff content and FAQs are managed through the custom staff workspace. Run Django to use the server-backed interactions.

## Staff publishing

To populate the local site with demonstration content, run:

```sh
.venv/bin/python app/manage.py seed_content
```

This adds eight published sample items (two per content type), one draft, one scheduled item and two FAQs. Sample items are clearly labelled, and notification delivery is disabled for them. Rerunning the command preserves existing records and staff edits.

After migrating, create the initial administrator:

```sh
.venv/bin/python app/manage.py createsuperuser
```

Open http://127.0.0.1:8000/staff/ (also linked as **Staff sign in** in the footer). Sign in with an existing staff account. For additional editors, an account administrator can create users, enable **Staff status** and assign the **Content editors** group. The initial superuser can also sign in directly. The workspace checks staff status and the specific add, view, change or delete permission for every action. Content editors cannot access subscriber email addresses or account administration.

The overview shows draft, scheduled and published counts and recent content. **Website content** includes search, content type and status filters, pagination, and create, edit, saved-page preview and delete views. Select Publication, News, Notice or Project / programme when creating an item. Enter a title, summary and body; optionally add an official source link or public PDF up to 10 MB. Leave the page address blank to generate a unique one from the title. Save with **Publish this item** unchecked for a draft. Check it when ready; a future publication date schedules visibility in Saint Lucia time. Published items appear on the homepage, category filters and search, with individual detail pages. Documents are public files; only upload documents intended for public access.

**FAQs** has its own list, create, edit and delete screens. Questions have editable answers, display order and visibility. Four introductory FAQs are installed by migration. Deletions require a confirmation page and POST; viewing a delete page does not remove anything. All forms use CSRF protection and sign-out requires POST.

**Subscribers** is a read-only overview for users with the subscriber view permission (including superusers). It shows confirmation state, topics and searchable email addresses. Subscriber consent and topic choices stay under subscriber control. These features are not registered in Django admin; `/admin/` is retained for account administration only.

## Email notifications

The homepage subscription form collects an email, topic choices and explicit consent. A confirmation email contains a link valid for 48 hours; the visitor must press **Confirm subscription** on that page. Repeat requests have a five-minute cooldown. Existing subscribers can submit the form again to change topics after confirmation. Each update contains an unsubscribe link leading to a confirmation page; opening a link alone does not change a subscription.

Local email is saved under `app/emails/`, so local testing does not send real mail. To test, submit the form, open the confirmation URL from the saved email, and confirm. Publish a new item with **Notify subscribers** checked, then run:

```sh
.venv/bin/python app/manage.py send_notifications --dry-run
.venv/bin/python app/manage.py send_notifications
```

Only confirmed, active subscribers following the item's topic receive it. Subscribers do not receive items published before their confirmation. Drafts and future items are excluded. Delivery records prevent normal repeat sends and failed sends can be retried. Run a single worker; as with SMTP generally, a process failure after SMTP acceptance but before recording delivery may cause a duplicate on retry. Editing an item does not resend it to recipients already notified.

For real email, configure these environment variables (or an ignored `.env` file):

```dotenv
SITE_URL=https://your-ministry-domain.example
SECRET_KEY=replace-with-a-long-random-production-secret
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
DEFAULT_FROM_EMAIL=Ministry updates <updates@your-ministry-domain.example>
EMAIL_HOST=smtp.your-provider.example
EMAIL_PORT=587
EMAIL_HOST_USER=your-smtp-user
EMAIL_HOST_PASSWORD=your-smtp-password
EMAIL_USE_TLS=1
```

Schedule **one** `send_notifications` worker every five minutes using the deployment's scheduler, for example with cron (replace `/path/to/ministry-website`):

```cron
*/5 * * * * cd /path/to/ministry-website/app && /path/to/ministry-website/.venv/bin/python manage.py send_notifications
```

For deployments outside Docker, SMTP credentials and the scheduler must be configured before automatic delivery is active. Docker configures shared Mailpit and starts the notification worker automatically. Serve uploaded PDFs from `MEDIA_ROOT` in production; Django serves them locally with `DEBUG=1`. Back up the database and uploaded files together.

## Checks

```sh
.venv/bin/python app/manage.py check
.venv/bin/python app/manage.py test pages
node --check app/static/js/site.js
```

`DEBUG` defaults to false and accepts `1`, `true` or `yes`. Use `DEBUG=1` for local development and Django’s static-file serving. Deployment configuration is separate from this local migration.

## Content and imagery

- Ministry branding uses “Ministry of Infrastructure, Port Services and Energy”, as supplied. Existing official service and resource URLs are retained.
- Resources link to official sources. The January 2025 SLASPA notice is explicitly marked as archived; no current tender availability is implied.
- Castries harbour photograph: [Unsplash image source](https://images.unsplash.com/photo-1622896900858-99ad8da7b8d9), found through the [Castries photo collection](https://unsplash.com/s/photos/castries).
- Coat of arms: [Government of Saint Lucia ministry portal](https://infrastructure.govt.lc/Images/logo-41.png). The source is a small raster image and should be replaced with an official high-resolution asset before launch.
- Roadwork photographs were already present in the repository. They are illustrative; verify usage rights and replace them with ministry project photography before production use.
- DM Sans and Manrope load from Google Fonts, with local system-font fallbacks.
