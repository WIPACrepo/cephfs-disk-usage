"""
Server
"""

import asyncio
from dataclasses import dataclass as dc
import json
import logging
import os
from pathlib import Path
import stat
import time
from typing import Self

from tornado.web import RequestHandler, HTTPError
from rest_tools.server import RestServer
from wipac_dev_tools import from_environment

from . import __version__ as version

logger = logging.getLogger('server')


class Error(RequestHandler):
    def prepare(self):
        raise HTTPError(404, 'invalid route')


class BaseHandler(RequestHandler):
    def initialize(self, filesystems):
        self.filesystems = filesystems

    def set_default_headers(self):
        self._headers['Server'] = f'CephFS Disk Usage {version}'

    def get_template_namespace(self):
        ret = super().get_template_namespace()
        ret['os'] = os
        ret['json_encode'] = json.dumps
        return ret


class Health(BaseHandler):
    async def get(self):
        ret = {}
        for k in self.filesystems:
            ret[k] = await self.filesystems[k].status()
        if any(r != 'OK' for r in ret.values()):
            self.set_status(500)
        self.write(ret)


class Main(BaseHandler):
    async def get(self):
        paths = {}
        for k in self.filesystems:
            paths[k] = await self.filesystems[k].dir_entry('/')
        self.render('main.html', paths=paths)


class Details(BaseHandler):
    async def get(self, path):
        for fs in self.filesystems:
            if path.startswith(fs):
                data = await self.filesystems[fs].dir_entry(path[len(fs):])
                break
        else:
            raise HTTPError(400, reason='bad path')

        self.render('details.html', path=path, data=data)


async def call(*args, shell=False):
    if shell:
        ret = await asyncio.create_subprocess_shell(' '.join(args), stdout=asyncio.subprocess.PIPE)
    else:
        ret = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE)
    out,err = await ret.communicate()
    if ret.returncode:
        raise Exception(f'call failed: return code {ret.returncode}')
    if not shell:
        out = out.decode('utf-8')
    return out


@dc
class Entry:
    name: str
    path: str
    size: int
    is_dir: bool = False
    is_link: bool = False
    nfiles: int = 0
    percent_size: float = 0.0


@dc
class DirEntry:
    name: str
    path: str
    size: int
    nfiles: int
    children: list

    @classmethod
    def from_entry(cls, e: Entry) -> Self:
        if not e.is_dir:
            raise Exception('is not a directory!')
        return cls(e.name, e.path, e.size, e.nfiles, [])


class POSIXFileSystem:
    def __init__(self, base_path):
        self.base_path = Path(base_path)

    async def status(self):
        try:
            async with asyncio.timeout(5):
                await call('/usr/bin/ls', str(self.base_path))
        except Exception as e:
            return f'FAIL: {e}'
        return 'OK'

    async def _get_meta(self, path: Path) -> Entry:
        """Get recursive size and nfiles for a path"""
        if not path.is_relative_to(self.base_path):
            raise Exception('not relative to base path')
        p = str(path)
        async with asyncio.timeout(30):
            stats = await asyncio.to_thread(path.stat)
            is_dir = stat.S_ISDIR(stats.st_mode)
            is_link = stat.S_ISLNK(stats.st_mode)
            if is_dir:
                size, nfiles = await asyncio.gather(
                    call('du', '-s', '-b', p, shell=True),
                    call(f'find "{p}" -type f | wc -l', shell=True)
                )
                size = int(size.split()[0])
                nfiles = int(nfiles.strip())
            else:
                size = stats.st_size
                nfiles = 0
        return Entry(path.name, p, size, is_dir, is_link, nfiles)

    async def dir_entry(self, path: str) -> DirEntry:
        """Get directory contents"""
        fullpath = self.base_path / path.lstrip('/')
        if not fullpath.is_dir():
            raise Exception('not a directory!')

        tasks = set()
        for child in fullpath.iterdir():
            tasks.add(tg.create_task(self._get_meta(child)))

        ret = DirEntry.from_entry(await self._get_meta(fullpath))
        start_time = time.time()
        while tasks:
            if time.time() - start_time > 60:
                raise HTTPError(500, reason='Request timed out')
            done, tasks = await asyncio.wait(tasks, timeout=5)
            for task in done:
                try:
                    r = await task
                except FileNotFoundError:
                    logger.debug('error', exc_info=True)
                    continue
                except Exception:
                    logger.warning('error', exc_info=True)
                    continue
                r.percent_size = r.size*100.0/ret.size
                ret.children.append(r)
        ret.children.sort(key=lambda r: r.name)

        return ret


class CephFileSystem(POSIXFileSystem):
    async def _get_meta(self, path: Path) -> Entry:
        """Get recursive size and nfiles for a path"""
        if not path.is_relative_to(self.base_path):
            raise Exception('not relative to base path')
        p = str(path)
        async with asyncio.timeout(30):
            stats = await asyncio.to_thread(path.stat)
            is_dir = stat.S_ISDIR(stats.st_mode)
            is_link = stat.S_ISLNK(stats.st_mode)
            if is_dir:
                size, nfiles = await asyncio.gather(
                    call('/usr/bin/getfattr', '-n', 'ceph.dir.rbytes', p),
                    call('/usr/bin/getfattr', '-n', 'ceph.dir.rfiles', p)
                )
                size = int(size.split('=')[-1].strip('" \n'))
                nfiles = int(nfiles.split('=')[-1].strip('" \n'))
            else:
                size = stats.st_size
                nfiles = 0
        return Entry(path.name, p, size, is_dir, is_link, nfiles)


class Server:
    def __init__(self, s3_override=None):
        static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
        template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

        default_config = {
            'HOST': 'localhost',
            'PORT': 8080,
            'DEBUG': False,
            'MAX_BODY_SIZE': 10**9,
            'CI_TESTING': '',
        }
        config = from_environment(default_config)

        kwargs = {}
        if config['CI_TESTING']:
            cwd = os.path.abspath(config['CI_TESTING'])
            kwargs['filesystems'] = {
                cwd: POSIXFileSystem(cwd),
            }
        else:
            kwargs['filesystems'] = {
                '/data/ana': CephFileSystem('/data/ana'),
                '/data/user': CephFileSystem('/data/user'),
            }

        server = RestServer(
            static_path=static_path,
            template_path=template_path,
            debug=config['DEBUG'],
            max_body_size=config['MAX_BODY_SIZE'],
        )

        server.add_route('/', Main, kwargs)
        # handle moving up gracefully
        if config['CI_TESTING']:
            server.add_route(cwd, Main, kwargs)
        else:
            server.add_route('/data', Main, kwargs)
        server.add_route('/healthz', Health, kwargs)
        server.add_route(r'(.*)', Details, kwargs)

        server.startup(address=config['HOST'], port=config['PORT'])

        self.server = server

    async def start(self):
        pass

    async def stop(self):
        await self.server.stop()
