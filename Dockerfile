FROM python:3.10

RUN groupadd -g 1000 app && useradd -m -g 1000 -u 1000 app

WORKDIR /home/app

COPY --chown=1000:1000 . cephfs-disk-usage

WORKDIR /home/app/cephfs-disk-usage

RUN pip install --no-cache-dir -e .

CMD ["python", "-m", "cephfs_disk_usage"]
