FROM otel/opentelemetry-collector-contrib:0.127.0
COPY deployments/otel-collector/config-azure.yaml /etc/otel-collector-config.yaml
CMD ["--config=/etc/otel-collector-config.yaml"]
