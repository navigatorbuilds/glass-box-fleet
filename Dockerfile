# Glass-Box Fleet — Cloud Run image (A1b: no node, no consensus; sealer + ADK only)
# Stage 1: build the Rust sealer (crates.io deps only — elara-record 0.3.0)
FROM rust:1.90-slim AS sealer-build
WORKDIR /build
COPY sealer/ sealer/
RUN cd sealer && cargo build --release

# Stage 2: runtime — Python ADK app + sealer binary
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agents/ agents/
COPY glassbox/ glassbox/
COPY ui/ ui/
COPY --from=sealer-build /build/sealer/target/release/sealer /app/sealer/target/release/sealer
ENV GLASSBOX_EVIDENCE_DIR=/tmp/evidence
# SEALER_IDENTITY is mounted via Secret Manager at deploy time — never baked into the image.
EXPOSE 8080
CMD ["python", "-m", "ui.server"]
