# The API, built to fit a free container host.
#
# Deliberately no Playwright and no Chromium. They are needed for one rung of
# reading a pasted URL -- the rendered-page fallback -- and they would roughly
# quintuple this image and want more memory than a free instance has. Without
# them that rung is skipped and the posting is looked up through Google for
# Jobs instead, which is where it was headed next anyway. Searching, scoring,
# tailoring and export are unaffected. Install requirements-dev.txt to get the
# browser back locally.

FROM python:3.13-slim

# WeasyPrint renders the PDF export through Pango and Cairo, which it loads
# from the system by name rather than bundling. Without these, PDF export
# reports itself unavailable and Word export still works -- so they are worth
# the few megabytes. The DejaVu fonts give the renderer something to draw
# with; a slim image ships no fonts at all.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements first: this layer is cached until the pins themselves change.
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Hosts assign the port at runtime and expect the app to read $PORT. The shell
# form is deliberate -- exec form would pass the variable through unexpanded.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
