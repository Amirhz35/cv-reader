"""
Django management command to wait for databases to be ready.
"""

import time
import logging
import os
from django.core.management.base import BaseCommand
from django.db import connection
import mongoengine
import redis

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Wait for databases to be ready'

    def add_arguments(self, parser):
        parser.add_argument(
            '--timeout',
            type=int,
            default=60,
            help='Timeout in seconds to wait for databases'
        )

    def handle(self, *args, **options):
        timeout = options['timeout']
        start_time = time.time()

        self.stdout.write('Waiting for databases...')

        # Wait for MySQL
        while True:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                self.stdout.write(self.style.SUCCESS('MySQL is ready'))
                break
            except Exception as e:
                if time.time() - start_time > timeout:
                    self.stderr.write(self.style.ERROR(f'MySQL not ready after {timeout} seconds'))
                    return
                self.stdout.write(f'Waiting for MySQL: {e}')
                time.sleep(2)

        # Wait for MongoDB
        while True:
            try:
                mongoengine.connection.get_db().command('ping')
                self.stdout.write(self.style.SUCCESS('MongoDB is ready'))
                break
            except Exception as e:
                if time.time() - start_time > timeout:
                    self.stderr.write(self.style.ERROR(f'MongoDB not ready after {timeout} seconds'))
                    return
                self.stdout.write(f'Waiting for MongoDB: {e}')
                time.sleep(2)

        # Wait for Redis
        redis_host = os.getenv('REDIS_HOST', 'redis')
        redis_port = int(os.getenv('REDIS_PORT', '6379'))
        while True:
            try:
                r = redis.Redis(host=redis_host, port=redis_port, socket_timeout=5)
                r.ping()
                self.stdout.write(self.style.SUCCESS('Redis is ready'))
                break
            except Exception as e:
                if time.time() - start_time > timeout:
                    self.stderr.write(self.style.ERROR(f'Redis not ready after {timeout} seconds'))
                    return
                self.stdout.write(f'Waiting for Redis: {e}')
                time.sleep(2)

        self.stdout.write(self.style.SUCCESS('All services are ready!'))
