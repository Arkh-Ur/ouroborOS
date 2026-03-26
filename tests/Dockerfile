FROM archlinux:latest

# Refresh keyring and update system first (avoids signature errors)
RUN pacman-key --init && \
    pacman-key --populate archlinux && \
    pacman -Syu --noconfirm

# Install test dependencies via pacman
RUN pacman -S --noconfirm --needed \
    shellcheck \
    python \
    python-pip \
    python-yaml \
    git \
    bash \
    findutils \
    grep \
    coreutils \
    util-linux && \
    pacman -Scc --noconfirm

# Install Python tools via pip (newer versions than Arch repos for dev tools)
RUN pip install --no-cache-dir --break-system-packages \
    ruff \
    pytest \
    pytest-cov

# Non-root user for tests that should not run as root
RUN useradd -m -s /bin/bash testrunner && \
    echo 'testrunner ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

WORKDIR /workspace

# Default: drop to bash (overridden by docker-compose services)
CMD ["bash"]
