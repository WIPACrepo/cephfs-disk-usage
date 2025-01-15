FROM python:3.12

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y attr

RUN groupadd -g 1000 app && useradd -m -g 1000 -u 1000 app

WORKDIR /home/app

COPY --chown=1000:1000 . cephfs-disk-usage

RUN pip install --no-cache-dir -e cephfs-disk-usage

CMD ["python", "-m", "cephfs_disk_usage"]
