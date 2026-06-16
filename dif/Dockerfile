# Mahsa DIF sidecar — multi-stage build to a small runtime image.
FROM rust:1-slim AS build
WORKDIR /build
COPY Cargo.toml ./
COPY src ./src
COPY rules ./rules
COPY tests ./tests
RUN cargo build --release && strip target/release/mahsa

FROM debian:bookworm-slim
RUN useradd -r -u 10001 mahsa
COPY --from=build /build/target/release/mahsa /usr/local/bin/mahsa
USER mahsa
ENV MAHSA_ADDR=0.0.0.0:8088
EXPOSE 8088
ENTRYPOINT ["mahsa"]
