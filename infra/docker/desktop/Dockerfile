FROM lscr.io/linuxserver/chromium:latest

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY services/controller-api/requirements.txt /tmp/controller-requirements.txt
RUN /lsiopy/bin/pip3 install --no-cache-dir -r /tmp/controller-requirements.txt

WORKDIR /opt/capture

COPY services/controller-api/src /opt/capture/services/controller-api/src
COPY services/desktop-agent/src /opt/capture/services/desktop-agent/src
COPY services/desktop-agent/scripts /opt/capture/services/desktop-agent/scripts
COPY packages/capture_contracts /opt/capture/packages/capture_contracts
COPY infra/docker/desktop/s6-rc.d /etc/s6-overlay/s6-rc.d
RUN chmod +x /opt/capture/services/desktop-agent/scripts/*.sh /etc/s6-overlay/s6-rc.d/svc-desktop-agent/run

ENV PYTHONPATH=/opt/capture/services/controller-api/src:/opt/capture/services/desktop-agent/src:/opt/capture/packages \
    CAPTURE_RUNTIME_DIR=/tmp/capture-runtime

EXPOSE 3000 8790 9222
